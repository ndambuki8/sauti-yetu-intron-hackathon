import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

INTRON_API_KEY = os.getenv("INTRON_API_KEY", "")
INTRON_BASE_URL = os.getenv("INTRON_BASE_URL", "https://infer.voice.intron.io")
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
MMS_MODEL_ID = os.getenv("MMS_MODEL_ID", "facebook/mms-1b-all")

FRONTEND_DIR = PROJECT_ROOT / "frontend"
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
