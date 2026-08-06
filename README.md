# Voice Triage Hint — Agentic Code-Switch Assistant

MLC (Africa) x Intron Agentic Voice AI Challenge — Deep Learning Indaba 2026.

A patient who code-switches (Swahili-English, Hausa-English, Yoruba-English, Pidgin, ...)
arrives at a facility where staff work in English. This app captures their speech,
uses **Intron Sahara** to transcribe and extract clinical structure, then an
**agentic layer takes action**: it classifies the triage topic, assigns an urgency
level, routes to a suggested department, auto-fills an intake card, and proposes
clarifying questions for the nurse — while a **live clinical reasoning graph**
shows the clinician how each piece of the picture connects.

Voice drives a downstream task (triage + routing + intake), not just transcription.

## How it works

```
Browser mic / file upload
        |
        v
FastAPI  POST /api/triage
        |
        v
Intron Sahara sync upload  (telehealth category, English extraction output)
  - transcript in patient language
  - entities, differential diagnosis, suggestions, summary (in English)
        |
        v
Agentic triage layer (backend/triage.py)
  - topic classification
  - urgency: EMERGENCY / URGENT / ROUTINE
  - suggested department routing
  - auto-filled intake card
  - clarifying questions for the nurse
        |
        v
Clinical reasoning graph (backend/graph.py + graph_store.py)
  - one session per consultation (POST /api/session)
  - each recording appends nodes/edges: patient -> symptoms/findings ->
    topic -> possible conditions; red flags escalate; topic routes to department
        |
        v
Practitioner UI: live reasoning graph (Cytoscape.js) + triage cards
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
- Rendered with [Cytoscape.js](https://js.cytoscape.org/) inside the React app;
  clicking a node highlights its 1-hop neighborhood and shows what it is and
  when it first came up.
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

3. Frontend dependencies (Node 18+):

```bash
cd frontend
npm install
```

4. API key — sign up at [voice.intron.io](https://voice.intron.io), open the
   Developer tab, copy your key, then:

```bash
cp .env.example .env
# edit .env and set INTRON_API_KEY
```

## Run

The frontend is a **React + TypeScript + Vite + Tailwind** app. Two ways to run it:

**Development** (hot reload, two terminals):

```bash
# terminal 1 — API
uvicorn backend.app:app --reload --port 8000

# terminal 2 — UI (proxies /api to :8000)
cd frontend && npm run dev
```

Open http://localhost:5173.

**Production / single process**:

```bash
cd frontend && npm run build   # type-checks, then bundles to frontend/dist
cd .. && uvicorn backend.app:app --port 8000
```

Open http://localhost:8000 — FastAPI serves the built SPA. Restart uvicorn
after rebuilding.

Notes:
- The local benchmark models (Whisper, MMS) are lazy-loaded on first use;
  the first benchmark request downloads model weights and is slow.
- The triage flow only needs the Intron API key; it works even if the local
  models are not installed.

## Supported patient languages (code-switch capable)

Swahili-English (`sw`), Hausa-English (`ha`), Yoruba-English (`yo`),
Igbo-English (`ig`), Zulu-English (`zu`), Amharic-English (`am`),
Kinyarwanda-English-French (`rw`), Pidgin-English (`pcm`),
Afrikaans-English (`af`), Luganda-English (`lg`), Wolof-French (`wo`), and English (`en`).

## Benchmark data (`data/samples/`)

Code-switched test clips live in `data/samples/` with `metadata.csv`
(columns: `filename, language_pair, domain, accent_country, device_type,
noise_condition, reference_transcript`). These double as the challenge's
audio-sample submission. Run the whole set from the UI's Benchmark section
or via `POST /api/benchmark`.

## Project layout

```
backend/
  app.py            FastAPI app: /, /api/session, /api/triage, /api/benchmark
  config.py         .env loading
  intron_client.py  Sahara sync upload + status-poll fallback
  triage.py         agentic layer: topic, urgency, department, intake, questions
  graph.py          turns one triage turn into a graph delta (nodes + edges)
  graph_store.py    in-memory per-consultation session graphs
  asr_models.py     local Whisper + Meta MMS wrappers
  benchmark.py      WER/CER (jiwer) + latency across the 3 models
  tests/            graph + API tests (no Intron key needed)
frontend/
  index.html          Vite entry
  vite.config.ts      dev server on :5173, proxies /api to :8000
  tailwind.config.js  design tokens (clinical semantics shared with the graph)
  src/
    api/              typed client + response contracts mirroring the backend
    state/            consultation context (session, turns, cumulative graph)
    lib/              palette (node-kind colors) + Sahara extraction splitting
    components/       TopBar, CapturePanel, StageStepper, ConversationTimeline,
                      ReasoningGraph (Cytoscape), ClinicalRail, BenchmarkPanel
  dist/               production build (git-ignored), served by FastAPI at /
data/
  samples/          code-switched audio + metadata.csv
```

## Tests

```bash
python -m pytest backend/tests/
cd frontend && npm run build   # also the frontend's type-check gate (tsc)
```

The Intron HTTP call is monkeypatched, so the suite runs without an API key.

## Out of scope (hackathon simplicity)

Auth, database, EHR integration, real patient PII handling, persistent
consultation sessions, server-streamed (SSE/WebSocket) analysis progress.
