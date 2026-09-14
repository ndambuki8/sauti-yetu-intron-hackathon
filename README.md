# Voice Triage Hint — Agentic Code-Switch Assistant

MLC (Africa) x Intron Agentic Voice AI Challenge — Deep Learning Indaba 2026.

**Sauti** is a doctor-first consult app for web, phone, and tablet (Expo).
A patient who code-switches (Swahili-English, Hausa-English, Yoruba-English, Pidgin, ...)
arrives at a facility where staff work in English or French. The doctor starts a
record session; the system **auto-detects** the patient's language, transcribes
with **Intron Sahara**, and shows the consult in the **doctor's pre-selected language**.

An **agentic layer takes action**: topic, urgency, department, intake card, and
clarifying questions — plus a **clinical picture graph**. After the consult, the
doctor can speak a request (“prepare a flowchart of probable diseases from these
symptoms”) and a **GPT-4o agent** writes a report or Mermaid flowchart from the
session. The doctor can also reply by voice so the patient hears Intron TTS in
their own language.

Voice drives triage, routing, and documentation — not just transcription.

## How it works

```
Doctor app (Expo: web / phone / tablet)
        |
        +-- Record session --> POST /api/triage
        |       Whisper detect (if Auto) -> Intron Sahara STT + extractions
        |       -> translate transcript to doctor language (NLLB)
        |       -> rule triage + session graph
        |
        +-- Speak to patient --> POST /api/respond  (NLLB + Intron TTS)
        |
        +-- Voice command --> POST /api/command
                Doctor STT -> GPT-4o -> report / flowchart artifact
```

### Clinical reasoning graph (Sahara-only)

The triage tab keeps a **consultation session**. Every recording analysed with
Sahara extends a cumulative graph of the clinical picture — symptoms and
findings the patient presents, the triage topics they suggest, the possible
conditions from Sahara's differential diagnosis, red flags that escalate
urgency, and the department the case routes to. The graph is the
explainability surface: the clinician can see *why* the triage card says what
it says, and how the picture builds over the conversation.

- Built **only** on the Sahara triage flow (`POST /api/triage`). The benchmark
  endpoint never produces a graph.
- `POST /api/session` starts a consultation; `DELETE /api/session/{id}` ends it.
  If `/api/triage` is called without a valid `session_id`, one is created
  implicitly and returned.
- Rendered on its own **Picture** screen (SVG graph on phone; split pane on
  tablet/web). Tap a node to inspect kind and first-seen turn.
- Sessions live in memory only — a server restart clears all consultations.
- The "analysis stages" indicator while Sahara runs is client-side progress,
  not streamed server events.

A second endpoint, `POST /api/benchmark`, runs the same audio through
**three speech models** — Intron Sahara, OpenAI Whisper (local), and Meta MMS
(local) — and reports WER, CER, and latency against a reference transcript,
per the challenge's code-switch benchmarking requirement.

## Setup

1. System dependency (needed by Whisper and audio conversion):

```bash
sudo apt install ffmpeg
```

2. Python environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Expo app (Node 18+):

```bash
cd app
npm install
```

4. API keys — Sahara from [voice.intron.io](https://voice.intron.io) (Developer
   tab) and OpenAI for doctor voice commands:

```bash
cp .env.example .env
# set INTRON_API_KEY and OPENAI_API_KEY
```

## Run

The UI is an **Expo (React Native)** app for web, iOS, Android, and tablet.

**Development** (two terminals):

```bash
# terminal 1 — API
uvicorn backend.app:app --reload --port 8000

# terminal 2 — UI
cd app && npx expo start
```

- Web: press `w` (Expo web on :8081 talks to the API on :8000).
- Phone: scan the QR code with Expo Go. Set `EXPO_PUBLIC_API_URL` to your
  machine's LAN address, e.g. `http://192.168.1.20:8000`, so the device can
  reach FastAPI.

**Production / single process** (web):

```bash
cd app && npm run export:web   # writes app/dist
cd .. && uvicorn backend.app:app --port 8000
```

Open http://localhost:8000 — FastAPI serves the Expo static export.

Notes:
- The local models (Whisper, MMS, NLLB) are lazy-loaded on first use;
  the first benchmark or reply request downloads model weights and is slow.
- The triage flow only needs the Intron API key; it works even if the local
  models are not installed. Replies to `en`/`pcm` patients also skip
  translation entirely.
- Quick-reply translations are cached in `backend/phrases.json`; a native
  speaker can hand-correct entries there and corrections are kept.

## Benchmark report (submission PDF)

Record your code-switched clips into `data/samples/`, register them in
`metadata.csv`, then run:

```bash
python3 -m scripts.generate_benchmark_report --agentic
```

This writes `reports/benchmark_report.pdf` (methodology, overall and
per-language-pair/per-noise WER/CER/latency, switch-point WER, RTF, optional
downstream intent/slot/entity metrics, charts, per-clip transcripts,
limitations) and `reports/results.json` (raw outputs for reproducibility).
Draft answers to the 8 submission questions live in [SUBMISSION.md](SUBMISSION.md).

## Supported patient languages (code-switch capable)

Swahili-English (`sw`), Hausa-English (`ha`), Yoruba-English (`yo`),
Igbo-English (`ig`), Zulu-English (`zu`), Amharic-English (`am`),
Kinyarwanda-English-French (`rw`), Pidgin-English (`pcm`),
Afrikaans-English (`af`), Luganda-English (`lg`), Wolof-French (`wo`), and English (`en`).

## Benchmark data (`data/samples/`)

Code-switched test clips live in `data/samples/` with `metadata.csv`
(columns: `filename, language_pair, language_code, domain, accent_country,
device_type, noise_condition, reference_transcript`, plus optional switch-point
and downstream gold annotations documented in `data/samples/README.md`). These double as the challenge's
audio-sample submission. Run the whole set from the UI's Benchmark section
or via `POST /api/benchmark`.

## Project layout

```
backend/
  app.py            FastAPI: session, triage, respond, command, phrases, benchmark
  agent.py          GPT-4o doctor voice-command artifacts (report / flowchart)
  config.py         .env, doctor + patient language lists
  intron_client.py  Sahara STT sync upload + status-poll fallback
  tts_client.py     Sahara TTS
  translator.py     NLLB-200, including patient ↔ doctor
  phrases.py/.json  quick-reply bank
  triage.py         topic, urgency, department, intake, questions
  graph.py          one-turn graph delta
  graph_store.py    in-memory session graph + history + artifacts
  asr_models.py     Whisper / MMS + language detection
  benchmark.py      3-model WER/CER/latency
  tests/
app/                Expo Router app (web + native)
  src/app/          Home, Record session, Picture, Notes
  src/api/          typed client (EXPO_PUBLIC_API_URL for devices)
  src/state/        consultation context
  src/components/   record control, graph, timeline, reply
  dist/             web export, served by FastAPI at /
frontend/           previous Vite UI (kept for reference)
scripts/
  generate_benchmark_report.py
data/samples/
SUBMISSION.md
```

## Tests

```bash
python -m pytest backend/tests/
```

The Intron HTTP call is monkeypatched, so the suite runs without an API key.

## Out of scope (hackathon simplicity)

Auth, database, EHR integration, real patient PII handling, persistent
consultation sessions, server-streamed (SSE/WebSocket) analysis progress.
