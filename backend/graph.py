"""Clinical reasoning graph — explainability layer for the Sahara triage flow.

Turns one turn of Intron Sahara output + the agentic triage result into a
graph *delta* (nodes + edges) that the frontend merges into a cumulative
per-consultation graph:

    patient --presents--> symptom / finding
    symptom / finding --suggests--> topic
    topic --consider--> condition
    red_flag --escalates--> topic
    topic --route_to--> department

Pure functions only; session accumulation lives in graph_store.py.
Stable node ids (``kind:normalized-label``) make repeats across turns dedup
naturally, so the same symptom mentioned twice stays a single node.
"""

import re

MAX_EXTRACTION_ITEMS = 8

# Node kinds, in clinical-semantic order. The frontend stylesheet keys off these.
KIND_PATIENT = "patient"
KIND_SYMPTOM = "symptom"
KIND_FINDING = "finding"
KIND_CONDITION = "condition"
KIND_RED_FLAG = "red_flag"
KIND_TOPIC = "topic"
KIND_DEPARTMENT = "department"

_SPLIT_RE = re.compile(r"[\n;•]|,\s*(?=[A-Z0-9])")
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def _split_extraction(text: str, cap: int = MAX_EXTRACTION_ITEMS) -> list[str]:
    """Best-effort itemize a Sahara string extraction (entities, differential
    diagnosis, ...) into short labels for graph nodes."""
    if not text:
        return []
    items = []
    for chunk in _SPLIT_RE.split(text):
        label = _BULLET_RE.sub("", chunk).strip().strip(".")
        if label:
            items.append(label)
    return items[:cap]


def _node_id(kind: str, label: str) -> str:
    normalized = re.sub(r"\s+", " ", label.strip().lower())
    return f"{kind}:{normalized}"


def _node(kind: str, label: str, turn: int) -> dict:
    return {"data": {"id": _node_id(kind, label), "label": label, "kind": kind, "turn": turn}}


def _edge(source_id: str, target_id: str, relation: str, turn: int) -> dict:
    return {
        "data": {
            "id": f"{source_id}|{relation}|{target_id}",
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "turn": turn,
        }
    }


def _red_flag_labels(triage_result: dict) -> list[str]:
    raw = triage_result.get("intake_card", {}).get("red_flags", "") or ""
    if not raw or raw == "None detected":
        return []
    return [flag.strip() for flag in raw.split(",") if flag.strip()]


def build_graph_delta(intron_result: dict, triage_result: dict, turn: int) -> dict:
    """Build the graph delta for one consultation turn.

    ``turn`` is 1-based (recording number within the session) and is stored on
    every element so the UI can highlight what the latest recording added.
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    patient = _node(KIND_PATIENT, "Patient", 1)  # root is stable across turns
    nodes.append(patient)
    patient_id = patient["data"]["id"]

    topic_labels = [triage_result.get("topic", "")]
    topic_labels += triage_result.get("other_possible_topics", []) or []
    topic_ids = []
    for label in topic_labels:
        if not label:
            continue
        node = _node(KIND_TOPIC, label, turn)
        nodes.append(node)
        topic_ids.append(node["data"]["id"])

    # Symptoms: keywords the rule-based triage actually matched on.
    for keyword in triage_result.get("matched_keywords", []) or []:
        node = _node(KIND_SYMPTOM, keyword, turn)
        nodes.append(node)
        edges.append(_edge(patient_id, node["data"]["id"], "presents", turn))
        if topic_ids:
            edges.append(_edge(node["data"]["id"], topic_ids[0], "suggests", turn))

    # Findings: structured entities extracted by Sahara.
    for item in _split_extraction(intron_result.get("entities", "")):
        node = _node(KIND_FINDING, item, turn)
        nodes.append(node)
        edges.append(_edge(patient_id, node["data"]["id"], "presents", turn))
        if topic_ids:
            edges.append(_edge(node["data"]["id"], topic_ids[0], "suggests", turn))

    # Possible conditions: Sahara differential diagnosis.
    for item in _split_extraction(intron_result.get("differential_diagnosis", "")):
        node = _node(KIND_CONDITION, item, turn)
        nodes.append(node)
        if topic_ids:
            edges.append(_edge(topic_ids[0], node["data"]["id"], "consider", turn))

    # Red flags: escalate the primary topic.
    for flag in _red_flag_labels(triage_result):
        node = _node(KIND_RED_FLAG, flag, turn)
        nodes.append(node)
        edges.append(_edge(patient_id, node["data"]["id"], "presents", turn))
        if topic_ids:
            edges.append(_edge(node["data"]["id"], topic_ids[0], "escalates", turn))

    department = triage_result.get("suggested_department", "")
    if department and topic_ids:
        node = _node(KIND_DEPARTMENT, department, turn)
        nodes.append(node)
        edges.append(_edge(topic_ids[0], node["data"]["id"], "route_to", turn))

    return {"nodes": nodes, "edges": edges}
