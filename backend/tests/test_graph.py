"""Tests for the clinical reasoning graph (Sahara-only) — no API key needed.

The Intron HTTP call is faked/monkeypatched throughout.
"""

import io
import sys
import types

from fastapi.testclient import TestClient

from backend import lid
from backend.app import app
from backend.asr_models import closed_set_lid
from backend.graph import _split_extraction, build_graph_delta
from backend.graph_store import SessionStore
from backend.extract import extract_patient_hints
from backend.triage import PatientContext, run_triage

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
    ctx = body["triage"]["patient_context"]
    assert ctx["age"] is None or isinstance(ctx["age"], (int, float))
    assert "sex" in ctx


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


# ---------- text LID + Auto language triage ----------

SWAHILI_TRANSCRIPT = (
    "Ninaumwa kichwa sana tangu asubuhi na siwezi kulala vizuri."
)


def test_lid_identifies_swahili():
    result = lid.identify(SWAHILI_TRANSCRIPT)
    assert result is not None
    assert result["language_code"] == "sw"
    assert result["confidence"] >= 0.55


def test_lid_identifies_english():
    result = lid.identify(
        "I have had a headache since this morning and I cannot sleep well."
    )
    assert result is not None
    assert result["language_code"] == "en"


def test_lid_identifies_amharic_from_fidel():
    result = lid.identify("ራስ ምታት አለብኝ ከጠዋት ጀምሮ መተኛት አልችልም።")
    assert result is not None
    assert result["language_code"] == "am"
    assert result["source"] == "script"


def test_lid_rejects_short_text():
    assert lid.identify("hi") is None


def test_store_last_patient_language():
    store = SessionStore()
    sid = store.create()
    assert store.last_patient_language(sid) is None
    store.append(sid, build_graph_delta(FAKE_INTRON_RESULT, _triage_result(), turn=1))
    store.record_turn(
        sid,
        detected_language="sw",
        transcript_patient=SWAHILI_TRANSCRIPT,
        transcript_doctor=SWAHILI_TRANSCRIPT,
        triage=_triage_result(),
        summary="headache",
    )
    assert store.last_patient_language(sid) == "sw"


def test_closed_set_lid_maps_ibo_and_ignores_unknown():
    picked = closed_set_lid({"ibo": 4.0, "som": 9.0, "eng": 1.0})
    assert picked is not None
    assert picked["language_code"] == "ig"
    assert picked["mms_code"] == "ibo"
    assert closed_set_lid({"som": 5.0, "ful": 3.0}) is None


def _audio_english(*_args, **_kwargs):
    return {"language_code": "en", "mms_code": "eng", "confidence": 0.91}


def test_auto_triage_trusts_text_lid_over_audio_english(monkeypatch):
    swahili_result = {**FAKE_INTRON_RESULT, "transcript": SWAHILI_TRANSCRIPT}
    monkeypatch.setattr(
        "backend.app.transcribe_telehealth",
        lambda *args, **kwargs: dict(swahili_result),
    )
    monkeypatch.setattr("backend.asr_models.detect_language", _audio_english)
    client = TestClient(app)
    res = client.post(
        "/api/triage",
        files={"audio": ("clip.webm", io.BytesIO(b"fake audio"), "audio/webm")},
        data={"language_code": "auto"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["detected_language"] == "sw"
    assert body["detection"]["audio"]["language_code"] == "en"
    assert body["detection"]["text"]["language_code"] == "sw"
    assert body["detection"]["final"] == "sw"


def test_auto_audio_lid_failure_uses_session_prior(monkeypatch):
    sahara_languages: list[str] = []

    def _capture_transcribe(audio_bytes, filename, language_code, output_language):
        sahara_languages.append(language_code)
        return {**FAKE_INTRON_RESULT, "transcript": SWAHILI_TRANSCRIPT}

    monkeypatch.setattr("backend.app.transcribe_telehealth", _capture_transcribe)
    monkeypatch.setattr("backend.asr_models.detect_language", _audio_english)
    client = TestClient(app)
    first = client.post(
        "/api/triage",
        files={"audio": ("clip.webm", io.BytesIO(b"fake audio"), "audio/webm")},
        data={"language_code": "auto"},
    )
    assert first.status_code == 200
    assert first.json()["detected_language"] == "sw"
    sid = first.json()["session_id"]

    def _audio_fails(*_args, **_kwargs):
        raise RuntimeError("mms-lid unavailable")

    monkeypatch.setattr("backend.asr_models.detect_language", _audio_fails)
    second = client.post(
        "/api/triage",
        files={"audio": ("clip.webm", io.BytesIO(b"fake audio"), "audio/webm")},
        data={"language_code": "auto", "session_id": sid},
    )
    assert second.status_code == 200
    assert sahara_languages[-1] == "sw"
    assert second.json()["detected_language"] == "sw"


# ---------- knowledge-base triage ----------

def test_chest_pain_emergency_only_when_over_50():
    young = run_triage(FAKE_INTRON_RESULT, "English", PatientContext(age=8))
    old = run_triage(FAKE_INTRON_RESULT, "English", PatientContext(age=55))
    young_ids = {d["id"] for d in young["matched_discriminators"]}
    old_ids = {d["id"] for d in old["matched_discriminators"]}
    assert "acute-chest-abdo-pain-over-50" not in young_ids
    assert "acute-chest-abdo-pain-over-50" in old_ids
    assert old["urgency"] == "EMERGENCY"


def test_vitals_hr_150_emergency_at_age_8_not_age_3():
    toddler = run_triage(FAKE_INTRON_RESULT, "English", PatientContext(age=3, hr=150))
    child = run_triage(FAKE_INTRON_RESULT, "English", PatientContext(age=8, hr=150))
    toddler_vitals = [d for d in toddler["matched_discriminators"] if d["id"].startswith("vital-")]
    child_vitals = [d for d in child["matched_discriminators"] if d["id"].startswith("vital-")]
    assert toddler_vitals == []
    assert child_vitals
    assert child["urgency"] == "EMERGENCY"


def test_differential_ranks_cited_conditions():
    result = run_triage(FAKE_INTRON_RESULT, "English", PatientContext(age=55))
    assert result["differential"]
    top = result["differential"][0]
    assert 0 < top["probability"] <= 1
    assert top["source"]["ref"]
    assert top["contributing"]


def test_extract_patient_hints_from_transcript():
    hints = extract_patient_hints("34-year-old woman, 28 weeks pregnant, chest pain")
    assert hints["age"] == 34
    assert hints["sex"] == "female"
    assert hints["pregnant"] is True


def test_triage_returns_extracted_patient_context(monkeypatch):
    spoken = {
        **FAKE_INTRON_RESULT,
        "transcript": "34-year-old woman with chest pain since morning",
        "summary": "34-year-old woman with chest pain since morning",
    }
    monkeypatch.setattr("backend.app.transcribe_telehealth", lambda *a, **k: dict(spoken))
    client = TestClient(app)
    res = _post_triage(client)
    assert res.status_code == 200
    ctx = res.json()["triage"]["patient_context"]
    assert ctx["age"] == 34
    assert ctx["sex"] == "female"
    assert "age" in res.json()["triage"]["auto_detected"]
