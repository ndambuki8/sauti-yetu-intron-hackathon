"""Voice Triage Hint — FastAPI app.

Endpoints:
- GET  /               simple white-page UI
- GET  /api/languages  supported patient languages for the dropdown
- GET  /api/phrases    quick-reply phrases translated to patient language
- POST /api/triage     audio -> Intron Sahara -> agentic triage card
- POST /api/respond    worker reply -> NLLB translation -> Intron TTS audio
- POST /api/benchmark  audio + reference -> 3-model code-switch benchmark
"""

import base64

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import benchmark as benchmark_module
from . import phrases as phrases_module
from . import translator, tts_client
from .config import FRONTEND_DIR, SUPPORTED_LANGUAGES
from .intron_client import IntronError, transcribe_telehealth
from .triage import run_triage

app = FastAPI(title="Voice Triage Hint")

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # sanity limit; sync API caps at 120s anyway


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


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


@app.post("/api/triage")
def triage(
    audio: UploadFile = File(...),
    language_code: str = Form("en"),
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

    triage_result = run_triage(intron_result, SUPPORTED_LANGUAGES[language_code])

    return {
        "transcript": intron_result["transcript"],
        "summary": intron_result["summary"],
        "duration_seconds": intron_result["duration_seconds"],
        "triage": triage_result,
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

    return benchmark_module.run_benchmark(
        audio_bytes,
        filename=audio.filename or "recording.webm",
        reference_transcript=reference_transcript.strip(),
        language_code=language_code,
    )


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
