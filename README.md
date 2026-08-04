# Voice Triage Hint — Agentic Code-Switch Assistant

MLC (Africa) x Intron Agentic Voice AI Challenge — Deep Learning Indaba 2026.

A patient who code-switches (Swahili-English, Hausa-English, Yoruba-English, Pidgin, ...)
arrives at a facility where staff work in English. This app captures their speech,
uses **Intron Sahara** to transcribe and extract clinical structure, then an
**agentic layer takes action**: it classifies the triage topic, assigns an urgency
level, routes to a suggested department, auto-fills an intake card, and proposes
clarifying questions for the nurse — all rendered on a simple white page.

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
Practitioner triage card (white page UI)
```

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

3. API key — sign up at [voice.intron.io](https://voice.intron.io), open the
   Developer tab, copy your key, then:

```bash
cp .env.example .env
# edit .env and set INTRON_API_KEY
```

## Run

```bash
uvicorn backend.app:app --reload --port 8000
```

Open http://localhost:8000 — record from the mic or upload a clip
(max 120 seconds, per the Sahara sync endpoint limit).

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
  app.py            FastAPI app: /, /api/triage, /api/benchmark
  config.py         .env loading
  intron_client.py  Sahara sync upload + status-poll fallback
  triage.py         agentic layer: topic, urgency, department, intake, questions
  asr_models.py     local Whisper + Meta MMS wrappers
  benchmark.py      WER/CER (jiwer) + latency across the 3 models
frontend/
  index.html, app.js, styles.css   simple white-background UI
data/
  samples/          code-switched audio + metadata.csv
```

## Out of scope (hackathon simplicity)

Auth, database, EHR integration, real patient PII handling.
