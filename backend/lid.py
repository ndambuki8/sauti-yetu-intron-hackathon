"""Closed-set text language-ID for Auto patient language.

Used after Sahara returns a transcript so a wrong Whisper audio guess
(usually English) does not lock replies/TTS to the wrong language.

langdetect is lazy-imported so the triage tests still run if it is missing.
"""

import re

from .config import SUPPORTED_LANGUAGES

# langdetect ISO-639-1 -> our Intron / app codes.
# Only languages langdetect actually emits are listed.
LANGDETECT_TO_APP = {
    "en": "en",
    "sw": "sw",
    "af": "af",
    "fr": "fr",
    "am": "am",
    "ha": "ha",
    "yo": "yo",
    "ig": "ig",
    "zu": "zu",
}

# Ethiopic (Ge'ez) block — Amharic in our set.
_ETHIOPIC = re.compile(r"[\u1200-\u137F]")

MIN_CONFIDENCE = 0.55
MIN_CHARS = 8


def _ethiopic_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha() or "\u1200" <= c <= "\u137F"]
    if not letters:
        return 0.0
    hits = sum(1 for c in letters if _ETHIOPIC.match(c))
    return hits / len(letters)


def identify(text: str) -> dict | None:
    """Return {language_code, confidence, source} or None if unsure.

    Never invents Pidgin. Unknown / low-confidence text returns None
    so the caller can keep the audio guess or the session prior.
    """
    text = (text or "").strip()
    if len(text) < MIN_CHARS:
        return None

    if _ethiopic_ratio(text) >= 0.3:
        return {"language_code": "am", "confidence": 0.99, "source": "script"}

    try:
        from langdetect import detect_langs
    except ImportError:
        return None

    try:
        ranked = detect_langs(text)
    except Exception:
        return None

    if not ranked:
        return None

    top = ranked[0]
    confidence = float(getattr(top, "prob", 0))
    if confidence < MIN_CONFIDENCE:
        return None

    app_code = LANGDETECT_TO_APP.get(top.lang)
    if app_code == "fr":
        # French is doctor-facing, not an Intron patient ASR mode here.
        return None
    if app_code not in SUPPORTED_LANGUAGES:
        return None

    return {
        "language_code": app_code,
        "confidence": round(confidence, 3),
        "source": "langdetect",
    }
