"""Doctor voice-command agent — OpenAI GPT-4o over the consultation session.

Produces structured artifacts (markdown report or Mermaid flowchart) from
the accumulated triage history. Hints only — not a diagnosis.
"""

import json

from .config import OPENAI_API_KEY, OPENAI_MODEL

ALLOWED_INTENTS = {"report", "flowchart", "summary", "clarify"}

SYSTEM_PROMPT = """You are a clinical documentation assistant for a hospital triage desk in Africa.
You help a doctor turn a multilingual consultation into a structured note or flowchart.

Hard rules:
- You are NOT a medical device. Every artifact must open with a one-line disclaimer:
  "Decision support only — hints to aid clinical judgement, not a diagnosis."
- Do not invent symptoms, vitals, or conditions that are not in the session context.
- If information is missing, say so and suggest clarifying questions.
- Prefer conservative urgency language. Red flags already marked EMERGENCY stay that way.
- Write the artifact in the doctor's language (ISO code given in the user message).

Return a JSON object with exactly these keys:
- intent: one of "report", "flowchart", "summary", "clarify"
- title: short title
- body: markdown for report/summary/clarify, OR a mermaid flowchart (flowchart TD) for intent=flowchart
- notes: one short sentence on uncertainty or next step
"""


class AgentError(Exception):
    pass


def _session_context(full: dict) -> str:
    parts = []
    for item in full.get("history") or []:
        triage = item.get("triage") or {}
        intake = triage.get("intake_card") or {}
        parts.append(
            f"Turn {item.get('turn')}: "
            f"detected_language={item.get('detected_language')}\n"
            f"Doctor-facing transcript: {item.get('transcript_doctor')}\n"
            f"Summary: {item.get('summary')}\n"
            f"Topic: {triage.get('topic')} | Urgency: {triage.get('urgency')} | "
            f"Department: {triage.get('suggested_department')}\n"
            f"Findings: {intake.get('key_findings')}\n"
            f"Possible conditions: {intake.get('possible_conditions')}\n"
            f"Red flags: {intake.get('red_flags')}\n"
            f"Questions: {triage.get('clarifying_questions')}\n"
        )
    graph = full.get("nodes") or []
    if graph:
        labels = [
            f"{n['data'].get('kind')}:{n['data'].get('label')}"
            for n in graph
            if n.get("data")
        ]
        parts.append("Graph nodes: " + "; ".join(labels[:40]))
    return "\n---\n".join(parts) if parts else "No patient turns recorded yet."


def run_command(command_text: str, full_session: dict) -> dict:
    """Classify the doctor's command and generate an artifact."""
    if not OPENAI_API_KEY:
        raise AgentError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    text = (command_text or "").strip()
    if not text:
        raise AgentError("Command text is empty.")

    doctor_lang = full_session.get("doctor_language") or "en"
    user = (
        f"Doctor language: {doctor_lang}\n"
        f"Doctor command: {text}\n\n"
        f"Session context:\n{_session_context(full_session)}"
    )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AgentError("The openai package is not installed.") from exc

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
        )
    except Exception as exc:
        raise AgentError(f"OpenAI request failed: {exc}") from exc

    raw = (completion.choices[0].message.content or "").strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AgentError("Model returned invalid JSON.") from exc

    intent = parsed.get("intent") if parsed.get("intent") in ALLOWED_INTENTS else "report"
    title = str(parsed.get("title") or "Consultation note").strip()
    body = str(parsed.get("body") or "").strip()
    notes = str(parsed.get("notes") or "").strip()
    if not body:
        raise AgentError("Model returned an empty artifact.")

    return {
        "intent": intent,
        "title": title,
        "body": body,
        "notes": notes,
        "kind": "flowchart" if intent == "flowchart" else "report",
    }
