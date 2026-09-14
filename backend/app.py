"""Voice Triage Hint — FastAPI app.

Endpoints:
- GET    /                      Expo web build (app/dist) or legacy Vite build
- GET    /api/languages         patient + doctor language lists
- GET    /api/phrases           quick-reply phrases translated to patient language
- POST   /api/session           start a consultation (returns session_id)
- GET    /api/session/{id}      session graph, history, artifacts
- DELETE /api/session/{id}      end a consultation
- POST   /api/triage            audio -> detect/STT -> triage card + graph
- POST   /api/respond           worker reply -> NLLB translation -> Intron TTS
- POST   /api/command           doctor voice/text command -> report/flowchart
- POST   /api/benchmark         audio + reference -> 3-model benchmark
"""

import base64
import json

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import lid, phrases as phrases_module
from . import translator, tts_client
from .config import (
    APP_DIR,
    DOCTOR_LANGUAGES,
    FRONTEND_DIR,
    SAHARA_OUTPUT_LANGUAGES,
    SUPPORTED_LANGUAGES,
)
from .extract import extract_patient_hints
from .graph import build_graph_delta
from .graph_store import SESSION_STORE
from .intron_client import IntronError, transcribe_plain, transcribe_telehealth
from .triage import PatientContext, run_triage

app = FastAPI(title="Voice Triage Hint")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

EXPO_DIST = APP_DIR / "dist"
VITE_DIST = FRONTEND_DIR / "dist"
DIST_DIR = EXPO_DIST if EXPO_DIST.exists() else VITE_DIST


@app.get("/")
def index():
    index_file = DIST_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(
            status_code=404,
            detail="Frontend not built. Run `npx expo export --platform web` "
            "in app/, or use the Expo dev server.",
        )
    return FileResponse(index_file)


@app.get("/api/languages")
def languages():
    return {
        "languages": {"auto": "Auto-detect", **SUPPORTED_LANGUAGES},
        "doctor_languages": DOCTOR_LANGUAGES,
    }


