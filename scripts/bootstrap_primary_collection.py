"""Bootstrap helper: draft first-pass transcripts for primary_collection clips.

This script transcribes clips with Intron Sahara to produce a *draft* metadata
file that a human then reviews and corrects. The corrected, human-verified
transcripts in data/primary_collection/metadata.csv are the ground truth used by
generate_primary_report.py — that file is authoritative and must not be
regenerated blindly.

IMPORTANT: metadata.csv is now curated by hand (it includes hand-written ogg
WhatsApp references that this script does not generate — _collect_files() only
globs mp3 + m4a). To protect that work, this script REFUSES to overwrite an
existing metadata.csv and writes metadata.bootstrap_draft.csv instead, unless
--overwrite-metadata is explicitly passed.

The script produces:
  data/primary_collection/bootstrap_cache.json         — raw Sahara outputs, one per clip
  data/primary_collection/metadata.bootstrap_draft.csv — draft metadata (when metadata.csv exists)
  data/primary_collection/metadata.csv                 — only when the file is absent or --overwrite-metadata is passed

Usage (from project root, venv active, INTRON_API_KEY in .env):
    python -m scripts.bootstrap_primary_collection                       # draft only if metadata.csv missing
    python -m scripts.bootstrap_primary_collection --force               # re-transcribe even if cached
    python -m scripts.bootstrap_primary_collection --overwrite-metadata  # DANGER: rebuild metadata.csv from scratch
"""

import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import asr_models, intron_client  # noqa: E402

PRIMARY_DIR = Path("data/primary_collection")
CACHE_PATH  = PRIMARY_DIR / "bootstrap_cache.json"
META_PATH   = PRIMARY_DIR / "metadata.csv"

