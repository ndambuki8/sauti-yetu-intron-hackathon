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


# Phone recordings (Expo / iOS / Android) that Intron often cannot decode
# as uploaded; convert to 16 kHz WAV first.
_PHONE_SUFFIXES = {".m4a", ".mp4", ".3gp", ".caf", ".aac", ".m4b"}


def prepare_for_intron(audio_bytes: bytes, filename: str) -> tuple[bytes, str]:
    """Return (bytes, filename) Intron is likely to accept."""
    suffix = Path(filename).suffix.lower() or ".bin"
    if suffix not in _PHONE_SUFFIXES:
        return audio_bytes, filename
    wav_path = convert_to_wav_16k(audio_bytes, suffix=suffix)
    try:
        return wav_path.read_bytes(), str(Path(filename).with_suffix(".wav").name)
    finally:
        wav_path.unlink(missing_ok=True)


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


# Whisper detect_language ISO codes we can map back to an Intron/app code.
WHISPER_DETECT_TO_APP = {
    "en": "en",
    "sw": "sw",
    "ha": "ha",
    "yo": "yo",
    "ig": "ig",
    "zu": "zu",
    "am": "am",
    "af": "af",
    "fr": "fr",
    "rw": "rw",
    "lg": "lg",
    "wo": "wo",
}


def detect_language(audio_bytes: bytes, filename: str = "recording.webm") -> dict:
    """Detect spoken language with Whisper. Returns app language code.

    {"language_code": str, "whisper_code": str, "confidence": float}
    Falls back to English if detection fails or the language is unknown.
    """
    global _whisper_model
    import whisper  # lazy import

    if _whisper_model is None:
        _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)

    suffix = Path(filename).suffix or ".webm"
    wav_path = convert_to_wav_16k(audio_bytes, suffix=suffix)
    try:
        audio = whisper.load_audio(str(wav_path))
        audio = whisper.pad_or_trim(audio)
        mel = whisper.log_mel_spectrogram(audio).to(_whisper_model.device)
        _, probs = _whisper_model.detect_language(mel)
        whisper_code = max(probs, key=probs.get)
        confidence = float(probs[whisper_code])
        app_code = WHISPER_DETECT_TO_APP.get(whisper_code, "en")
        return {
            "language_code": app_code,
            "whisper_code": whisper_code,
            "confidence": round(confidence, 3),
        }
    finally:
        wav_path.unlink(missing_ok=True)
