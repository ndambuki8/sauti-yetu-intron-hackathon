"""Local open-source ASR wrappers used in the code-switch benchmark.

Two models, both key-free:
- OpenAI Whisper (multilingual, via the openai-whisper package)
- Meta MMS (facebook/mms-1b-all, via transformers)

Models are lazy-loaded on first use so the triage flow works even when these
heavy dependencies are not installed. Audio is normalized to 16 kHz mono WAV
with ffmpeg before inference (browser recordings arrive as webm/ogg).
"""

import subprocess
import tempfile
import time
from pathlib import Path

from .config import MMS_MODEL_ID, WHISPER_MODEL_SIZE

# Intron/ISO-639-1 code -> Whisper language name (None = auto-detect).
WHISPER_LANG = {
    "sw": "swahili",
    "ha": "hausa",
    "yo": "yoruba",
    "am": "amharic",
    "af": "afrikaans",
    "en": "english",
    # Not supported by Whisper's language set; let it auto-detect.
    "ig": None,
    "zu": None,
    "rw": None,
    "pcm": None,
    "lg": None,
    "wo": None,
}

# Intron code -> MMS ISO-639-3 adapter code.
MMS_LANG = {
    "sw": "swh",
    "ha": "hau",
    "yo": "yor",
    "ig": "ibo",
    "zu": "zul",
    "am": "amh",
    "rw": "kin",
    "pcm": "pcm",
    "af": "afr",
    "lg": "lug",
    "wo": "wol",
    "en": "eng",
}

_whisper_model = None
_mms_model = None
_mms_processor = None


def convert_to_wav_16k(audio_bytes: bytes, suffix: str = ".webm") -> Path:
    """Convert arbitrary input audio to 16 kHz mono WAV via ffmpeg."""
    src = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    src.write(audio_bytes)
    src.close()
    dst_path = Path(src.name).with_suffix(".16k.wav")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", src.name,
                "-ac", "1", "-ar", "16000", "-f", "wav", str(dst_path),
            ],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ffmpeg not found. Install it with: sudo apt install ffmpeg"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"ffmpeg failed to convert audio: {exc.stderr.decode()[:300]}"
        ) from exc
    finally:
        Path(src.name).unlink(missing_ok=True)
    return dst_path


def transcribe_whisper(wav_path: Path, language_code: str = "en") -> dict:
    global _whisper_model
    import whisper  # lazy import

    if _whisper_model is None:
        _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)

    start = time.monotonic()
    result = _whisper_model.transcribe(
        str(wav_path),
        language=WHISPER_LANG.get(language_code),
        fp16=False,
    )
    return {
        "transcript": (result.get("text") or "").strip(),
        "latency_seconds": time.monotonic() - start,
    }


def transcribe_mms(wav_path: Path, language_code: str = "en") -> dict:
    global _mms_model, _mms_processor
    import soundfile as sf
    import torch
    from transformers import AutoProcessor, Wav2Vec2ForCTC  # lazy import

    if _mms_model is None:
        _mms_processor = AutoProcessor.from_pretrained(MMS_MODEL_ID)
        _mms_model = Wav2Vec2ForCTC.from_pretrained(MMS_MODEL_ID)

    mms_lang = MMS_LANG.get(language_code, "eng")
    start = time.monotonic()
    _mms_processor.tokenizer.set_target_lang(mms_lang)
    _mms_model.load_adapter(mms_lang)

    audio, sample_rate = sf.read(wav_path, dtype="float32")
    inputs = _mms_processor(audio, sampling_rate=sample_rate, return_tensors="pt")
    with torch.no_grad():
        logits = _mms_model(**inputs).logits
    ids = torch.argmax(logits, dim=-1)[0]
    transcript = _mms_processor.decode(ids)
    return {
        "transcript": transcript.strip(),
        "latency_seconds": time.monotonic() - start,
    }
