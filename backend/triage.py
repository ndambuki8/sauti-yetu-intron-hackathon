"""Agentic triage layer.

Turns the Intron Sahara telehealth output (transcript + English extractions)
into an *action*: a triage decision the front desk can act on immediately —
topic, urgency level, department routing, an auto-filled intake card, and
clarifying questions for the nurse.

Rule-based on purpose: no extra API keys needed, deterministic, easy to demo.
An LLM can be swapped in later behind the same `run_triage` signature.
"""

import re
from dataclasses import dataclass, field

URGENCY_EMERGENCY = "EMERGENCY"
URGENCY_URGENT = "URGENT"
URGENCY_ROUTINE = "ROUTINE"


@dataclass
class TopicRule:
    topic: str
    department: str
    urgency: str
    keywords: list[str]
    questions: list[str] = field(default_factory=list)


# Ordered by severity: first match group wins on urgency ties.
TOPIC_RULES: list[TopicRule] = [
    TopicRule(
        topic="Chest pain / possible cardiac event",
        department="Emergency / Resuscitation",
        urgency=URGENCY_EMERGENCY,
        keywords=[
            "chest pain", "chest tightness", "heart attack", "palpitations",
            "crushing pain", "pain radiating", "left arm pain",
        ],
        questions=[
            "When did the chest pain start and is it constant?",
            "Does the pain spread to the arm, jaw, or back?",
            "Any history of heart disease or hypertension?",
        ],
    ),
    TopicRule(
        topic="Breathing difficulty",
        department="Emergency / Resuscitation",
        urgency=URGENCY_EMERGENCY,
        keywords=[
            "can't breathe", "cannot breathe", "difficulty breathing",
            "shortness of breath", "short of breath", "choking", "wheezing",
            "asthma attack", "gasping",
        ],
        questions=[
            "Did the breathing difficulty start suddenly or gradually?",
            "Any known asthma, allergies, or recent choking?",
            "Are the lips or fingertips turning blue?",
        ],
    ),
    TopicRule(
        topic="Severe bleeding / major injury",
        department="Emergency / Trauma",
        urgency=URGENCY_EMERGENCY,
        keywords=[
            "bleeding heavily", "severe bleeding", "lost a lot of blood",
            "deep cut", "stab", "gunshot", "accident", "fracture", "broken bone",
            "head injury", "unconscious", "fainted", "collapsed", "seizure",
            "convulsion",
        ],
        questions=[
            "How did the injury happen and when?",
            "Has the patient lost consciousness at any point?",
            "Is the bleeding controlled with pressure?",
        ],
    ),
    TopicRule(
        topic="Pregnancy / labour concern",
        department="Obstetrics & Gynaecology / Maternity",
        urgency=URGENCY_URGENT,
        keywords=[
            "pregnant", "pregnancy", "labour", "labor", "contractions",
            "water broke", "waters broke", "miscarriage", "baby is coming",
            "antenatal",
        ],
        questions=[
            "How many weeks pregnant is the patient?",
            "Any bleeding, fluid loss, or reduced baby movement?",
            "How far apart are the contractions?",
        ],
    ),
    TopicRule(
        topic="Fever / possible infection (malaria, typhoid, etc.)",
        department="General Outpatient / Internal Medicine",
        urgency=URGENCY_URGENT,
        keywords=[
            "fever", "high temperature", "malaria", "typhoid", "chills",
            "shivering", "sweating at night", "body is hot", "hot body",
        ],
        questions=[
            "How many days has the fever lasted?",
            "Any recent travel or mosquito exposure?",
            "Is there vomiting, rash, or neck stiffness with the fever?",
        ],
    ),
    TopicRule(
        topic="Abdominal pain / gastrointestinal",
        department="General Outpatient / Surgery review",
        urgency=URGENCY_URGENT,
        keywords=[
            "stomach pain", "abdominal pain", "stomach ache", "belly pain",
            "vomiting", "diarrhea", "diarrhoea", "nausea", "constipation",
            "blood in stool",
        ],
        questions=[
            "Where exactly is the pain and how severe (1-10)?",
            "Any vomiting or diarrhoea, and for how long?",
            "When did the patient last eat or drink?",
        ],
    ),
    TopicRule(
        topic="Child illness (paediatric)",
        department="Paediatrics",
        urgency=URGENCY_URGENT,
        keywords=[
            "my baby", "my child", "the baby", "infant", "toddler",
            "child is sick", "not feeding", "child has",
        ],
        questions=[
            "How old is the child?",
            "Is the child feeding, drinking, and passing urine normally?",
            "Any fever, rash, or fast breathing?",
        ],
    ),
    TopicRule(
        topic="Headache / neurological complaint",
        department="General Outpatient / Neurology review",
        urgency=URGENCY_URGENT,
        keywords=[
            "headache", "migraine", "dizzy", "dizziness", "blurred vision",
            "numbness", "weakness on one side", "confusion",
        ],
        questions=[
            "Is this the worst headache the patient has ever had?",
            "Any vision changes, vomiting, or neck stiffness?",
            "Did the symptoms come on suddenly?",
        ],
    ),
    TopicRule(
        topic="Skin / wound complaint",
        department="General Outpatient / Minor procedures",
        urgency=URGENCY_ROUTINE,
        keywords=[
            "rash", "itching", "skin", "wound", "swelling", "boil", "burn",
            "insect bite", "dog bite", "snake bite",
        ],
        questions=[
            "How long has the skin problem been present?",
            "Is it spreading, painful, or discharging?",
            "Any animal or insect bite involved?",
        ],
    ),
    TopicRule(
        topic="Medication refill / chronic condition follow-up",
        department="Pharmacy / Chronic care clinic",
        urgency=URGENCY_ROUTINE,
        keywords=[
            "medication", "medicine finished", "refill", "prescription",
            "diabetes", "hypertension", "blood pressure", "hiv", "arv",
            "clinic appointment", "follow up", "follow-up",
        ],
        questions=[
            "Which medication does the patient take and at what dose?",
            "When was the last clinic review?",
            "Any new symptoms since the last visit?",
        ],
    ),
]

