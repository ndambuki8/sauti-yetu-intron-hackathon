"""Reproducible code-switch and agentic benchmark harness.

The basic ``run_benchmark`` contract remains useful for the API endpoint. The
optional annotations add switch-point WER and downstream triage metrics, while
the ``agentic`` mode runs Sahara's telehealth extraction before the triage
layer. Model failures are isolated so one unavailable model does not discard a
clip.
"""

import re
import time
import wave
from pathlib import Path

import jiwer

from . import asr_models, intron_client, triage
from .config import SUPPORTED_LANGUAGES

_NORMALIZE = jiwer.Compose(
    [
        jiwer.ToLowerCase(),
        jiwer.RemovePunctuation(),
        jiwer.RemoveMultipleSpaces(),
        jiwer.Strip(),
    ]
)


def _score(reference: str, hypothesis: str) -> dict:
    ref = _NORMALIZE(reference)
    hyp = _NORMALIZE(hypothesis)
    if not ref:
        return {"wer": None, "cer": None}
    return {
        "wer": round(jiwer.wer(ref, hyp), 4),
        "cer": round(jiwer.cer(ref, hyp), 4),
    }


def _tokens(text: str) -> list[str]:
    return _NORMALIZE(text).split()


def _switch_point_score(
    reference: str, hypothesis: str, switch_points: list[dict] | None, radius: int = 3
) -> dict:
    """Score a reference window around each annotated language boundary.

    ``token_index`` is the number of reference tokens before the switch. The
    clip-level WER remains the primary metric; this local score makes boundary
    degradation visible without claiming forced word-level alignment.
    """
    if not switch_points:
        return {"wer": None, "count": 0, "windows": []}

    reference_tokens = _tokens(reference)
    hypothesis_tokens = _tokens(hypothesis)
    windows = []
    for point in switch_points:
        try:
            boundary = int(point["token_index"])
        except (KeyError, TypeError, ValueError):
            continue
        start = max(0, boundary - radius)
        end = min(len(reference_tokens), boundary + radius)
        reference_window = " ".join(reference_tokens[start:end])
        hypothesis_window = " ".join(hypothesis_tokens[start:end])
        score = _score(reference_window, hypothesis_window)
        windows.append(
            {
                "token_index": boundary,
                "from_language": point.get("from_language"),
                "to_language": point.get("to_language"),
                "reference_window": reference_window,
                "hypothesis_window": hypothesis_window,
                "wer": score["wer"],
            }
        )
    values = [window["wer"] for window in windows if window["wer"] is not None]
    return {
        "wer": round(sum(values) / len(values), 4) if values else None,
        "count": len(windows),
        "windows": windows,
    }


def _normalized_value(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _agentic_score(intron_result: dict, language_code: str, expected: dict | None) -> dict | None:
    if not expected:
        return None
    result = triage.run_triage(
        intron_result,
        SUPPORTED_LANGUAGES.get(language_code, language_code),
    )
    checks = {}
    for field in ("topic", "urgency", "suggested_department"):
        expected_value = expected.get(f"expected_{field}")
        if expected_value:
            checks[field] = {
                "expected": expected_value,
                "predicted": result[field],
                "correct": _normalized_value(result[field]) == _normalized_value(expected_value),
            }

    expected_slots = expected.get("expected_slots") or {}
    slot_checks = {}
    for key, value in expected_slots.items():
        predicted = result["intake_card"].get(key, "")
        slot_checks[key] = {
            "expected": value,
            "predicted": predicted,
            "correct": _normalized_value(predicted) == _normalized_value(value),
        }

    expected_entities = [
        _normalized_value(entity) for entity in (expected.get("expected_entities") or [])
    ]
    predicted_entities = [
        _normalized_value(entity)
        for entity in result["intake_card"].get("key_findings", "").split(";")
        if entity.strip()
    ]
    missing = [entity for entity in expected_entities if entity not in predicted_entities]
    spurious = [entity for entity in predicted_entities if entity not in expected_entities]
    entity_denominator = len(expected_entities) + len(spurious)
    entity_error_rate = (
        round((len(missing) + len(spurious)) / entity_denominator, 4)
        if entity_denominator
        else None
    )
    return {
        "topic": result["topic"],
        "urgency": result["urgency"],
        "suggested_department": result["suggested_department"],
        "field_checks": checks,
        "slot_checks": slot_checks,
        "intent_correct": checks.get("topic", {}).get("correct"),
        "slot_accuracy": (
            round(sum(item["correct"] for item in slot_checks.values()) / len(slot_checks), 4)
            if slot_checks
            else None
        ),
        "entity_error_rate": entity_error_rate,
        "missing_entities": missing,
        "spurious_entities": spurious,
    }


def run_benchmark(
    audio_bytes: bytes,
    filename: str,
    reference_transcript: str,
    language_code: str = "en",
    switch_points: list[dict] | None = None,
    agent_reference: dict | None = None,
    agentic: bool = False,
) -> dict:
    """Run all three models and optionally score switch points and triage."""
    suffix = Path(filename).suffix or ".webm"
    wav_path = asr_models.convert_to_wav_16k(audio_bytes, suffix=suffix)
    with wave.open(str(wav_path), "rb") as wav_file:
        duration_seconds = wav_file.getnframes() / wav_file.getframerate()

    runners = [
        (
            "Intron Sahara",
            "commercial API (African-accent optimized)",
            lambda: (
                intron_client.transcribe_telehealth(
                    audio_bytes, filename, language_code, output_language="en"
                )
                if agentic
                else intron_client.transcribe_plain(audio_bytes, filename, language_code)
            ),
        ),
        (
            "OpenAI Whisper",
            "open-source, local",
            lambda: asr_models.transcribe_whisper(wav_path, language_code),
        ),
        (
            "Meta MMS",
            "open-source, local (mms-1b-all)",
            lambda: asr_models.transcribe_mms(wav_path, language_code),
        ),
    ]

    results = []
    try:
        for name, kind, run in runners:
            entry = {"model": name, "kind": kind}
            try:
                started = time.monotonic()
                output = run()
                entry["transcript"] = output["transcript"]
                entry["latency_seconds"] = round(
                    output.get("latency_seconds", time.monotonic() - started), 2
                )
                entry["audio_duration_seconds"] = round(duration_seconds, 3)
                entry["rtf"] = round(entry["latency_seconds"] / duration_seconds, 4) if duration_seconds else None
                entry.update(_score(reference_transcript, output["transcript"]))
                entry["switch_point"] = _switch_point_score(
                    reference_transcript, output["transcript"], switch_points
                )
                if agent_reference:
                    entry["agentic"] = _agentic_score(
                        output, language_code, agent_reference
                    )
                entry["error"] = None
            except Exception as exc:  # keep other models running
                entry.update(
                    {
                        "transcript": "",
                        "latency_seconds": None,
                        "audio_duration_seconds": round(duration_seconds, 3),
                        "rtf": None,
                        "wer": None,
                        "cer": None,
                        "error": str(exc)[:300],
                    }
                )
            results.append(entry)
    finally:
        wav_path.unlink(missing_ok=True)

    scored = [r for r in results if r["wer"] is not None]
    best = min(scored, key=lambda r: r["wer"])["model"] if scored else None

    return {
        "reference_transcript": reference_transcript,
        "language_code": language_code,
        "results": results,
        "best_model": best,
        "switch_points": switch_points or [],
        "agentic": bool(agent_reference),
    }
