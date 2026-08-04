"""Code-switch ASR benchmark: Intron Sahara vs Whisper vs Meta MMS.

For a given audio clip and human reference transcript, runs all three models
and reports WER, CER (via jiwer, with standard text normalization), and
wall-clock latency. Models that fail (e.g. missing deps, no API key) are
reported with their error instead of aborting the whole benchmark.
"""

from pathlib import Path

import jiwer

from . import asr_models, intron_client

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


def run_benchmark(
    audio_bytes: bytes,
    filename: str,
    reference_transcript: str,
    language_code: str = "en",
) -> dict:
    """Run all three models on one clip and score against the reference."""
    suffix = Path(filename).suffix or ".webm"
    wav_path = asr_models.convert_to_wav_16k(audio_bytes, suffix=suffix)

    runners = [
        (
            "Intron Sahara",
            "commercial API (African-accent optimized)",
            lambda: intron_client.transcribe_plain(audio_bytes, filename, language_code),
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
                output = run()
                entry["transcript"] = output["transcript"]
                entry["latency_seconds"] = round(output["latency_seconds"], 2)
                entry.update(_score(reference_transcript, output["transcript"]))
                entry["error"] = None
            except Exception as exc:  # keep other models running
                entry.update(
                    {
                        "transcript": "",
                        "latency_seconds": None,
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
    }
