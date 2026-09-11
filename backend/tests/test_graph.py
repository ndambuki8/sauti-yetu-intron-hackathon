"""Tests for the clinical reasoning graph (Sahara-only) — no API key needed.

The Intron HTTP call is faked/monkeypatched throughout.
"""

import io
import sys
import types

from fastapi.testclient import TestClient

from backend.app import app
from backend.graph import _split_extraction, build_graph_delta
from backend.graph_store import SessionStore
from backend.triage import run_triage

FAKE_INTRON_RESULT = {
    "transcript": "Naumwa kifua, chest pain since morning, I feel dizzy",
    "summary": "Patient reports chest pain and dizziness since morning.",
    "entities": "Chest pain; Dizziness; Onset this morning",
    "differential_diagnosis": "1. Angina\n2. Musculoskeletal pain\n3. Anxiety attack",
    "suggestions": "ECG, troponin, monitor vitals",
    "followup_instructions": "Review in 24 hours",
    "duration_seconds": 42.0,
}


def _triage_result():
    return run_triage(FAKE_INTRON_RESULT, "Swahili-English")


# ---------- graph.build_graph_delta ----------

def test_split_extraction_handles_bullets_and_delimiters():
    text = "1. Angina\n2. Musculoskeletal pain; Anxiety attack"
    assert _split_extraction(text) == ["Angina", "Musculoskeletal pain", "Anxiety attack"]
    assert _split_extraction("") == []
    assert _split_extraction(None) == []


def test_delta_contains_expected_kinds_and_edges():
    delta = build_graph_delta(FAKE_INTRON_RESULT, _triage_result(), turn=1)
    kinds = {n["data"]["kind"] for n in delta["nodes"]}
    assert {"patient", "symptom", "finding", "condition", "red_flag", "topic", "department"} <= kinds

    relations = {(e["data"]["relation"]) for e in delta["edges"]}
    assert {"presents", "suggests", "consider", "escalates", "route_to"} <= relations

    # Chest pain is both a matched keyword and a red flag phrase.
    labels = {n["data"]["label"] for n in delta["nodes"]}
    assert "chest pain" in labels


def test_node_ids_are_stable_across_turns():
    delta1 = build_graph_delta(FAKE_INTRON_RESULT, _triage_result(), turn=1)
    delta2 = build_graph_delta(FAKE_INTRON_RESULT, _triage_result(), turn=2)
    ids1 = {n["data"]["id"] for n in delta1["nodes"]}
    ids2 = {n["data"]["id"] for n in delta2["nodes"]}
    assert ids1 == ids2  # same content, different turn -> same ids (dedup key)


def test_delta_robust_to_empty_extractions():
    empty = {key: "" for key in FAKE_INTRON_RESULT}
    triage_result = run_triage(empty, "English")
    delta = build_graph_delta(empty, triage_result, turn=1)
    # Always at least the patient, a topic and a department.
    kinds = {n["data"]["kind"] for n in delta["nodes"]}
    assert {"patient", "topic", "department"} <= kinds


# ---------- graph_store.SessionStore ----------

def test_store_dedups_and_keeps_first_seen_turn():
    store = SessionStore()
    sid = store.create()
    store.append(sid, build_graph_delta(FAKE_INTRON_RESULT, _triage_result(), turn=1))
    full = store.append(sid, build_graph_delta(FAKE_INTRON_RESULT, _triage_result(), turn=2))

    node_ids = [n["data"]["id"] for n in full["nodes"]]
    assert len(node_ids) == len(set(node_ids))  # no duplicates
    # Repeated content keeps turn 1, not turn 2.
    symptom = next(n for n in full["nodes"] if n["data"]["kind"] == "symptom")
    assert symptom["data"]["turn"] == 1
    assert full["turns"] == 2


def test_store_delete():
    store = SessionStore()
    sid = store.create()
    assert store.delete(sid) is True
    assert store.delete(sid) is False


# ---------- app endpoints (Intron call monkeypatched) ----------

def _fake_transcribe(audio_bytes, filename, language_code, output_language):
    return dict(FAKE_INTRON_RESULT)


def _post_triage(client, session_id=None):
    files = {"audio": ("clip.webm", io.BytesIO(b"fake audio"), "audio/webm")}
    data = {"language_code": "sw"}
    if session_id:
        data["session_id"] = session_id
    return client.post("/api/triage", files=files, data=data)


def test_triage_returns_graph_and_accumulates(monkeypatch):
    monkeypatch.setattr("backend.app.transcribe_telehealth", _fake_transcribe)
    client = TestClient(app)

    res1 = _post_triage(client)
    assert res1.status_code == 200
    body1 = res1.json()
    assert body1["session_id"]
    assert body1["graph"]["turns"] == 1
    assert body1["graph"]["nodes"] and body1["graph"]["edges"]

    res2 = _post_triage(client, session_id=body1["session_id"])
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["session_id"] == body1["session_id"]
    assert body2["graph"]["turns"] == 2
    # Same recording twice -> no duplicate nodes.
    assert len(body2["graph"]["nodes"]) == len(body1["graph"]["nodes"])


def test_triage_with_unknown_session_starts_fresh(monkeypatch):
    monkeypatch.setattr("backend.app.transcribe_telehealth", _fake_transcribe)
    client = TestClient(app)
    res = _post_triage(client, session_id="does-not-exist")
    assert res.status_code == 200
    assert res.json()["session_id"] != "does-not-exist"


def test_session_create_and_delete():
    client = TestClient(app)
    body = client.post("/api/session").json()
    sid = body["session_id"]
    assert sid
    assert body["doctor_language"] == "en"
    assert client.delete(f"/api/session/{sid}").status_code == 204
    assert client.delete(f"/api/session/{sid}").status_code == 404


def test_triage_returns_doctor_transcript(monkeypatch):
    monkeypatch.setattr("backend.app.transcribe_telehealth", _fake_transcribe)
    client = TestClient(app)
    res = _post_triage(client)
    assert res.status_code == 200
    body = res.json()
    assert body["transcript_patient"]
    assert body["transcript_doctor"]
    assert body["detected_language"] == "sw"
    assert "artifacts" in body


def test_command_persists_artifact(monkeypatch):
    monkeypatch.setattr("backend.app.transcribe_telehealth", _fake_transcribe)

    def _fake_run(command_text, full_session):
        return {
            "intent": "flowchart",
            "title": "Probable conditions",
            "body": "flowchart TD\n  A[Chest pain] --> B[Angina]",
            "notes": "Hints only",
            "kind": "flowchart",
        }

    monkeypatch.setattr("backend.agent.run_command", _fake_run)
    client = TestClient(app)
    sid = _post_triage(client).json()["session_id"]
    res = client.post("/api/command", data={"session_id": sid, "text": "prepare a flowchart"})
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "flowchart"
    assert body["artifact"]["body"].startswith("flowchart")
    assert len(body["artifacts"]) == 1


def test_benchmark_has_no_graph(monkeypatch):
    """The graph is Sahara-triage-only; benchmark must not expose one."""
    fake_benchmark = types.ModuleType("backend.benchmark")
    fake_benchmark.run_benchmark = lambda *args, **kwargs: {"results": [], "best_model": None}
    monkeypatch.setitem(sys.modules, "backend.benchmark", fake_benchmark)
    client = TestClient(app)
    res = client.post(
        "/api/benchmark",
        files={"audio": ("clip.webm", io.BytesIO(b"fake audio"), "audio/webm")},
        data={"reference_transcript": "hello world", "language_code": "en"},
    )
    assert res.status_code == 200
    assert "graph" not in res.json()
