"""Rule-based patient-context extraction from the conversation.

Pulls age, sex, and pregnancy hints out of the transcript / English summary so
the clinician does not have to type what the patient already said. This is
deterministic (regex, no model, no API key) and testable, and it feeds the
same triage engine.

Design principle: extraction only ever SUGGESTS. Explicit clinician input
always wins; extracted values fill blanks and are flagged as auto-detected so
they can be confirmed. We never override something the clinician entered.
"""

import re

# "34 years", "34-year-old", "aged 34", "34 yo", "34yrs"
_AGE_YEARS = re.compile(
    r"\b(\d{1,3})\s*(?:-|\s)?\s*(?:years?|yrs?|yo|year[-\s]?old)\b", re.IGNORECASE
)
_AGE_AGED = re.compile(r"\baged\s+(\d{1,3})\b", re.IGNORECASE)
_AGE_MONTHS = re.compile(r"\b(\d{1,2})\s*(?:-|\s)?\s*months?\s*(?:old)?\b", re.IGNORECASE)
_AGE_WEEKS = re.compile(r"\b(\d{1,2})\s*(?:-|\s)?\s*weeks?\s*old\b", re.IGNORECASE)
_AGE_DAYS = re.compile(r"\b(\d{1,2})\s*(?:-|\s)?\s*days?\s*old\b", re.IGNORECASE)

# Pregnancy comes before generic sex terms (it implies female).
_PREGNANT = re.compile(
    r"\b(pregnant|pregnancy|antenatal|weeks pregnant|expecting a baby|in labour|in labor)\b",
    re.IGNORECASE,
)

_FEMALE = re.compile(
    r"\b(female|woman|women|girl|lady|mother|she|her|mrs|madam)\b", re.IGNORECASE
)
_MALE = re.compile(r"\b(male|man|boy|gentleman|mr|he|him|his)\b", re.IGNORECASE)


def _extract_age(text: str) -> float | None:
    """Return age in YEARS. Recognises months/weeks/days for infants."""
    m = _AGE_YEARS.search(text) or _AGE_AGED.search(text)
    if m:
        years = int(m.group(1))
        if 0 <= years <= 120:
            return float(years)
    m = _AGE_MONTHS.search(text)
    if m:
        return round(int(m.group(1)) / 12.0, 3)
    m = _AGE_WEEKS.search(text)
    if m:
        return round(int(m.group(1)) * 7 / 365.0, 4)
    m = _AGE_DAYS.search(text)
    if m:
        return round(int(m.group(1)) / 365.0, 4)
    return None


def _extract_sex(text: str, pregnant: bool) -> str | None:
    if pregnant:
        return "female"
    # Prefer explicit gender nouns over weak pronouns by scoring occurrences.
    female = len(_FEMALE.findall(text))
    male = len(_MALE.findall(text))
    if female > male:
        return "female"
    if male > female:
        return "male"
    return None


def extract_patient_hints(*texts: str) -> dict:
    """Best-effort {age, sex, pregnant} from the conversation text.

    Values are hints only; any of them may be None when not confidently found.
    """
    blob = " ".join(t for t in texts if t)
    pregnant = bool(_PREGNANT.search(blob))
    return {
        "age": _extract_age(blob),
        "sex": _extract_sex(blob, pregnant),
        "pregnant": True if pregnant else None,
    }
