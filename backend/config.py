import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

INTRON_API_KEY = os.getenv("INTRON_API_KEY", "")
INTRON_BASE_URL = os.getenv("INTRON_BASE_URL", "https://infer.voice.intron.io")
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
MMS_MODEL_ID = os.getenv("MMS_MODEL_ID", "facebook/mms-1b-all")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

FRONTEND_DIR = PROJECT_ROOT / "frontend"
APP_DIR = PROJECT_ROOT / "app"
SAMPLES_DIR = PROJECT_ROOT / "data" / "samples"

# Patient languages offered in the UI. Intron code -> display name.
# All are code-switch capable pairs per the Sahara supported-languages docs.
SUPPORTED_LANGUAGES = {
    "sw": "Swahili-English",
    "ha": "Hausa-English",
    "yo": "Yoruba-English",
    "ig": "Igbo-English",
    "zu": "Zulu-English",
    "am": "Amharic-English",
    "rw": "Kinyarwanda-English-French",
    "pcm": "Pidgin-English",
    "af": "Afrikaans-English",
    "lg": "Luganda-English",
    "wo": "Wolof-French",
    "en": "English",
}

# Doctor-facing UI / translation targets. English and French first.
DOCTOR_LANGUAGES = {
    "en": "English",
    "fr": "French",
    "sw": "Swahili",
    "ha": "Hausa",
    "yo": "Yoruba",
    "ig": "Igbo",
    "am": "Amharic",
    "rw": "Kinyarwanda",
    "pcm": "Pidgin",
    "af": "Afrikaans",
    "lg": "Luganda",
    "wo": "Wolof",
}

# Sahara extraction output languages we will request directly.
SAHARA_OUTPUT_LANGUAGES = {"en", "fr"}
