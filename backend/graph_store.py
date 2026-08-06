"""In-memory session store for cumulative consultation graphs.

One session = one consultation. Each triage call appends a graph delta
(see graph.py); the store dedups by element id and keeps the first-seen
turn number, so the cumulative graph stays stable as it grows.

Hackathon scope: process-local, non-persistent, no TTL. A restart clears
all consultations — documented in the README.
"""

import threading
import uuid


class UnknownSessionError(KeyError):
    pass


class SessionStore:
    def __init__(self):
        self._lock = threading.Lock()
        # session_id -> {"nodes": {id: node}, "edges": {id: edge}, "turns": int}
        self._sessions: dict[str, dict] = {}

    def create(self) -> str:
        session_id = uuid.uuid4().hex
        with self._lock:
            self._sessions[session_id] = {"nodes": {}, "edges": {}, "turns": 0}
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
            return self._snapshot(session)

    def get(self, session_id: str) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownSessionError(session_id)
            return self._snapshot(session)

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    @staticmethod
    def _snapshot(session: dict) -> dict:
        return {
            "nodes": list(session["nodes"].values()),
            "edges": list(session["edges"].values()),
            "turns": session["turns"],
        }


SESSION_STORE = SessionStore()
