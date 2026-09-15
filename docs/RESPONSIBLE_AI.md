# Responsible AI

*A note on privacy, consent, safety, and responsible data use.*

Sauti Yetu handles some of the most sensitive data there is — a person's health complaint, in their own voice, in their own language. This note sets out the commitments we hold ourselves to and, for each one, how it is actually realised in the codebase. It is written to be read by clinicians, reviewers, and the people whose voices the system hears.

> **First principle:** Sauti Yetu is *decision support*. It produces hints to aid a clinician's judgement. It is not a medical device, it does not diagnose, and it never makes a care decision on its own.

---

## 1. Data minimisation

We pass only the information that is relevant to the patient's care, to the component that needs it, for as long as it is needed — and no more.

- **Audio is transient.** Recordings are converted to 16 kHz WAV for processing and the temporary files are deleted immediately afterwards (`asr_models.convert_to_wav_16k`, `prepare_for_intron`). Audio is not stored.
- **Only clinical structure flows downstream.** The reasoning engine and the documentation agent operate over the extracted summary, entities, and the triage decision — not over identity data. Raw audio never reaches the reasoning layer or the external documentation model.
- **Vitals are never inferred.** Age‑banded vital‑sign checks fire *only* when a clinician actually enters a reading; a vital is never guessed from the audio (`triage._evaluate_vitals`).
- **Patient context is optional and additive.** Age, sex, and pregnancy are used only as clinical signal to gate age/sex‑specific criteria. When absent, rules are never excluded (safety‑first) rather than demanding the data.
- **External calls carry the minimum.** Speech audio goes to Intron only when online and only for transcription/TTS; the documentation agent receives the de‑identified session context, never the raw recording.

## 2. Privacy and data retention

- **No persistent database.** The session store is in‑memory and process‑local (`graph_store.py`). One session equals one consultation.
- **Ephemeral by design.** There is no long‑term storage and no TTL persistence — a restart clears all consultations, and there is an explicit `DELETE /api/session/{id}` to end a consultation and drop its data on demand.
- **Local‑first processing.** Transcription (Whisper, MMS), language ID (MMS‑LID), and translation (NLLB‑200) run locally and key‑free, so the core loop can operate without sending a patient's words to any third party. This makes an offline, data‑stays‑here deployment viable.
- **No secrets in outputs.** API keys live in `.env` (git‑ignored) and are never echoed into transcripts, logs, reports, or benchmark artifacts.

## 3. Consent and transparency

- **The patient can see what was heard.** The transcript is surfaced back, so a person can tell what the system understood in their own language.
- **Every reply is shown, not just spoken.** The worker's reply is displayed and played in the patient's language, so nothing is communicated to the patient without being visible.
- **Right to be forgotten, operationally.** Because storage is ephemeral and a session can be deleted, a patient's data does not linger.
- **Deployment expectation.** In a real clinic, obtaining spoken/written consent to record and process the complaint is a deployment requirement; the ephemeral design supports honouring a withdrawal of consent immediately.

## 4. Safety

- **Conservative, escalate‑only triage.** Urgency is *derived*: acuity discriminators and entered vitals can only raise urgency, never lower it (`triage.run_triage`). Under‑triage is treated as the dangerous error.
- **Safe fallback.** When nothing matches, the system does not guess — it routes to *"Undetermined — needs nurse assessment"* and hands off to a human (`fallback` in `triage_kb.yaml`).
- **Red‑flag safety net.** Emergency‑category signs are surfaced explicitly as red flags and preserved through documentation.
- **Human‑in‑the‑loop everywhere.** Extraction only suggests; explicit clinician input always overrides auto‑detected values, which are flagged for confirmation (`extract.py`, `auto_detected`).
- **Fail fast, fail clear.** The clinical knowledge base is validated on boot — a malformed KB stops the app rather than silently mis‑triaging. Transport errors from the ASR API are normalised into clear messages instead of leaking stack traces.

## 5. Explainability and provenance

- **Every clinical claim is cited.** Each assertion in the knowledge base carries a `source` block: `evidence_level` (provisional / expert / guideline / dataset), `review_status` (unreviewed / clinician‑reviewed), the `mapped_scale` (e.g. WHO IITT / SATS), a human‑readable `ref`, and a `url` surfaced in the UI (`ProvenanceBadge`).
- **The reasoning is visible.** The per‑consultation reasoning graph shows the path from complaint → findings → topic → urgency → red flags, so a clinician can inspect *why* a decision was reached.
- **Deterministic decision path.** The triage decision is rule‑based and reproducible; the same input yields the same, auditable output. There is no opaque model in the decision loop.
- **Honest about maturity.** Discriminators adapted from clinical guidelines remain marked `unreviewed` until a clinician confirms the mapping. The system does not overstate the review status of its own knowledge.

## 6. Bounded generative AI

The only generative model (OpenAI GPT‑4o) is confined to *documentation* — turning an existing consultation into a report or flowchart (`agent.py`). It is fenced by a strict system prompt that requires it to:

- open every artifact with a "decision support only — not a diagnosis" disclaimer;
- never invent symptoms, vitals, or conditions absent from the session context;
- keep anything already marked EMERGENCY at that level;
- state when information is missing and suggest clarifying questions;
- write in the clinician's language.

It never sees raw audio and cannot alter the triage decision.

## 7. Fairness, dignity, and access

- **Built for code‑switching.** The system is designed for how people in the region actually speak — mixing Swahili and English mid‑sentence — rather than forcing a single "clean" language.
- **Meets people in their language.** Patients speak and are answered in their own language; clinicians read in theirs. Character Error Rate is reported alongside WER because it is fairer to agglutinative languages such as Swahili and Kinyarwanda.
- **Low‑resource friendly.** Local, key‑free models and an offline‑capable design target clinics with limited or intermittent connectivity, so access does not depend on a paid API always being reachable.
- **Evaluated honestly.** Benchmarks score models against human ground‑truth transcripts, and the reports document their own limitations (sample size, single‑speaker subsets, reference provenance) rather than hiding them.

## 8. Known limitations and responsibilities

- This is a **prototype**; the knowledge base is small and partly `unreviewed`, and results indicate trends rather than clinically validated performance.
- Clinical knowledge adapted from third‑party guidelines (e.g. WHO IITT) is attributed and licensed for non‑commercial use; licensing must be verified before any paid deployment (see the license note in `triage_kb.yaml`).
- Real‑world deployment requires: informed consent workflows, a clinician sign‑off on the knowledge base, secure hosting appropriate to local health‑data regulation, and ongoing monitoring for bias and error.
- Sauti Yetu supports clinical staff. It does not replace clinical assessment, and its outputs must always be reviewed by a qualified human.

---

*This document describes commitments realised in the current codebase and the responsibilities that come with taking it further. If a claim here ever drifts from the code, treat the code — and clinical safety — as the source of truth, and update this note.*