# ─── Clinical metadata known from filenames ──────────────────────────────────
# Keys are filename stems (without extension, lowercase).
M4A_KNOWN: dict[str, dict] = {
    "sample_sw_en_fever_and_headache": {
        "expected_topic":      "Fever / possible infection (malaria, typhoid, etc.)",
        "expected_urgency":    "URGENT",
        "expected_department": "General Outpatient / Internal Medicine",
        "expected_entities":   ["fever", "headache"],
        "switch_points":       [{"token_index": 5, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Fever & Infection",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_difficulty_breathing": {
        "expected_topic":      "Breathing difficulty",
        "expected_urgency":    "EMERGENCY",
        "expected_department": "Emergency / Resuscitation",
        "expected_entities":   ["difficulty breathing", "shortness of breath"],
        "switch_points":       [{"token_index": 4, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Respiratory Emergency",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_injury_ongoning_bleeding": {
        "expected_topic":      "Severe bleeding / major injury",
        "expected_urgency":    "EMERGENCY",
        "expected_department": "Emergency / Trauma",
        "expected_entities":   ["injury", "bleeding"],
        "switch_points":       [{"token_index": 4, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Trauma",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_pregancy_bleeding": {
        "expected_topic":      "Pregnancy / labour concern",
        "expected_urgency":    "URGENT",
        "expected_department": "Obstetrics & Gynaecology / Maternity",
        "expected_entities":   ["pregnancy", "bleeding"],
        "switch_points":       [{"token_index": 5, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Obstetrics",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_chest_discomfort": {
        "expected_topic":      "Chest pain / possible cardiac event",
        "expected_urgency":    "EMERGENCY",
        "expected_department": "Emergency / Resuscitation",
        "expected_entities":   ["chest pain", "chest discomfort"],
        "switch_points":       [{"token_index": 4, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Cardiac Emergency",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_adbominal_pain": {
        "expected_topic":      "Abdominal pain / gastrointestinal",
        "expected_urgency":    "URGENT",
        "expected_department": "General Outpatient / Surgery review",
        "expected_entities":   ["abdominal pain"],
        "switch_points":       [{"token_index": 5, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Abdominal & GI",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_diarrhoea_vomiting": {
        "expected_topic":      "Abdominal pain / gastrointestinal",
        "expected_urgency":    "URGENT",
        "expected_department": "General Outpatient / Surgery review",
        "expected_entities":   ["diarrhoea", "vomiting"],
        "switch_points":       [{"token_index": 5, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Abdominal & GI",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_persisent_cough": {
        "expected_topic":      "",
        "expected_urgency":    "ROUTINE",
        "expected_department": "General Outpatient",
        "expected_entities":   ["persistent cough", "cough"],
        "switch_points":       [{"token_index": 5, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Respiratory",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_mild_respiratory_symptoms": {
        "expected_topic":      "",
        "expected_urgency":    "ROUTINE",
        "expected_department": "General Outpatient",
        "expected_entities":   ["respiratory symptoms", "cough"],
        "switch_points":       [{"token_index": 5, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Respiratory",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_head_injury_uncertainity": {
        "expected_topic":      "Severe bleeding / major injury",
        "expected_urgency":    "EMERGENCY",
        "expected_department": "Emergency / Trauma",
        "expected_entities":   ["head injury"],
        "switch_points":       [{"token_index": 4, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Trauma",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_backpain_explicit_negatives": {
        "expected_topic":      "",
        "expected_urgency":    "ROUTINE",
        "expected_department": "General Outpatient",
        "expected_entities":   ["back pain"],
        "switch_points":       [{"token_index": 4, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Musculoskeletal",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_dental_pain_swelling": {
        "expected_topic":      "Skin / wound complaint",
        "expected_urgency":    "ROUTINE",
        "expected_department": "General Outpatient / Minor procedures",
        "expected_entities":   ["dental pain", "swelling"],
        "switch_points":       [{"token_index": 4, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Dental & Oral",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_diabetes_missed_food": {
        "expected_topic":      "Medication refill / chronic condition follow-up",
        "expected_urgency":    "ROUTINE",
        "expected_department": "Pharmacy / Chronic care clinic",
        "expected_entities":   ["diabetes", "medication", "blood sugar"],
        "switch_points":       [{"token_index": 5, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Chronic Disease",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_emotinal distress": {   # note: space in original filename
        "expected_topic":      "",
        "expected_urgency":    "URGENT",
        "expected_department": "General Outpatient",
        "expected_entities":   ["emotional distress", "anxiety"],
        "switch_points":       [{"token_index": 5, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Mental Health",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_eye_exposure": {
        "expected_topic":      "",
        "expected_urgency":    "URGENT",
        "expected_department": "General Outpatient",
        "expected_entities":   ["eye exposure", "eye"],
        "switch_points":       [{"token_index": 4, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Eye & ENT",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_medication-refill": {
        "expected_topic":      "Medication refill / chronic condition follow-up",
        "expected_urgency":    "ROUTINE",
        "expected_department": "Pharmacy / Chronic care clinic",
        "expected_entities":   ["medication refill", "prescription"],
        "switch_points":       [{"token_index": 5, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Chronic Disease",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_pain_urinating": {
        "expected_topic":      "",
        "expected_urgency":    "ROUTINE",
        "expected_department": "General Outpatient",
        "expected_entities":   ["pain urinating", "dysuria"],
        "switch_points":       [{"token_index": 4, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Urological",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_child_described": {
        "expected_topic":      "Child illness (paediatric)",
        "expected_urgency":    "URGENT",
        "expected_department": "Paediatrics",
        "expected_entities":   ["child", "paediatric"],
        "switch_points":       [{"token_index": 4, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Paediatrics",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_sudden_change_relative": {
        "expected_topic":      "Headache / neurological complaint",
        "expected_urgency":    "URGENT",
        "expected_department": "General Outpatient / Neurology review",
        "expected_entities":   ["sudden change", "confusion"],
        "switch_points":       [{"token_index": 4, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Neurological",
        "noise_condition":     "indoor quiet",
    },
    "sample_sw_en_symptoms_after_taking_meds": {
        "expected_topic":      "Medication refill / chronic condition follow-up",
        "expected_urgency":    "ROUTINE",
        "expected_department": "Pharmacy / Chronic care clinic",
        "expected_entities":   ["medication side effects", "symptoms after medication"],
        "switch_points":       [{"token_index": 5, "from_language": "sw", "to_language": "en"}],
        "clinical_category":   "Medication Side Effects",
        "noise_condition":     "indoor quiet",
    },
}


COLUMNS = [
    "filename", "recording_type", "language_pair", "language_code",
    "domain", "accent_country", "device_type", "noise_condition",
    "clinical_category", "reference_transcript",
    "switch_points", "expected_topic", "expected_urgency",
    "expected_department", "expected_slots", "expected_entities",
]


def _collect_files() -> list[Path]:
    mp3_files = sorted(PRIMARY_DIR.glob("*.mp3"), key=lambda p: (len(p.stem), p.stem))
    m4a_files = sorted(PRIMARY_DIR.glob("*.m4a"))
    return mp3_files + m4a_files


def _lookup_m4a(stem: str) -> dict:
    """Match a filename stem to M4A_KNOWN using lowercase comparison."""
    key = stem.lower()
    if key in M4A_KNOWN:
        return M4A_KNOWN[key]
    # Some filenames have capital letters in the middle: try case-insensitive match
    for k, v in M4A_KNOWN.items():
        if k.lower() == key:
            return v
    return {}


def _transcribe_one(path: Path, use_telehealth: bool) -> dict:
    """Call Sahara and return the parsed result dict."""
    audio_bytes = path.read_bytes()
    # prepare_for_intron converts .m4a → .wav so Intron accepts it
    safe_bytes, safe_name = asr_models.prepare_for_intron(audio_bytes, path.name)
    lang = "sw" if path.suffix == ".m4a" else "sw"  # all clips assumed Swahili-English

    if use_telehealth:
        return intron_client.transcribe_telehealth(safe_bytes, safe_name, lang, output_language="en")
    return intron_client.transcribe_plain(safe_bytes, safe_name, lang)


def run_bootstrap(force: bool = False) -> dict:
    """Transcribe every file with Sahara; return {filename: result} cache."""
    if CACHE_PATH.exists() and not force:
        print(f"Loading cached Sahara transcripts from {CACHE_PATH}")
        with open(CACHE_PATH, encoding="utf-8") as fh:
            return json.load(fh)

    files = _collect_files()
    print(f"\nBootstrap: transcribing {len(files)} clips with Intron Sahara...\n")
    cache: dict[str, dict] = {}

    for i, path in enumerate(files, 1):
        use_telehealth = path.suffix == ".m4a"
        mode = "telehealth" if use_telehealth else "plain"
        print(f"  [{i:2d}/{len(files)}] {path.name}  ({mode})", end=" ", flush=True)
        started = time.monotonic()
        try:
            result = _transcribe_one(path, use_telehealth=use_telehealth)
            elapsed = round(time.monotonic() - started, 1)
            transcript = (result.get("transcript") or "").strip()
            print(f"✓  {elapsed}s  \"{transcript[:60]}{'...' if len(transcript) > 60 else ''}\"")
            cache[path.name] = result
        except Exception as exc:
            elapsed = round(time.monotonic() - started, 1)
            print(f"ERR  {elapsed}s  {str(exc)[:80]}")
            cache[path.name] = {"transcript": "", "error": str(exc)[:200]}

    PRIMARY_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=2)
    print(f"\nSahara transcripts saved → {CACHE_PATH}\n")
    return cache


def build_metadata(cache: dict) -> None:
    """Write data/primary_collection/metadata.csv from the bootstrap cache."""
    files = _collect_files()
    rows: list[dict] = []

    for path in files:
        result = cache.get(path.name, {})
        transcript = (result.get("transcript") or "").strip()
        # Entities extracted by Sahara telehealth (m4a files only)
        sahara_entities_raw = (result.get("entities") or "").strip()

        is_m4a = path.suffix == ".m4a"
        stem = path.stem

        if is_m4a:
            known = _lookup_m4a(stem)
            lang_pair    = "Swahili-English"
            lang_code    = "sw"
            rec_type     = "naturalistic_health_complaint"
            accent       = "Kenya"
            device       = "smartphone (m4a)"
            category     = known.get("clinical_category", "Healthcare")
            noise_cond   = known.get("noise_condition", "indoor quiet")
            exp_topic    = known.get("expected_topic", "")
            exp_urgency  = known.get("expected_urgency", "")
            exp_dept     = known.get("expected_department", "")
            switch_pts   = known.get("switch_points", [])
            # Combine filename-derived entities with Sahara's extracted entities
            known_ents   = known.get("expected_entities", [])
            exp_entities = known_ents   # start with filename-derived
        else:
            lang_pair    = "Swahili-English"
            lang_code    = "sw"
            rec_type     = "synthetic_triage_phrase"
            accent       = "Kenya"
            device       = "laptop microphone (mp3)"
            category     = "Triage Phrase"
            noise_cond   = "studio quiet"
            exp_topic    = ""
            exp_urgency  = ""
            exp_dept     = ""
            switch_pts   = []
            exp_entities = []

        rows.append({
            "filename":             path.name,
            "recording_type":       rec_type,
            "language_pair":        lang_pair,
            "language_code":        lang_code,
            "domain":               "healthcare",
            "accent_country":       accent,
            "device_type":          device,
            "noise_condition":      noise_cond,
            "clinical_category":    category,
            "reference_transcript": transcript,
            "switch_points":        json.dumps(switch_pts),
            "expected_topic":       exp_topic,
            "expected_urgency":     exp_urgency,
            "expected_department":  exp_dept,
            "expected_slots":       "{}",
            "expected_entities":    json.dumps(exp_entities),
        })

    # SAFETY GUARD: metadata.csv is a curated, human-verified ground-truth file
    # (it contains hand-written ogg references and corrected transcripts that this
    # script does not produce). Overwriting it would destroy that work and drop the
    # ogg rows entirely, since _collect_files() only globs mp3 + m4a. So by default
    # we refuse to overwrite an existing metadata.csv and write a draft instead.
    out_path = META_PATH
    if META_PATH.exists() and "--overwrite-metadata" not in sys.argv:
        out_path = PRIMARY_DIR / "metadata.bootstrap_draft.csv"
        print(
            f"\nWARNING: {META_PATH.name} already exists and is treated as curated ground truth.\n"
            f"         Refusing to overwrite it. Writing a first-pass draft to "
            f"{out_path.name} instead.\n"
            f"         Pass --overwrite-metadata to force a full rebuild "
            f"(this DESTROYS hand-written references and drops all ogg rows).\n"
        )

    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    m4a_count = sum(1 for r in rows if r["recording_type"] != "synthetic_triage_phrase")
    mp3_count  = sum(1 for r in rows if r["recording_type"] == "synthetic_triage_phrase")
    annotated  = sum(1 for r in rows if r["expected_topic"])
    print(f"metadata written → {out_path}")
    print(f"  {len(rows)} clips total: {m4a_count} m4a (naturalistic), {mp3_count} mp3 (phrase)")
    print(f"  {annotated} clips with expected_topic annotation")
    if out_path != META_PATH:
        print(
            f"  NOTE: review {out_path.name} and merge any wanted rows into "
            f"{META_PATH.name} by hand — do not blindly replace it."
        )


def main():
    force = "--force" in sys.argv
    cache = run_bootstrap(force=force)
    build_metadata(cache)
    print("\nBootstrap complete. Run the full benchmark with:")
    print("  python -m scripts.generate_primary_report")
    print("  python -m scripts.generate_primary_report --agentic   (enables Sahara extraction)")


if __name__ == "__main__":
    main()
