"""Voice Triage Hint — FastAPI app.

Endpoints:
- GET    /                      built React SPA (frontend/dist)
- GET    /api/languages         supported patient languages for the dropdown
- POST   /api/session           start a consultation (returns session_id)
- DELETE /api/session/{id}      end a consultation (drops its graph)
- POST   /api/triage            audio -> Intron Sahara -> triage card + graph
- POST   /api/benchmark         audio + reference -> 3-model benchmark

The clinical reasoning graph is built only on the Sahara triage flow —
the benchmark endpoint never touches it.

Frontend: React + TypeScript + Vite. During development use the Vite dev
server (port 5173, proxies /api here); for a single-process deployment run
`npm run build` in frontend/ and this app serves frontend/dist directly.
"""

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIR, SUPPORTED_LANGUAGES
from .graph import build_graph_delta
from .graph_store import SESSION_STORE
from .intron_client import IntronError, transcribe_telehealth
from .triage import run_triage

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
