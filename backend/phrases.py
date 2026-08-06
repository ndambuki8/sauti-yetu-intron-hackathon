"""Quick-reply phrase bank for the health worker.

English source phrases live in phrases.json. Translations are produced by
the local NLLB model on first request and cached back into the same JSON
file, so a native speaker can review and hand-correct them before a demo —
manually edited entries are never overwritten.
"""

import json
import threading
from pathlib import Path

from . import translator

PHRASES_PATH = Path(__file__).resolve().parent / "phrases.json"

_lock = threading.Lock()


def _load_bank() -> dict:
    with open(PHRASES_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _save_bank(bank: dict) -> None:
    with open(PHRASES_PATH, "w", encoding="utf-8") as fh:
        json.dump(bank, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def get_phrases(language_code: str) -> list[dict]:
    """Return quick replies as [{"english": ..., "translated": ...}, ...].

    For passthrough languages (en, pcm) the translated text equals the
    English text. Missing translations are generated once and cached.
    """
    with _lock:
        bank = _load_bank()
        phrases = bank.get("phrases", [])

        if language_code in translator.PASSTHROUGH:
            return [{"english": p, "translated": p} for p in phrases]

        cache = bank.setdefault("translations", {}).setdefault(language_code, {})
        dirty = False
        for phrase in phrases:
            if not cache.get(phrase):
                result = translator.translate(phrase, language_code)
                if result["was_translated"]:
                    cache[phrase] = result["translated_text"]
                    dirty = True
        if dirty:
            _save_bank(bank)

        return [
            {"english": p, "translated": cache.get(p, p)}
            for p in phrases
        ]


def lookup_cached(text: str, language_code: str) -> str | None:
    """Return the cached translation for a bank phrase, or None."""
    with _lock:
        bank = _load_bank()
        return bank.get("translations", {}).get(language_code, {}).get(text)
