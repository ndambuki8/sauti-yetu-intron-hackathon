"""Agentic triage layer.

Turns the Intron Sahara telehealth output (transcript + English extractions)
into an *action*: a triage decision the front desk can act on immediately —
topic, urgency level, department routing, an auto-filled intake card, and
clarifying questions for the nurse.

The clinical knowledge (topics, keywords, red flags, routing, urgency) is NOT
hard-coded here any more. It lives as reviewable, source-tagged data in
``knowledge/triage_kb.yaml`` and is loaded/validated by ``knowledge_base.py``.
This module is now just the deterministic reasoning engine over that data:
keyword evidence -> ranked topic -> urgency, with a red-flag safety net.

Deterministic on purpose: no extra API keys, reproducible, easy to demo and
to audit. An LLM can be layered in at the *normalization* step later without
touching this decision logic.
"""

import re
from dataclasses import dataclass

from .knowledge_base import (
    Condition,
    Discriminator,
    KnowledgeBase,
    Provenance,
    TopicRule,
    load_kb,
)

# Loaded and validated once, on import — a malformed KB fails fast here rather
# than silently mis-triaging at request time.
_KB: KnowledgeBase = load_kb()

# Kept for readability / any external reference; the source of truth is the KB.
URGENCY_EMERGENCY = _KB.most_acute_urgency


@dataclass
class PatientContext:
    """Known patient facts. Age/sex/pregnant gate conditional discriminators;
    the vitals gate the age-banded high-risk vital-sign checks. All optional:
    unknown fields never exclude a rule (safety-first)."""

    age: float | None = None
    sex: str | None = None  # "male" | "female" | None
    pregnant: bool | None = None
    hr: float | None = None       # heart rate, bpm
    rr: float | None = None       # respiratory rate, /min
    temp: float | None = None     # temperature, °C
    spo2: float | None = None     # oxygen saturation, %
    avpu: str | None = None       # A | V | P | U


def _fmt_num(value: float) -> str:
    return str(int(value)) if float(value) == int(value) else str(value)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _provenance_dict(source: Provenance, topic_id: str | None = None) -> dict:
    """Flatten a Provenance block into the JSON the API/graph carry, so every
    surfaced conclusion can be traced to its source and citation in the UI."""
    payload = {
        "ref": source.ref,
        "url": source.url,
        "evidence_level": source.evidence_level.value,
        "review_status": source.review_status.value,
        "mapped_scale": source.mapped_scale,
    }
    if topic_id is not None:
        payload["topic_id"] = topic_id
    return payload


def _match_discriminators(
    searchable: str, patient: PatientContext
) -> list[tuple[Discriminator, str]]:
    """Return (discriminator, first-matched-keyword) pairs for every acuity
    discriminator that (a) applies to this patient and (b) whose keywords
    appear in the text, most-acute category first."""
    urgency_rank = _KB.urgency_rank
    matches: list[tuple[Discriminator, str]] = []
    for disc in _KB.discriminators:
        if not disc.applies_to(patient.age, patient.sex, patient.pregnant):
            continue
        hit = next((kw for kw in disc.keywords if kw in searchable), None)
        if hit is not None:
            matches.append((disc, hit))
    matches.sort(key=lambda pair: urgency_rank[pair[0].category])
    return matches


def _differential(searchable: str, patient: PatientContext, limit: int = 5) -> list[dict]:
    """Rank candidate conditions by posterior probability (naive-Bayes odds
    update over the KB). Pure arithmetic, so it adds no latency. Only conditions
    with at least one present finding are surfaced, each with its cited
    contributing findings and likelihood ratios."""
    results: list[dict] = []
    for cond in _KB.conditions:
        if not cond.applies_to(patient.age, patient.sex, patient.pregnant):
            continue
        prior = min(max(cond.prior, 1e-4), 0.999)
        odds = prior / (1 - prior)
        contributing: list[dict] = []
        for finding in cond.findings:
            if finding.match in searchable:
                odds *= finding.lr
                contributing.append({"finding": finding.match, "lr": finding.lr})
        if not contributing:
            continue
        probability = odds / (1 + odds)
        results.append(
            {
                "id": cond.id,
                "label": cond.label,
                "probability": round(probability, 3),
                "prior": cond.prior,
                "department": cond.department,
                "contributing": contributing,
                "source": _provenance_dict(cond.source),
            }
        )
    results.sort(key=lambda c: c["probability"], reverse=True)
    return results[:limit]