def _read_audio(audio: UploadFile) -> bytes:
    audio_bytes = audio.file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")
    if len(audio_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Audio file too large (max 25 MB).")
    return audio_bytes


def _resolve_patient_language(
    language_code: str,
    audio_bytes: bytes,
    filename: str,
    prior_language: str | None = None,
) -> tuple[str, dict | None]:
    """Return (intron_language_code, audio_detection_or_None)."""
    if language_code != "auto":
        return language_code, None
    fallback = prior_language if prior_language in SUPPORTED_LANGUAGES else "en"
    try:
        from .asr_models import detect_language

        detected = detect_language(audio_bytes, filename)
    except Exception as exc:
        return fallback, {
            "language_code": fallback,
            "mms_code": None,
            "confidence": 0,
            "error": str(exc)[:200],
        }
    code = detected["language_code"]
    if code not in SUPPORTED_LANGUAGES:
        code = fallback
    return code, detected


@app.post("/api/session")
def create_session(
    doctor_language: str = "en",
    patient_language: str = "auto",
):
    if doctor_language not in DOCTOR_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported doctor language: {doctor_language}")
    if patient_language != "auto" and patient_language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {patient_language}")
    session_id = SESSION_STORE.create(doctor_language, patient_language)
    return {
        "session_id": session_id,
        "doctor_language": doctor_language,
        "patient_language": patient_language,
    }


@app.get("/api/session/{session_id}")
def get_session(session_id: str):
    if not SESSION_STORE.exists(session_id):
        raise HTTPException(status_code=404, detail="Unknown session.")
    full = SESSION_STORE.get_full(session_id)
    return {
        "session_id": session_id,
        "graph": {
            "nodes": full["nodes"],
            "edges": full["edges"],
            "turns": full["turns"],
        },
        "doctor_language": full["doctor_language"],
        "patient_language": full["patient_language"],
        "detected_languages": full["detected_languages"],
        "artifacts": full["artifacts"],
    }


@app.delete("/api/session/{session_id}", status_code=204)
def delete_session(session_id: str):
    if not SESSION_STORE.delete(session_id):
        raise HTTPException(status_code=404, detail="Unknown session.")


@app.post("/api/triage")
def triage(
    audio: UploadFile = File(...),
    language_code: str = Form("auto"),
    doctor_language: str = Form("en"),
    session_id: str | None = Form(None),
    age: float | None = Form(None),
    sex: str | None = Form(None),
    pregnant: bool | None = Form(None),
    hr: float | None = Form(None),
    rr: float | None = Form(None),
    temp: float | None = Form(None),
    spo2: float | None = Form(None),
    avpu: str | None = Form(None),
):
    if language_code != "auto" and language_code not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language_code}")
    if doctor_language not in DOCTOR_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported doctor language: {doctor_language}")

    audio_bytes = _read_audio(audio)
    filename = audio.filename or "recording.webm"
    try:
        from .asr_models import prepare_for_intron

        audio_bytes, filename = prepare_for_intron(audio_bytes, filename)
    except Exception:
        pass

    prior_language = None
    if session_id and SESSION_STORE.exists(session_id):
        prior_language = SESSION_STORE.last_patient_language(session_id)

    asr_language, audio_detection = _resolve_patient_language(
        language_code, audio_bytes, filename, prior_language
    )
    output_language = doctor_language if doctor_language in SAHARA_OUTPUT_LANGUAGES else "en"

    try:
        intron_result = transcribe_telehealth(
            audio_bytes,
            filename=filename,
            language_code=asr_language,
            output_language=output_language,
        )
    except IntronError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    transcript_patient = intron_result["transcript"] or ""
    text_detection = None
    if language_code == "auto":
        text_detection = lid.identify(transcript_patient)
        if text_detection and text_detection["language_code"] in SUPPORTED_LANGUAGES:
            asr_language = text_detection["language_code"]

    detection = None
    if language_code == "auto":
        detection = {
            "audio": audio_detection,
            "text": text_detection,
            "final": asr_language,
        }

    language_name = SUPPORTED_LANGUAGES.get(asr_language, asr_language)

    explicit_age = age if age is not None and age >= 0 else None
    explicit_sex = sex if sex in ("male", "female") else None
    hints = extract_patient_hints(
        intron_result.get("transcript", ""),
        intron_result.get("summary", ""),
        intron_result.get("entities", ""),
    )
    eff_age = explicit_age if explicit_age is not None else hints["age"]
    eff_sex = explicit_sex if explicit_sex is not None else hints["sex"]
    eff_pregnant = pregnant if pregnant is not None else hints["pregnant"]
    auto_detected: list[str] = []
    if explicit_age is None and hints["age"] is not None:
        auto_detected.append("age")
    if explicit_sex is None and hints["sex"] is not None:
        auto_detected.append("sex")
    if pregnant is None and hints["pregnant"] is not None:
        auto_detected.append("pregnancy")

    patient = PatientContext(
        age=eff_age,
        sex=eff_sex,
        pregnant=eff_pregnant,
        hr=hr,
        rr=rr,
        temp=temp,
        spo2=spo2,
        avpu=avpu if avpu else None,
    )
    triage_result = run_triage(intron_result, language_name, patient)
    triage_result["auto_detected"] = auto_detected
    triage_result["patient_context"] = {
        "age": eff_age,
        "sex": eff_sex,
        "pregnant": eff_pregnant,
        "hr": hr,
        "rr": rr,
        "temp": temp,
        "spo2": spo2,
        "avpu": avpu or None,
    }

    transcript_doctor = translator.translate_to_doctor(
        transcript_patient, asr_language, doctor_language
    )
    if output_language != doctor_language:
        intake = triage_result.get("intake_card") or {}
        for key in ("presenting_complaint", "key_findings", "possible_conditions", "red_flags"):
            if intake.get(key):
                intake[key] = translator.translate_to_doctor(
                    intake[key], output_language, doctor_language
                )
        if intron_result.get("summary"):
            intron_result["summary"] = translator.translate_to_doctor(
                intron_result["summary"], output_language, doctor_language
            )
        if triage_result.get("clarifying_questions"):
            triage_result["clarifying_questions"] = [
                translator.translate_to_doctor(q, output_language, doctor_language)
                for q in triage_result["clarifying_questions"]
            ]

    if not session_id or not SESSION_STORE.exists(session_id):
        session_id = SESSION_STORE.create(doctor_language, language_code)

    turn = SESSION_STORE.get(session_id)["turns"] + 1
    delta = build_graph_delta(intron_result, triage_result, turn)
    graph = SESSION_STORE.append(session_id, delta)
    SESSION_STORE.record_turn(
        session_id,
        detected_language=asr_language,
        transcript_patient=transcript_patient,
        transcript_doctor=transcript_doctor,
        triage=triage_result,
        summary=intron_result.get("summary") or "",
    )
    full = SESSION_STORE.get_full(session_id)

    return {
        "transcript": transcript_patient,
        "transcript_patient": transcript_patient,
        "transcript_doctor": transcript_doctor,
        "detected_language": asr_language,
        "detection": detection,
        "doctor_language": doctor_language,
        "summary": intron_result["summary"],
        "duration_seconds": intron_result["duration_seconds"],
        "triage": triage_result,
        "session_id": session_id,
        "graph": graph,
        "detected_languages": full["detected_languages"],
        "artifacts": full["artifacts"],
    }