# Red-flag phrases that escalate any topic to EMERGENCY.
RED_FLAGS = [
    "unconscious", "not breathing", "severe bleeding", "bleeding heavily",
    "seizure", "convulsion", "collapsed", "chest pain", "can't breathe",
    "cannot breathe", "difficulty breathing", "poison", "overdose",
    "suicide", "snake bite", "gunshot", "stab",
]

DEFAULT_QUESTIONS = [
    "When did the symptoms start?",
    "Has the patient taken any medication for this already?",
    "Any known allergies or chronic conditions?",
]

_URGENCY_RANK = {URGENCY_EMERGENCY: 0, URGENCY_URGENT: 1, URGENCY_ROUTINE: 2}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def run_triage(intron_result: dict, language_name: str) -> dict:
    """Take the agentic action: decide topic, urgency, department, intake.

    Scans the English-language extractions (summary, entities, differential
    diagnosis) plus the transcript for topic keywords and red flags.
    """
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

    matched: list[tuple[TopicRule, list[str]]] = []
    for rule in TOPIC_RULES:
        hits = [kw for kw in rule.keywords if kw in searchable]
        if hits:
            matched.append((rule, hits))

    matched.sort(key=lambda pair: (_URGENCY_RANK[pair[0].urgency], -len(pair[1])))

    red_flag_hits = [flag for flag in RED_FLAGS if flag in searchable]

    if matched:
        primary_rule, primary_hits = matched[0]
        topic = primary_rule.topic
        department = primary_rule.department
        urgency = primary_rule.urgency
        questions = list(primary_rule.questions)
        matched_keywords = primary_hits
        other_topics = [rule.topic for rule, _ in matched[1:3]]
    else:
        topic = "Undetermined — needs nurse assessment"
        department = "General Outpatient / Triage desk"
        urgency = URGENCY_ROUTINE
        questions = list(DEFAULT_QUESTIONS)
        matched_keywords = []
        other_topics = []

    if red_flag_hits:
        urgency = URGENCY_EMERGENCY

    intake_card = {
        "patient_language": language_name,
        "presenting_complaint": intron_result.get("summary")
        or intron_result.get("transcript", "")[:300],
        "key_findings": intron_result.get("entities", ""),
        "possible_conditions": intron_result.get("differential_diagnosis", ""),
        "red_flags": ", ".join(red_flag_hits) if red_flag_hits else "None detected",
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
    }