def _evaluate_vitals(patient: PatientContext) -> list[dict]:
    """Turn any entered vital signs into cited, escalating signs using the
    KB's age-banded thresholds. Only readings that were actually provided are
    evaluated; a vital is never inferred from audio."""
    vs = _KB.vital_signs
    if vs is None:
        return []

    band = vs.band_for(patient.age)
    readings: dict[str, float | str | None] = {
        "heart_rate": patient.hr,
        "resp_rate": patient.rr,
        "temperature": patient.temp,
        "spo2": patient.spo2,
        "avpu": patient.avpu,
    }
    emergency = _KB.most_acute_urgency
    source_payload = _provenance_dict(vs.source)
    out: list[dict] = []

    for th in vs.thresholds:
        value = readings.get(th.id)
        if value is None or value == "":
            continue

        abnormal = False
        detail = ""
        if th.kind == "avpu":
            letter = str(value).strip().upper()
            if letter and letter != "A":
                abnormal = True
                detail = f"{letter} (not alert)"
        else:
            try:
                num = float(value)
            except (TypeError, ValueError):
                continue
            rng = th.bands.get(band) or th.bands.get("all")
            if rng is not None:
                unit = th.unit or ""
                if rng.high is not None and num > rng.high:
                    abnormal, detail = True, f"{_fmt_num(num)}{unit} (high)"
                elif rng.low is not None and num < rng.low:
                    abnormal, detail = True, f"{_fmt_num(num)}{unit} (low)"

        if abnormal:
            out.append(
                {
                    "id": f"vital-{th.id}",
                    "label": f"{th.label} {detail}",
                    "category": th.category,
                    "keyword": detail,
                    "source": source_payload,
                    "is_red_flag": th.category == emergency,
                }
            )
    return out


