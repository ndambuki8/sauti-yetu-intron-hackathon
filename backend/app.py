"""Voice Triage Hint — FastAPI app.

Endpoints:
- GET  /               simple white-page UI
- GET  /api/languages  supported patient languages for the dropdown
- POST /api/triage     audio -> Intron Sahara -> agentic triage card
- POST /api/benchmark  audio + reference -> 3-model code-switch benchmark
"""

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import benchmark as benchmark_module
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
