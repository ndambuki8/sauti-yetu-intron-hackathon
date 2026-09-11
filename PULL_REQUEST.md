# Explainable, knowledge-base-driven triage + product-grade UI

## Summary

This PR turns the triage prototype into an explainable, knowledge-base-driven
decision-support tool and rebuilds the interface into a mobile-ready,
SaaS-grade product. The clinical logic moves out of hard-coded Python and into
a reviewable, source-tagged knowledge base; urgency is now **derived and cited**
from WHO IITT criteria; patient context (age / sex / pregnancy) and optional
vitals are folded in; a **probabilistic differential** ranks likely conditions;
and every conclusion is traceable to its source in the UI.

The deterministic, safety-first reasoning core is preserved throughout — nothing
here is a black box, and the acuity/red-flag path is never overridden by a
probability.

## Why

- The old triage was a flat keyword→topic map with hard-coded urgency. It wasn't
  reviewable by clinicians, wasn't sourced, and couldn't explain itself.
- Explainability is the product's core value. Every step now carries provenance.
- The UI read as a prototype and was unusable on a phone.

## What changed

### Reasoning engine (backend)

- **Knowledge as data.** All clinical logic now lives in
  `backend/knowledge/triage_kb.yaml`, loaded and validated on boot by
  `backend/knowledge_base.py` (Pydantic schema, fail-fast on a malformed KB).
  `backend/triage.py` is now a thin deterministic engine over that data.
- **Provenance on everything.** Every topic, discriminator, condition, and vital
  threshold carries a `source` block: `evidence_level`, `review_status`,
  `mapped_scale`, `ref`, and a citation `url`.
- **WHO IITT acuity model.** Replaced the flat red-flag list with ~33
  category-tagged discriminators (red = EMERGENCY, yellow = URGENT). Urgency is
  **derived** as the most acute of the matched topic and discriminators, and
  only ever escalates (safety-first). Each escalation names the specific
  discriminator that caused it.
- **Patient context.** `PatientContext` (age / sex / pregnancy) gates
  age- and sex-conditional criteria (e.g. chest/abdominal pain is red only over
  50, testicular pain is male-only, the pregnancy block requires pregnancy).
  Unknown context never excludes a rule, biasing toward over-triage.
- **Age-banded vital signs.** Optional HR / RR / temperature / SpO₂ / AVPU are
  evaluated against IITT age-banded thresholds and escalate as cited signs — only
  when a reading is actually entered (audio never supplies vitals).
- **Conversation extraction.** `backend/extract.py` pulls age / sex / pregnancy
  hints from the transcript as *suggestions* (explicit clinician input always
  wins; auto-detected fields are flagged for confirmation).
- **Probabilistic differential (naive-Bayes).** Conditions in the KB carry a
  prior and symptom likelihood ratios; the engine updates the odds per present
  finding and ranks a cited differential. Pure arithmetic (~0.5 ms, no added
  latency). It augments the "possible conditions" list and never overrides the
  acuity path.
- **Honest review status.** Added a `chart-verified` review state (cross-checked
  against the source chart, pending clinician sign-off) between `unreviewed` and
  `clinician-reviewed`.

### Interface (frontend)

- **Voice-first hero** (`VoiceCapture`): a reactive microphone orb whose halo and
  live waveform respond to the real mic input (Web Audio `AnalyserNode`), with
  idle / recording / analysing states and a 120s auto-stop.
- **SaaS visual system**: gradient-mesh background, glassmorphism cards, a brand
  gradient, animated aurora accents, and a glass header. Fully responsive /
  mobile-ready. Removed the prototype footer; verbose helper paragraphs became
  tooltips; purged em dashes from UI copy.
- **Miro-style reasoning board**: migrated the graph from Cytoscape to **React
  Flow** (`@xyflow/react`) with a dotted canvas, custom node cards, dagre
  left-to-right auto-layout, controls, minimap, drag, and fullscreen. Condition
  nodes are **sized and labeled by probability**. (Bundle dropped ~731 kB → ~473 kB.)
- **Adaptive segmented view** to prevent clutter after analysis:
  **Summary / Differential / Evidence / Map**, showing one focused panel at a
  time. Opens on Summary after analysis, on the interactive Map before it.
- **Explainability surfaced**: evidence/review badges (green = guideline /
  clinician-reviewed, blue = chart-verified, amber = provisional) and citation
  links appear on the trace, the differential, and the graph inspector.

## Design decisions

- **No RAG.** Triage is a bounded decision over a finite, authoritative source.
  A structured, cited KB is deterministic, auditable, and explainable; RAG would
  add latency, nondeterminism, and hallucination risk. An LLM's right role here
  is extraction/normalization, not the decision.
- **Deterministic safety net stays deterministic.** Probabilities rank the
  differential; they never soften a red flag or the derived urgency.
- **Honesty about maturity.** Provenance status reflects reality: chart-mapped
  entries are `chart-verified`, not falsely `clinician-reviewed`.

## Testing / verification

- Backend: `pytest backend/tests/` — 10 passing (graph, store, endpoints, triage
  contract preserved; `run_triage` remains backward-compatible).
- Frontend: `npm run build` (tsc + vite) passes clean.
- Smoke-tested: age/sex gating, age-banded vitals (HR 150 normal at age 3, EMERGENCY
  at age 8), extraction, and the differential ranking end-to-end into the graph.

## How to run

```bash
# backend (note: port 8001 to avoid a local Docker container on 8000)
uvicorn backend.app:app --reload --host 127.0.0.1 --port 8001

# frontend (proxies /api to 127.0.0.1:8001)
cd frontend && npm install && npm run dev
```

## New dependencies

- Backend: `pyyaml` (knowledge base).
- Frontend: `@xyflow/react`, `dagre`, `@types/dagre` (reasoning board).

## Licensing note (action required before commercial use)

The WHO IITT charts are © WHO/ICRC/MSF under **CC BY-NC-SA 3.0 IGO
(NonCommercial)**. The underlying clinical criteria are encoded with attribution
(see `meta.license` in the KB), but reproducing the tool's wording/layout
commercially may need permission. Verify before any paid deployment.

## Known limitations / follow-ups

- **Provisional numbers.** The differential priors and likelihood ratios are
  honest starter estimates to prove the mechanism. Replace with cited LRs (e.g.
  JAMA *Rational Clinical Examination*) and local-prevalence priors during
  clinical review; entries show amber until then.
- **Clinician sign-off pending.** Most entries are `chart-verified`, not yet
  `clinician-reviewed`.
- **Not real-time yet.** Flow is record → analyse; the UI is designed for
  streaming but the streaming transport is future work.
- **Future methods.** Noisy-OR Bayesian network (pgmpy) when the independence
  assumption hurts; calibrated logistic regression once real case data is
  collected (validate with Brier score / calibration curves).
- **Not a medical device.** Decision support only; outputs assist, never replace,
  clinical judgement.
