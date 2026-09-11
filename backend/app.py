"""Voice Triage Hint — FastAPI app.

Endpoints:
- GET    /                      built React SPA (frontend/dist)
- GET    /api/languages         supported patient languages for the dropdown
- GET    /api/phrases           quick-reply phrases translated to patient language
- POST   /api/session           start a consultation (returns session_id)
- DELETE /api/session/{id}      end a consultation (drops its graph)
- POST   /api/triage            audio -> Intron Sahara -> triage card + graph
- POST   /api/respond           worker reply -> NLLB translation -> Intron TTS audio
- POST   /api/benchmark         audio + reference -> 3-model benchmark

The clinical reasoning graph is built only on the Sahara triage flow —
the benchmark endpoint never touches it.

Frontend: React + TypeScript + Vite. During development use the Vite dev
server (port 5173, proxies /api here); for a single-process deployment run
`npm run build` in frontend/ and this app serves frontend/dist directly.
"""

import base64

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# NOTE: benchmark is imported lazily inside its endpoint (pulls in
# jiwer/torch/whisper, which the triage flow must not require).
from . import phrases as phrases_module
from . import translator, tts_client
from .config import FRONTEND_DIR, SUPPORTED_LANGUAGES
from .graph import build_graph_delta
from .extract import extract_patient_hints
from .graph_store import SESSION_STORE
from .intron_client import IntronError, transcribe_telehealth
from .triage import PatientContext, run_triage

app = FastAPI(title="Voice Triage Hint")

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # sanity limit; sync API caps at 120s anyway

DIST_DIR = FRONTEND_DIR / "dist"


@app.get("/")
def index():
    index_file = DIST_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(
            status_code=404,
            detail="Frontend not built. Run `npm run build` in frontend/, "
            "or use the Vite dev server on http://localhost:5173.",
        )
    return FileResponse(index_file)


@app.get("/api/languages")
def languages():
    return {"languages": SUPPORTED_LANGUAGES}


# Endpoints are deliberately sync (`def`): FastAPI runs them in a threadpool,
# so the blocking Intron HTTP calls and local model inference don't stall
# the event loop.
def _read_audio(audio: UploadFile) -> bytes:
    audio_bytes = audio.file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")
    if len(audio_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Audio file too large (max 25 MB).")
    return audio_bytes


@app.post("/api/session")
def create_session():
    """Start a consultation. The returned session_id accumulates a clinical
    reasoning graph across every triage call that passes it."""
    return {"session_id": SESSION_STORE.create()}


@app.delete("/api/session/{session_id}", status_code=204)
def delete_session(session_id: str):
    if not SESSION_STORE.delete(session_id):
        raise HTTPException(status_code=404, detail="Unknown session.")


@app.post("/api/triage")
def triage(
    audio: UploadFile = File(...),
    language_code: str = Form("en"),
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
    if language_code not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language_code}")
    audio_bytes = _read_audio(audio)

    try:
        intron_result = transcribe_telehealth(
            audio_bytes,
            filename=audio.filename or "recording.webm",
            language_code=language_code,
            output_language="en",
        )
    except IntronError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # Explicit clinician input wins; anything left blank is filled from what the
    # patient said in the conversation, and flagged as auto-detected for review.
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
    auto_detected = []
    if explicit_age is None and hints["age"] is not None:
        auto_detected.append("age")
    if explicit_sex is None and hints["sex"] is not None:
        auto_detected.append("sex")
    if pregnant is None and hints["pregnant"] is not None:
        auto_detected.append("pregnancy")

    # Age/sex gate age-conditional IITT discriminators; unknown never excludes.
    # Vitals (optional) drive the age-banded high-risk vital-sign checks.
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
    triage_result = run_triage(intron_result, SUPPORTED_LANGUAGES[language_code], patient)
    triage_result["auto_detected"] = auto_detected

    # Unknown or missing session ids start a fresh consultation implicitly,
    # so direct API callers don't need the session endpoints.
    if not session_id or not SESSION_STORE.exists(session_id):
        session_id = SESSION_STORE.create()
    turn = SESSION_STORE.get(session_id)["turns"] + 1
    delta = build_graph_delta(intron_result, triage_result, turn)
    graph = SESSION_STORE.append(session_id, delta)

    return {
        "transcript": intron_result["transcript"],
        "summary": intron_result["summary"],
        "duration_seconds": intron_result["duration_seconds"],
        "triage": triage_result,
        "session_id": session_id,
        "graph": graph,
    }


@app.get("/api/phrases")
def phrases(language_code: str = "en"):
    if language_code not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {language_code}")
    try:
        return {"phrases": phrases_module.get_phrases(language_code)}
    except Exception as exc:
        # Translation model missing/unavailable: still return English phrases
        # so the worker can use passthrough quick replies.
        bank = [
            {"english": p, "translated": p, "translation_error": str(exc)[:200]}
            for p in phrases_module._load_bank().get("phrases", [])
        ]
        return {"phrases": bank}


class RespondRequest(BaseModel):
    text: str
    language_code: str = "en"
    voice_gender: str = "female"
    # Set when the text is already in the patient's language
    # (e.g. a pre-translated quick reply) and must not be re-translated.
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
        # Quick replies reuse the vetted phrase-bank cache instead of
        # re-running the translation model.
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

    # Languages without a native TTS voice (e.g. Zulu) are spoken in English
    # with a local accent; the translated text is still shown on screen.
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


@app.post("/api/benchmark")
def run_benchmark(
    audio: UploadFile = File(...),
    reference_transcript: str = Form(...),
    language_code: str = Form("en"),
):
    if not reference_transcript.strip():
        raise HTTPException(status_code=400, detail="Reference transcript is required.")
    audio_bytes = _read_audio(audio)

    # Imported lazily: benchmark pulls in jiwer/torch/whisper, which the
    # triage flow (and its tests) must not require.
    from . import benchmark as benchmark_module

    return benchmark_module.run_benchmark(
        audio_bytes,
        filename=audio.filename or "recording.webm",
        reference_transcript=reference_transcript.strip(),
        language_code=language_code,
    )


# Serve the Vite production build as a single-page app. Mounted last so the
# /api routes above always win. Requires a restart after `npm run build`.
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=DIST_DIR, html=True), name="spa")
