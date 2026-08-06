"""Client for the Intron Sahara text-to-speech API.

Synthesizes the health worker's (translated) reply in the patient's language
using a native voice. Handles the documented 503 + text_id timeout path by
polling the Get Text Status endpoint, then downloads the generated audio
server-side (avoids CORS and keeps the API key off the client).

Docs: https://docs.voice.intron.io/docs/tts/tts-generate
"""

import time

import requests

from .config import INTRON_API_KEY, INTRON_BASE_URL

TTS_GENERATE_URL = f"{INTRON_BASE_URL}/tts/v1/generate"
TTS_STATUS_URL = f"{INTRON_BASE_URL}/tts/v1/status/{{text_id}}"

POLL_INTERVAL_SECONDS = 4
POLL_TIMEOUT_SECONDS = 120

# App language code -> (voice_language, voice_accent) per the TTS docs.
# Zulu has no native TTS voice, so it falls back to English speech with the
# zulu accent; the translated Zulu text is still shown on screen.
TTS_VOICE_MAP = {
    "sw": ("sw", "swahili"),
    "ha": ("ha", "hausa"),
    "yo": ("yo", "yoruba"),
    "ig": ("ig", "igbo"),
    "am": ("am", "amharic"),
    "rw": ("rw", "kinyarwanda"),
    "pcm": ("pcm", "pidgin"),
    "lg": ("lg", "luganda"),
    "wo": ("wo", "wolof"),
    "af": ("af", "afrikaans"),
    "zu": ("en", "zulu"),
    "en": ("en", "swahili"),
}

# Languages where the audio is spoken in English rather than the patient's
# language (no native voice available).
ENGLISH_AUDIO_FALLBACK = {"zu"}


class IntronTTSError(Exception):
    pass


def _headers() -> dict:
    if not INTRON_API_KEY:
        raise IntronTTSError(
            "INTRON_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return {"Authorization": f"Bearer {INTRON_API_KEY}"}


def synthesize(text: str, language_code: str, voice_gender: str = "female") -> dict:
    """Generate speech for ``text`` in the patient's language.

    Returns {"audio_bytes": bytes, "audio_format": "wav",
             "spoken_language": str, "english_fallback": bool}.
    """
    if language_code not in TTS_VOICE_MAP:
        raise IntronTTSError(f"No TTS voice available for language: {language_code}")
    if voice_gender not in ("male", "female"):
        raise IntronTTSError(f"Invalid voice gender: {voice_gender}")

    voice_language, voice_accent = TTS_VOICE_MAP[language_code]
    payload = {
        "text": text,
        "voice_language": voice_language,
        "voice_accent": voice_accent,
        "voice_gender": voice_gender,
        "output_audio_format": "wav",
    }

    response = requests.post(
        TTS_GENERATE_URL, headers=_headers(), json=payload, timeout=150
    )

    if response.status_code == 200:
        data = response.json().get("data", {}) or {}
    elif response.status_code == 503:
        text_id = _extract_text_id(response)
        if not text_id:
            raise IntronTTSError("Intron TTS timed out without returning a text_id.")
        data = _poll_status(text_id)
    else:
        raise IntronTTSError(
            f"Intron TTS error {response.status_code}: {response.text[:500]}"
        )

    audio_path = data.get("audio_path")
    if not audio_path:
        raise IntronTTSError(f"Intron TTS returned no audio_path: {data}")

    audio = requests.get(audio_path, timeout=60)
    if audio.status_code != 200:
        raise IntronTTSError(f"Failed to download TTS audio ({audio.status_code}).")

    return {
        "audio_bytes": audio.content,
        "audio_format": "wav",
        "spoken_language": voice_language,
        "english_fallback": language_code in ENGLISH_AUDIO_FALLBACK,
    }


def _extract_text_id(response: requests.Response) -> str | None:
    try:
        data = response.json().get("data", {}) or {}
        return data.get("text_id") or data.get("text-id")
    except ValueError:
        return None


def _poll_status(text_id: str) -> dict:
    url = TTS_STATUS_URL.format(text_id=text_id)
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        response = requests.get(url, headers=_headers(), timeout=30)
        if response.status_code == 200:
            data = response.json().get("data", {}) or {}
            status = data.get("processing_status")
            if status == "TTS_TEXT_AUDIO_GENERATED":
                return data
            if status == "TTS_TEXT_AUDIO_PROCESSING_FAILED":
                raise IntronTTSError("Intron TTS reported processing failed.")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise IntronTTSError("Timed out waiting for Intron TTS to finish.")