def run_triage(
    intron_result: dict,
    language_name: str,
    patient: PatientContext | None = None,
) -> dict:
    """Take the agentic action: decide topic, urgency, department, intake.

    Scans the English-language extractions (summary, entities, differential
    diagnosis) plus the transcript for topic keywords and red flags, ranking
    matched topics by acuity then by weight of evidence (number of hits).
    Age/sex-conditional discriminators are filtered by ``patient`` context.
    """
    patient = patient or PatientContext()
    searchable = _normalize(
        " ".join(
            [
                intron_result.get("transcript", ""),
                intron_result.get("summary", ""),
                intron_result.get("entities", ""),
                intron_result.get("differential_diagnosis", ""),
            ]
        )
    )

    urgency_rank = _KB.urgency_rank

    matched: list[tuple[TopicRule, list[str]]] = []
    for rule in _KB.topics:
        hits = [kw for kw in rule.keywords if kw in searchable]
        if hits:
            matched.append((rule, hits))

    # Most acute first; on an urgency tie, more keyword hits wins. Python's
    # sort is stable, so equal-key topics keep their authored KB order.
    matched.sort(key=lambda pair: (urgency_rank[pair[0].urgency], -len(pair[1])))

    if matched:
        primary_rule, primary_hits = matched[0]
        topic = primary_rule.topic
        department = primary_rule.department
        topic_urgency = primary_rule.urgency
        questions = list(primary_rule.questions)
        matched_keywords = primary_hits
        other_topics = [rule.topic for rule, _ in matched[1:3]]
        # Provenance of the decision: which KB entry, what evidence, what source.
        topic_source = _provenance_dict(primary_rule.source, primary_rule.id)
    else:
        topic = _KB.fallback.topic
        department = _KB.fallback.department
        topic_urgency = _KB.fallback.urgency
        questions = list(_KB.default_questions)
        matched_keywords = []
        other_topics = []
        # The fallback is a deliberate hand-off, not a sourced clinical claim.
        topic_source = None

    # --- Acuity derivation (WHO IITT discriminators) --------------------------
    # Urgency is DERIVED, not inherited: take the most acute of the topic's
    # urgency and any matched discriminator category. Discriminators can only
    # escalate (safety-first). Each match keeps the specific citation.
    discriminator_matches = _match_discriminators(searchable, patient)
    emergency_urgency = _KB.most_acute_urgency
    matched_discriminators = [
        {
            "id": disc.id,
            "label": disc.label,
            "category": disc.category,
            "keyword": keyword,
            "source": _provenance_dict(disc.source),
            # Emergency-category signs are the clinical "red flags" the graph
            # draws; flagged here so consumers don't re-derive rank logic.
            "is_red_flag": disc.category == emergency_urgency,
        }
        for disc, keyword in discriminator_matches
    ]
    # High-risk vital signs (only fire when a reading was entered) join the
    # same list, so text signs and vitals are ranked and cited identically.
    matched_discriminators.extend(_evaluate_vitals(patient))
    matched_discriminators.sort(key=lambda d: urgency_rank[d["category"]])

    urgency = topic_urgency
    acuity = None
    if matched_discriminators:
        top = matched_discriminators[0]  # most acute (sorted)
        if urgency_rank[top["category"]] < urgency_rank[urgency]:
            urgency = top["category"]
        # The acuity block explains the derived urgency: which sign drove it.
        acuity = {
            "category": top["category"],
            "discriminator": top["label"],
            "source": top["source"],
        }

    # Emergency-category signs are the clinical "red flags". Keep the
    # comma-separated intake-card field for backward compatibility (labels are
    # comma-free by KB convention).
    emergency_labels = [
        d["label"] for d in matched_discriminators if d["category"] == emergency_urgency
    ]

    if patient.age is not None:
        age_str = f"{int(patient.age)} yrs" if patient.age == int(patient.age) else f"{patient.age} yrs"
    else:
        age_str = ""
    patient_summary = " · ".join(
        part for part in [age_str, (patient.sex or "").capitalize()] if part
    )

    vitals_bits: list[str] = []
    if patient.hr is not None:
        vitals_bits.append(f"HR {_fmt_num(patient.hr)}")
    if patient.rr is not None:
        vitals_bits.append(f"RR {_fmt_num(patient.rr)}")
    if patient.temp is not None:
        vitals_bits.append(f"Temp {_fmt_num(patient.temp)}°C")
    if patient.spo2 is not None:
        vitals_bits.append(f"SpO2 {_fmt_num(patient.spo2)}%")
    if patient.avpu:
        vitals_bits.append(f"AVPU {patient.avpu.upper()}")

    intake_card = {
        "patient_language": language_name,
        "patient_summary": patient_summary,
        "vitals": " · ".join(vitals_bits),
        "presenting_complaint": intron_result.get("summary")
        or intron_result.get("transcript", "")[:300],
        "key_findings": intron_result.get("entities", ""),
        "possible_conditions": intron_result.get("differential_diagnosis", ""),
        "red_flags": ", ".join(emergency_labels) if emergency_labels else "None detected",
    }

    return {
        "topic": topic,
        "other_possible_topics": other_topics,
        "urgency": urgency,
        "suggested_department": department,
        "intake_card": intake_card,
        "clarifying_questions": questions,
        "matched_keywords": matched_keywords,
        "intron_suggestions": intron_result.get("suggestions", ""),
        # Explainability: source behind the primary topic, the derived acuity
        # (with the discriminator that drove it), and every matched sign.
        "topic_source": topic_source,
        "acuity": acuity,
        "matched_discriminators": matched_discriminators,
        # Probabilistic differential (ranked, cited). Ranking aid only; it never
        # overrides the deterministic acuity/red-flag path above.
        "differential": _differential(searchable, patient),
    }
