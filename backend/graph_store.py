"""In-memory session store for cumulative consultation graphs.

One session = one consultation. Each triage call appends a graph delta
(see graph.py); the store dedups by element id and keeps the first-seen
turn number, so the cumulative graph stays stable as it grows.

Also holds doctor/patient language settings, turn history for the
voice-command agent, and generated artifacts (reports, flowcharts).

Hackathon scope: process-local, non-persistent, no TTL. A restart clears
all consultations — documented in the README.
"""

import threading
import uuid
from datetime import datetime, timezone


class UnknownSessionError(KeyError):
    pass


def _empty_session(doctor_language: str = "en", patient_language: str = "auto") -> dict:
    return {
        "nodes": {},
        "edges": {},
        "turns": 0,
        "doctor_language": doctor_language,
        "patient_language": patient_language,
        "detected_languages": [],
        "history": [],
        "artifacts": [],
    }


class SessionStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: dict[str, dict] = {}

    def create(
        self,
        doctor_language: str = "en",
        patient_language: str = "auto",
    ) -> str:
        session_id = uuid.uuid4().hex
        with self._lock:
            self._sessions[session_id] = _empty_session(
                doctor_language, patient_language
            )
        return session_id

    def exists(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._sessions

    def append(self, session_id: str, delta: dict) -> dict:
        """Merge a delta into the session graph; returns the full graph.

        Existing elements keep their original ``turn`` (first time seen);
        only genuinely new elements carry the latest turn number.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(session_id)
            session["turns"] += 1
            for node in delta.get("nodes", []):
                session["nodes"].setdefault(node["data"]["id"], node)
            for edge in delta.get("edges", []):
                session["edges"].setdefault(edge["data"]["id"], edge)
            return self._graph_snapshot(session)

    def record_turn(
        self,
        session_id: str,
        *,
        detected_language: str,
        transcript_patient: str,
        transcript_doctor: str,
        triage: dict,
        summary: str,
    ) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(session_id)
            if detected_language and detected_language not in session["detected_languages"]:
                session["detected_languages"].append(detected_language)
            session["history"].append({
                "turn": session["turns"],
                "detected_language": detected_language,
                "transcript_patient": transcript_patient,
                "transcript_doctor": transcript_doctor,
                "summary": summary,
                "triage": triage,
            })

    def add_artifact(self, session_id: str, artifact: dict) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(session_id)
            stored = {
                "id": uuid.uuid4().hex[:12],
                "created_at": datetime.now(timezone.utc).isoformat(),
                **artifact,
            }
            session["artifacts"].append(stored)
            return stored

    def last_patient_language(self, session_id: str) -> str | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            langs = session.get("detected_languages") or []
            return langs[-1] if langs else None

    def get(self, session_id: str) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(session_id)
            return self._graph_snapshot(session)

    def get_full(self, session_id: str) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(session_id)
            return self._full_snapshot(session)

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    @staticmethod
    def _graph_snapshot(session: dict) -> dict:
        return {
            "nodes": list(session["nodes"].values()),
            "edges": list(session["edges"].values()),
            "turns": session["turns"],
        }

    @staticmethod
    def _full_snapshot(session: dict) -> dict:
        return {
            "nodes": list(session["nodes"].values()),
            "edges": list(session["edges"].values()),
            "turns": session["turns"],
            "doctor_language": session["doctor_language"],
            "patient_language": session["patient_language"],
            "detected_languages": list(session["detected_languages"]),
            "history": list(session["history"]),
            "artifacts": list(session["artifacts"]),
        }


SESSION_STORE = SessionStore()