@app.get("/api/phrases")
def phrases(language_code: str = "en"):
    if language_code not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language_code}")
    try:
        return {"phrases": phrases_module.get_phrases(language_code)}
    except Exception as exc:
        bank = [
            {"english": p, "translated": p, "translation_error": str(exc)[:200]}
            for p in phrases_module._load_bank().get("phrases", [])
        ]
        return {"phrases": bank}


class RespondRequest(BaseModel):
    text: str
    language_code: str = "en"
    voice_gender: str = "female"
    skip_translation: bool = False


@app.post("/api/respond")
def respond(req: RespondRequest):
    if req.language_code not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {req.language_code}")
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required.")
    if len(text) > 2000:
        raise HTTPException(status_code=400, detail="Text too long (max 2000 characters).")

    cached = phrases_module.lookup_cached(text, req.language_code)
    if req.skip_translation:
        translated_text = text
        was_translated = False
    elif cached:
        translated_text = cached
        was_translated = True
    else:
        try:
            result = translator.translate(text, req.language_code)
            translated_text = result["translated_text"]
            was_translated = result["was_translated"]
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Translation failed (is the NLLB model installed?): {exc}",
            )

    speak_text = (
        text
        if req.language_code in tts_client.ENGLISH_AUDIO_FALLBACK
        else translated_text
    )
    try:
        speech = tts_client.synthesize(speak_text, req.language_code, req.voice_gender)
    except tts_client.IntronTTSError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "original_text": text,
        "translated_text": translated_text,
        "was_translated": was_translated,
        "english_fallback": speech["english_fallback"],
        "audio_base64": base64.b64encode(speech["audio_bytes"]).decode("ascii"),
        "audio_format": speech["audio_format"],
    }


@app.post("/api/command")
def command(
    session_id: str = Form(...),
    text: str = Form(""),
    audio: UploadFile | None = File(None),
):
    if not SESSION_STORE.exists(session_id):
        raise HTTPException(status_code=404, detail="Unknown session.")

    command_text = (text or "").strip()
    if audio is not None and audio.filename:
        audio_bytes = _read_audio(audio)
        if audio_bytes:
            filename = audio.filename or "command.m4a"
            try:
                from .asr_models import prepare_for_intron

                audio_bytes, filename = prepare_for_intron(audio_bytes, filename)
            except Exception:
                pass
            full = SESSION_STORE.get_full(session_id)
            doctor_lang = full["doctor_language"]
            asr_lang = doctor_lang if doctor_lang in SUPPORTED_LANGUAGES else "en"
            try:
                spoken = transcribe_plain(
                    audio_bytes,
                    filename=filename,
                    language_code=asr_lang,
                )
            except IntronError as exc:
                raise HTTPException(status_code=502, detail=str(exc))
            command_text = (spoken.get("transcript") or "").strip() or command_text

    if not command_text:
        raise HTTPException(status_code=400, detail="Speak or type a command.")

    from .agent import AgentError, run_command

    full = SESSION_STORE.get_full(session_id)
    try:
        generated = run_command(command_text, full)
    except AgentError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    stored = SESSION_STORE.add_artifact(
        session_id,
        {
            "command_text": command_text,
            **generated,
        },
    )
    return {
        "session_id": session_id,
        "command_text": command_text,
        "intent": stored["intent"],
        "artifact": stored,
        "artifacts": SESSION_STORE.get_full(session_id)["artifacts"],
    }


@app.post("/api/benchmark")
def run_benchmark(
    audio: UploadFile = File(...),
    reference_transcript: str = Form(...),
    language_code: str = Form("en"),
    switch_points: str = Form("[]"),
    agent_reference: str = Form(""),
    agentic: bool = Form(False),
):
    if not reference_transcript.strip():
        raise HTTPException(status_code=400, detail="Reference transcript is required.")
    audio_bytes = _read_audio(audio)

    from . import benchmark as benchmark_module

    try:
        parsed_switch_points = json.loads(switch_points or "[]")
        parsed_agent_reference = json.loads(agent_reference) if agent_reference else None
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid benchmark annotation JSON: {exc}")
    if not isinstance(parsed_switch_points, list):
        raise HTTPException(status_code=400, detail="switch_points must be a JSON list.")
    if parsed_agent_reference is not None and not isinstance(parsed_agent_reference, dict):
        raise HTTPException(status_code=400, detail="agent_reference must be a JSON object.")

    return benchmark_module.run_benchmark(
        audio_bytes,
        filename=audio.filename or "recording.webm",
        reference_transcript=reference_transcript.strip(),
        language_code=language_code,
        switch_points=parsed_switch_points,
        agent_reference=parsed_agent_reference,
        agentic=agentic,
    )


if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="spa")
