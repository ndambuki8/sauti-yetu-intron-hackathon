"""Reproducible code-switch and agentic benchmark harness.

The basic ``run_benchmark`` contract remains useful for the API endpoint. The
optional annotations add switch-point WER and downstream triage metrics, while
the ``agentic`` mode runs Sahara's telehealth extraction before the triage
layer. Model failures are isolated so one unavailable model does not discard a
clip.

Extended in v2 with:
- ``_add_gaussian_noise`` / ``_silence_metrics`` for Domain-3 robustness
- ``run_noise_benchmark`` to sweep models across SNR levels
- ``run_offline_simulation`` to model local-only (no API) operation
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

# ---------------------------------------------------------------------------
# Core scoring helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Standard three-model benchmark
# ---------------------------------------------------------------------------

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

    # Phone recordings (m4a/mp4/aac) must be converted to WAV before Intron
    # accepts them; prepare_for_intron is a no-op for already-compatible formats.
    safe_bytes, safe_name = asr_models.prepare_for_intron(audio_bytes, filename)

    runners = [
        (
            "Intron Sahara",
            "commercial API (African-accent optimized)",
            lambda: (
                intron_client.transcribe_telehealth(
                    safe_bytes, safe_name, language_code, output_language="en"
                )
                if agentic
                else intron_client.transcribe_plain(safe_bytes, safe_name, language_code)
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
                transcript = (output.get("transcript") or "").strip()
                entry["transcript"] = transcript
                entry["latency_seconds"] = round(
                    output.get("latency_seconds", time.monotonic() - started), 2
                )
                entry["audio_duration_seconds"] = round(duration_seconds, 3)
                entry["rtf"] = round(entry["latency_seconds"] / duration_seconds, 4) if duration_seconds else None
                entry.update(_score(reference_transcript, transcript))
                entry["switch_point"] = _switch_point_score(
                    reference_transcript, transcript, switch_points
                )
                if agent_reference:
                    entry["agentic"] = _agentic_score(
                        output, language_code, agent_reference
                    )
                entry["error"] = None
                entry["warning"] = "Model returned an empty transcript." if not transcript else None
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
                        "warning": None,
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


# ---------------------------------------------------------------------------
# Domain-3: Environmental robustness helpers
# ---------------------------------------------------------------------------

def _add_gaussian_noise(wav_path: Path, snr_db: float, seed: int = 42) -> Path:
    """Return a new temporary WAV file with additive Gaussian noise at ``snr_db``.

    The seed is fixed so every benchmark run is reproducible.  The noisy file
    is written alongside the source with a ``.snrXX.wav`` suffix and must be
    deleted by the caller.
    """
    try:
        import numpy as np  # available wherever torch/transformers are installed
    except ImportError as exc:
        raise RuntimeError("numpy is required for noise augmentation: pip install numpy") from exc

    with wave.open(str(wav_path), "rb") as wf:
        params = wf.getparams()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    sw = params.sampwidth
    if sw == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
        int_type, clip_lo, clip_hi = np.int16, -32768, 32767
    elif sw == 4:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float64)
        int_type, clip_lo, clip_hi = np.int32, -(2 ** 31), 2 ** 31 - 1
    else:  # 8-bit unsigned
        samples = np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0
        int_type, clip_lo, clip_hi = np.uint8, 0, 255

    signal_power = float(np.mean(samples ** 2))
    if signal_power == 0.0:
        return wav_path  # silent clip — return original

    noise_power = signal_power / (10.0 ** (snr_db / 10.0))
    rng = np.random.default_rng(seed=seed)
    noise = rng.normal(0.0, float(np.sqrt(noise_power)), size=samples.shape)
    noisy = np.clip(samples + noise, clip_lo, clip_hi)

    if sw == 1:
        out_bytes = (noisy + 128.0).astype(int_type).tobytes()
    else:
        out_bytes = noisy.astype(int_type).tobytes()

    noisy_path = wav_path.with_suffix(f".snr{int(snr_db)}.wav")
    with wave.open(str(noisy_path), "wb") as wf:
        wf.setparams(params)
        wf.writeframes(out_bytes)
    return noisy_path


def _silence_metrics(
    wav_path: Path,
    frame_ms: int = 20,
    silence_threshold_db: float = -40.0,
) -> dict:
    """Analyse silence and pause structure in a 16 kHz mono WAV.

    Returns:
        silence_ratio          – fraction of frames classified as silent
        pause_count            – number of distinct silent segments (≥1 frame)
        longest_pause_seconds  – duration of the longest continuous silent segment
    """
    try:
        import numpy as np
    except ImportError:
        return {"silence_ratio": None, "pause_count": None, "longest_pause_seconds": None}

    with wave.open(str(wav_path), "rb") as wf:
        frame_rate = wf.getframerate()
        n_frames = wf.getnframes()
        sw = wf.getsampwidth()
        raw = wf.readframes(n_frames)

    if sw == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
        ref_level = 32768.0
    elif sw == 4:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float64)
        ref_level = 2147483648.0
    else:
        samples = np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0
        ref_level = 128.0

    frame_samples = max(1, int(frame_rate * frame_ms / 1000))
    total_frames = len(samples) // frame_samples
    if total_frames == 0:
        return {"silence_ratio": None, "pause_count": None, "longest_pause_seconds": None}

    is_silence = []
    for i in range(total_frames):
        chunk = samples[i * frame_samples : (i + 1) * frame_samples]
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        db = 20.0 * (float(np.log10(max(rms, 1e-12))) - float(np.log10(ref_level)))
        is_silence.append(db < silence_threshold_db)

    silence_count = sum(is_silence)
    silence_ratio = round(silence_count / total_frames, 4)

    # Count contiguous silent runs
    pause_count = 0
    longest_run = 0
    current_run = 0
    for silent in is_silence:
        if silent:
            current_run += 1
            if current_run > longest_run:
                longest_run = current_run
        else:
            if current_run > 0:
                pause_count += 1
            current_run = 0
    if current_run > 0:
        pause_count += 1

    return {
        "silence_ratio": silence_ratio,
        "pause_count": pause_count,
        "longest_pause_seconds": round(longest_run * frame_ms / 1000.0, 3),
    }


def run_noise_benchmark(
    audio_bytes: bytes,
    filename: str,
    reference_transcript: str,
    language_code: str = "en",
    snr_levels: list[float] | None = None,
    skip_api: bool = False,
) -> dict:
    """Sweep all three models over multiple SNR levels (Domain 3).

    For each SNR level, Gaussian noise is added to the 16 kHz WAV before
    inference.  Results are keyed by SNR value so the caller can plot WER vs
    noise level per model.

    Args:
        skip_api: When True, Intron Sahara is skipped to avoid API costs.
                  This models a true *offline* scenario (local models only).
    """
    if snr_levels is None:
        snr_levels = [30.0, 20.0, 10.0, 5.0]

    suffix = Path(filename).suffix or ".webm"
    wav_path = asr_models.convert_to_wav_16k(audio_bytes, suffix=suffix)
    # Intron-safe copy of the original bytes (converts m4a → wav if needed).
    safe_bytes, safe_name = asr_models.prepare_for_intron(audio_bytes, filename)
    with wave.open(str(wav_path), "rb") as wf:
        duration_seconds = wf.getnframes() / wf.getframerate()

    silence = _silence_metrics(wav_path)
    noisy_paths: list[Path] = []
    levels: dict[str, list[dict]] = {}

    try:
        for snr in snr_levels:
            noisy_path = _add_gaussian_noise(wav_path, snr)
            noisy_paths.append(noisy_path)
            noisy_bytes = noisy_path.read_bytes()
            key = str(int(snr))

            def _make_runners(nb: bytes, np_: Path):  # capture by value
                runners = []
                if not skip_api:
                    runners.append(
                        ("Intron Sahara", lambda nb_=nb: intron_client.transcribe_plain(nb_, safe_name, language_code))
                    )
                runners += [
                    ("OpenAI Whisper", lambda np__=np_: asr_models.transcribe_whisper(np__, language_code)),
                    ("Meta MMS",       lambda np__=np_: asr_models.transcribe_mms(np__, language_code)),
                ]
                return runners

            level_results = []
            for model_name, run_fn in _make_runners(noisy_bytes, noisy_path):
                entry: dict = {"model": model_name, "snr_db": snr}
                try:
                    started = time.monotonic()
                    out = run_fn()
                    transcript = (out.get("transcript") or "").strip()
                    entry["transcript"] = transcript
                    latency = round(out.get("latency_seconds", time.monotonic() - started), 2)
                    entry["latency_seconds"] = latency
                    entry["rtf"] = round(latency / duration_seconds, 4) if duration_seconds else None
                    entry.update(_score(reference_transcript, transcript))
                    entry["error"] = None
                except Exception as exc:
                    entry.update({
                        "transcript": "", "latency_seconds": None, "rtf": None,
                        "wer": None, "cer": None, "error": str(exc)[:200],
                    })
                level_results.append(entry)
            levels[key] = level_results
    finally:
        wav_path.unlink(missing_ok=True)
        for p in noisy_paths:
            p.unlink(missing_ok=True)

    return {
        "snr_levels_db": snr_levels,
        "audio_duration_seconds": round(duration_seconds, 3),
        "silence_metrics": silence,
        "levels": levels,  # keyed by str(int(snr))
    }


def run_offline_simulation(
    audio_bytes: bytes,
    filename: str,
    reference_transcript: str,
    language_code: str = "en",
) -> dict:
    """Run only local (key-free) models to simulate true offline operation.

    Returns the same per-model result structure as ``run_benchmark`` but
    without Intron Sahara.  The caller should compare these numbers to the
    full run to quantify the offline penalty.
    """
    suffix = Path(filename).suffix or ".webm"
    wav_path = asr_models.convert_to_wav_16k(audio_bytes, suffix=suffix)
    with wave.open(str(wav_path), "rb") as wf:
        duration_seconds = wf.getnframes() / wf.getframerate()

    runners = [
        ("OpenAI Whisper", "open-source, local", lambda: asr_models.transcribe_whisper(wav_path, language_code)),
        ("Meta MMS",       "open-source, local (mms-1b-all)", lambda: asr_models.transcribe_mms(wav_path, language_code)),
    ]
    results = []
    try:
        for name, kind, run in runners:
            entry: dict = {"model": name, "kind": kind}
            try:
                started = time.monotonic()
                output = run()
                transcript = (output.get("transcript") or "").strip()
                entry["transcript"] = transcript
                entry["latency_seconds"] = round(
                    output.get("latency_seconds", time.monotonic() - started), 2
                )
                entry["audio_duration_seconds"] = round(duration_seconds, 3)
                entry["rtf"] = round(entry["latency_seconds"] / duration_seconds, 4) if duration_seconds else None
                entry.update(_score(reference_transcript, transcript))
                entry["error"] = None
            except Exception as exc:
                entry.update({
                    "transcript": "", "latency_seconds": None,
                    "audio_duration_seconds": round(duration_seconds, 3),
                    "rtf": None, "wer": None, "cer": None, "error": str(exc)[:300],
                })
            results.append(entry)
    finally:
        wav_path.unlink(missing_ok=True)

    scored = [r for r in results if r["wer"] is not None]
    best = min(scored, key=lambda r: r["wer"])["model"] if scored else None
    return {
        "reference_transcript": reference_transcript,
        "language_code": language_code,
        "mode": "offline_local_only",
        "results": results,
        "best_local_model": best,
    }
