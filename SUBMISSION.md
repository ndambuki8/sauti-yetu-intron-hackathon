# Submission — Voice Triage Hint

MLC (Africa) x Intron Agentic Voice AI Challenge, Deep Learning Indaba 2026.
Draft answers to the 8 submission questions, plus links. Edit team-specific
placeholders before submitting.

- Demo video link: `<PASTE DEMO VIDEO LINK>`
- Benchmark report (PDF): generate with `python -m scripts.generate_benchmark_report`
  -> `reports/benchmark_report.pdf`
- Benchmark audio dataset link (optional): `<PASTE LINK TO data/samples OR CLOUD FOLDER>`

## 1. The problem it addresses

Patients who do not speak the language of the health facility — migrants,
refugees, cross-border travelers, or citizens outside their home language
region — struggle to communicate symptoms at the most critical moment:
arrival. Real African speech compounds this: people naturally code-switch
mid-sentence (Swahili-English, Hausa-English, Pidgin), which breaks
monolingual voice systems. Miscommunication at triage delays care and can be
dangerous.

## 2. Target users

Front-line health workers (triage nurses, front-desk clinical officers) in
hospitals and clinics that receive linguistically diverse patients — urban
referral hospitals, border-region facilities, and clinics serving migrant and
refugee populations. Secondary user: the patient, who both speaks and hears
feedback in their own language.

## 3. How it solves the problem

The patient speaks freely in their own (code-switched) language. The system
transcribes with Intron Sahara, extracts clinical structure in English, and
takes a triage action: it classifies the complaint topic, assigns an urgency
level (EMERGENCY / URGENT / ROUTINE) with red-flag escalation, routes to a
suggested department, auto-fills an intake card, and proposes clarifying
questions. The health worker then replies with a quick phrase or typed
English; the reply is machine-translated (local NLLB-200) and spoken back to
the patient with a native Intron TTS voice — a full two-way conversational
loop with no shared language required.

## 4. Code-switching support

The app targets Sahara's code-switch-capable (multilingual) language modes:
Swahili-English, Hausa-English, Yoruba-English, Zulu-English,
Amharic-English, Kinyarwanda-English-French, Pidgin-English, and
Afrikaans-English, plus more monolingual modes. Code-switched handling is not
assumed — it is measured: our benchmark runs self-recorded, code-switched
clinical clips (metadata: language pair, domain, accent/country, device,
noise) through three models and reports WER/CER/latency per language pair and
noise condition (see the PDF report).

## 5. Sahara API usage

Three Sahara capabilities are integrated:

1. STT sync upload (`POST /file/v1/upload/sync`) with
   `use_category=file_category_telehealth` and `use_language_asr_input` set to
   the patient's language, requesting `get_summary`, `get_entity_list`,
   `get_suggestions`, `get_differential_diagnosis`, `get_followup_instructions`.
2. Cross-language extraction: `use_language_data_extraction_output=en`, so the
   worker reads English structure while the patient speaks their language.
   The 503 timeout path falls back to polling `GET /file/v1/status/{file_id}`.
3. TTS (`POST /tts/v1/generate`) with native voices (swahili, hausa, yoruba,
   igbo, amharic, kinyarwanda, pidgin, luganda, wolof, afrikaans) and
   male/female gender choice, with the `GET /tts/v1/status/{text_id}` fallback.

## 6. Agentic behavior

Voice drives downstream actions, not just transcription. Each patient
utterance triggers an agentic pipeline that decides and acts: topic
classification, urgency scoring with red-flag escalation, department routing,
automatic intake-card completion, and generation of clarifying questions for
the nurse. The loop closes with an action in the opposite direction: the
system translates the worker's response and speaks it to the patient in
their language. The output is a decision-and-action bundle a triage desk can
execute immediately.

## 7. Technical overview

FastAPI backend + dependency-free white-page frontend. Patient audio
(browser MediaRecorder or file upload, <= 120 s) goes to `/api/triage`, which
calls Sahara STT-telehealth and runs a deterministic rule-based triage layer
(`backend/triage.py`) over the English extractions — transparent and
auditable, with an LLM hook if desired. `/api/respond` translates the
worker's English (local `facebook/nllb-200-distilled-600M`; Pidgin passes
through as English-lexified) and synthesizes speech via Sahara TTS, proxied
server-side so the API key never reaches the browser. The benchmark harness
(`backend/benchmark.py` + `scripts/generate_benchmark_report.py`) runs Intron
Sahara, OpenAI Whisper, and Meta MMS (mms-1b-all) on identical 16 kHz mono
audio with identical jiwer normalization and produces the PDF report with
per-language-pair and per-noise breakdowns. Quick-reply translations are
cached in `backend/phrases.json`, where native speakers can vet and correct
them.

## 8. Ethics, safety and inclusion

- Consent: recording is disabled until the worker confirms patient consent
  via an explicit checkbox stating what happens to the audio.
- Privacy: audio is processed via the Intron API and never stored by the app;
  no accounts, no database, no PII persistence; the API key stays server-side.
- Safety: the tool is explicitly labeled "not a medical device — hints only";
  it suggests, and the clinician decides. Red-flag escalation is conservative
  (any detected red flag raises urgency to EMERGENCY).
- Inclusion and dignity: patients are heard and answered in their own
  language, including a choice of voice gender; languages without a native
  TTS voice (e.g. Zulu) still get translated on-screen text plus
  locally-accented English audio, clearly labeled.
- Bias awareness: the benchmark report documents accent coverage limits,
  sample-size limits, and transcription-convention bias, and ships raw
  results (reports/results.json) for independent verification.

## Rubric mapping (for our own check)

| Criterion (weight) | Where we address it |
| --- | --- |
| Real-World Impact (20%) | Q1-Q3: triage communication for linguistically excluded patients |
| Code-Switching Benchmark Quality (30%) | PDF report: 3 models, identical audio/normalization/hints, WER+CER+latency, per-pair and per-noise breakdowns, limitations section, raw JSON |
| Product Quality & Fit (25%) | Q3/Q6: full agentic loop in a workflow a triage desk actually follows |
| Technical Execution (15%) | Q7: architecture, 503 fallbacks, key kept server-side, local models |
| Ethics, Safety & Inclusion (10%) | Q8: consent gate, no storage, disclaimers, voice dignity, bias notes |
