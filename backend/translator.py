"""English -> patient-language translation using a local NLLB-200 model.

Used before TTS so the health worker can type in English and the patient
hears (and reads) the reply in their own language. Lazy-loaded and key-free,
consistent with the local Whisper/MMS benchmark stack.
"""

import os

NLLB_MODEL_ID = os.getenv("NLLB_MODEL_ID", "facebook/nllb-200-distilled-600M")

# App language code -> FLORES-200 code used by NLLB.
FLORES_MAP = {
    "sw": "swh_Latn",
    "ha": "hau_Latn",
    "yo": "yor_Latn",
    "ig": "ibo_Latn",
    "zu": "zul_Latn",
    "am": "amh_Ethi",
    "rw": "kin_Latn",
    "lg": "lug_Latn",
    "wo": "wol_Latn",
    "af": "afr_Latn",
}

# Languages where the English text is passed through untranslated:
# - en: nothing to translate
# - pcm: Nigerian Pidgin is not in NLLB-200; it is English-lexified and the
#   Pidgin TTS voice renders plain English text naturally.
PASSTHROUGH = {"en", "pcm"}

_tokenizer = None
_model = None


def _load():
    global _tokenizer, _model
    if _model is None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # lazy import

        _tokenizer = AutoTokenizer.from_pretrained(NLLB_MODEL_ID)
        _model = AutoModelForSeq2SeqLM.from_pretrained(NLLB_MODEL_ID)
    return _tokenizer, _model


def translate(text: str, target_code: str) -> dict:
    """Translate English text to the target language.

    Returns {"translated_text": str, "was_translated": bool}.
    """
    text = text.strip()
    if not text:
        return {"translated_text": "", "was_translated": False}

    if target_code in PASSTHROUGH:
        return {"translated_text": text, "was_translated": False}

    flores_target = FLORES_MAP.get(target_code)
    if not flores_target:
        return {"translated_text": text, "was_translated": False}

    tokenizer, model = _load()
    tokenizer.src_lang = "eng_Latn"
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    output_ids = model.generate(
        **inputs,
        forced_bos_token_id=tokenizer.convert_tokens_to_ids(flores_target),
        max_length=512,
    )
    translated = tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0]
    return {"translated_text": translated, "was_translated": True}
