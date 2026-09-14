"""Client for the Intron Sahara speech-to-text API.

Uses the synchronous file-upload endpoint with telehealth post-processing.
If the sync call times out (HTTP 503 returns a file_id), falls back to
polling the Get File Status endpoint.

Docs: https://docs.voice.intron.io
"""

import time

import requests

from .config import INTRON_API_KEY, INTRON_BASE_URL

SYNC_UPLOAD_URL = f"{INTRON_BASE_URL}/file/v1/upload/sync"
STATUS_URL = f"{INTRON_BASE_URL}/file/v1/status/{{file_id}}"

# Telehealth extractions requested alongside the transcript.
TELEHEALTH_OPTIONS = {
    "get_summary": "TRUE",
    "get_entity_list": "TRUE",
    "get_suggestions": "TRUE",
    "get_differential_diagnosis": "TRUE",
    "get_followup_instructions": "TRUE",
}

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 180


class IntronError(Exception):
    pass


def _headers() -> dict:
    if not INTRON_API_KEY:
        raise IntronError(
            "INTRON_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return {"Authorization": f"Bearer {INTRON_API_KEY}"}


def _request(method: str, url: str, **kwargs) -> requests.Response:
    """requests call with transport errors normalized to IntronError,
    so the API returns a clean 502 instead of an unhandled 500 traceback."""
    try:
        return requests.request(method, url, **kwargs)
    except requests.exceptions.SSLError as exc:
        raise IntronError(
            "TLS certificate verification failed while contacting Intron. "
            "This is a local environment issue (outdated CA certificates or a "
            "TLS-inspecting antivirus/proxy), not an Intron outage. "
            f"Detail: {exc}"
        ) from exc
    except requests.RequestException as exc:
        raise IntronError(f"Could not reach the Intron API: {exc}") from exc


def transcribe_telehealth(
    audio_bytes: bytes,
    filename: str,
    language_code: str = "en",
    output_language: str = "en",
) -> dict:
    """Transcribe patient audio and extract clinical structure.

    The transcript comes back in the patient's language; the extractions
    (summary, entities, differential diagnosis, suggestions) come back in
    ``output_language`` so the practitioner can read them.
    """
    form = {
        "audio_file_name": (None, filename),
        "use_category": (None, "file_category_telehealth"),
        "use_language_asr_input": (None, language_code),
        "use_language_data_extraction_output": (None, output_language),
    }
    for key, value in TELEHEALTH_OPTIONS.items():
        form[key] = (None, value)
    form["audio_file_blob"] = (filename, audio_bytes)

    response = _request(
        "POST", SYNC_UPLOAD_URL, headers=_headers(), files=form, timeout=150
    )

    if response.status_code == 200:
        return _parse_result(response.json())

    if response.status_code == 503:
        file_id = _extract_file_id(response)
        if file_id:
            return _poll_status(file_id)
        raise IntronError("Intron timed out without returning a file_id.")

    raise IntronError(
        f"Intron API error {response.status_code}: {response.text[:500]}"
    )


def transcribe_plain(audio_bytes: bytes, filename: str, language_code: str = "en") -> dict:
    """Plain transcription (no post-processing) — used for benchmarking.

    Returns {"transcript": str, "latency_seconds": float}.
    """
    form = {
        "audio_file_name": (None, filename),
        "use_language_asr_input": (None, language_code),
        "audio_file_blob": (filename, audio_bytes),
    }
    start = time.monotonic()
    response = _request(
        "POST", SYNC_UPLOAD_URL, headers=_headers(), files=form, timeout=150
    )
    if response.status_code == 503:
        file_id = _extract_file_id(response)
        if not file_id:
            raise IntronError("Intron timed out without returning a file_id.")
        result = _poll_status(file_id)
    elif response.status_code == 200:
        result = _parse_result(response.json())
    else:
        raise IntronError(
            f"Intron API error {response.status_code}: {response.text[:500]}"
        )
    return {
        "transcript": result.get("transcript", ""),
        "latency_seconds": time.monotonic() - start,
    }


def _extract_file_id(response: requests.Response) -> str | None:
    try:
        return response.json().get("data", {}).get("file_id")
    except ValueError:
        return None


def _poll_status(file_id: str) -> dict:
    url = STATUS_URL.format(file_id=file_id)
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        response = _request(
            "GET",
            url,
            headers=_headers(),
            params={"get_structured_post_processing": "t"},
            timeout=30,
        )
        if response.status_code == 200:
            data = response.json().get("data", {})
            status = data.get("processing_status")
            if status == "FILE_TRANSCRIBED":
                return _parse_result(response.json())
            if status == "FILE_PROCESSING_FAILED":
                raise IntronError("Intron reported FILE_PROCESSING_FAILED.")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise IntronError("Timed out waiting for Intron to finish processing.")


def _first_key_containing(data: dict, *needles: str) -> str:
    """Best-effort lookup: exact post-processing key names are not fully
    documented, so match any response key containing all the needles."""
    for key, value in data.items():
        lowered = key.lower()
        if all(needle in lowered for needle in needles) and value:
            return str(value)
    return ""


def _parse_result(payload: dict) -> dict:
    """Normalize the Intron response into the fields the app uses."""
    data = payload.get("data", {}) or {}
    transcript = data.get("audio_transcript") or _first_key_containing(data, "transcript")
    return {
        "transcript": transcript,
        "summary": _first_key_containing(data, "summary"),
        "entities": _first_key_containing(data, "entity"),
        "differential_diagnosis": _first_key_containing(data, "differential"),
        "suggestions": _first_key_containing(data, "suggestion"),
        "followup_instructions": _first_key_containing(data, "follow"),
        "duration_seconds": data.get("processed_audio_duration_in_seconds"),
        "raw": data,
    }
