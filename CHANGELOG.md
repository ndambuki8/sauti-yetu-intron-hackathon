# Changelog

All notable changes to this project are documented here, grouped by branch.

## `visual-graphs` — clinical reasoning graph + SaaS frontend rebuild

### Added

- **Clinical reasoning graph (Sahara-only).** Every recording analysed through
  `POST /api/triage` now extends a cumulative per-consultation graph:
  patient → symptoms/findings → triage topic → possible conditions, with red
  flags escalating urgency and topics routing to departments. The benchmark
  endpoint never produces a graph.
  - `backend/graph.py` — pure delta builder; stable node ids
    (`kind:normalized-label`) so repeated mentions dedup naturally.
  - `backend/graph_store.py` — thread-safe in-memory session store (one
    session = one consultation; non-persistent by design).
  - New endpoints: `POST /api/session`, `DELETE /api/session/{id}`.
    `/api/triage` accepts an optional `session_id` (creates one implicitly if
    absent/unknown) and returns the full cumulative `graph` plus `session_id`.
- **React + TypeScript + Vite + Tailwind frontend**, replacing the vanilla
  JS/CSS UI:
  - Clinical-workstation layout: sticky TopBar (consultation status pill, tab
    switch, New consultation), left rail (capture + conversation), center
    graph, right rail (triage decision, intake card, nurse questions).
  - **Conversation timeline** — each recording becomes a turn card with
    timestamp, language, audio duration, urgency chip, transcript quote,
    English summary, findings/conditions chips, red-flag callout, and Sahara
    suggestions. Auto-scrolls to the newest turn.
  - **Analysis stage stepper** — client-side progress while Sahara works
    (upload → transcription → extraction → reasoning → graph update).
  - Typed API layer (`src/api/`) mirroring backend contracts; design tokens
    shared between Tailwind and the graph (`src/lib/palette.ts`); Sahara
    extraction splitting mirrors `backend/graph.py` (`src/lib/extraction.ts`).
  - Benchmark tab feature-complete in the new design system.
- **Miro-style graph rendering** (`src/components/ReasoningGraph.tsx`):
  compact tinted pill nodes with labels inside (high information density),
  deterministic left-to-right layered `breadthfirst` layout, right-angle
  `taxi` connectors, dashed red escalation edges, blue outline pulse on
  newest additions, click-to-inspect with 1-hop neighborhood highlight,
  zoom/fit toolbar.
- **Backend tests** — `backend/tests/test_graph.py`: 10 tests covering delta
  structure, node-id stability/dedup, session accumulation, unknown-session
  fallback, and the Sahara-only graph guarantee. The Intron call is
  monkeypatched; no API key needed.

### Changed

- `backend/app.py` — serves the built SPA from `frontend/dist` (mounted last
  so `/api` always wins); helpful 404 when the frontend isn't built.
- `backend/app.py` — benchmark module import is now lazy, so the triage flow
  (and its tests) work without `jiwer`/torch/whisper installed, as the README
  always claimed.
- `README.md` — documents the graph, sessions, the React dev workflow
  (Vite on :5173 proxying `/api` to :8000), and the single-process production
  mode (`npm run build` → uvicorn serves `frontend/dist`).
- `.gitignore` — ignores `node_modules/`.

### Fixed

- **TLS/transport failures no longer crash with a 500 traceback.**
  `backend/intron_client.py` wraps all Intron HTTP calls so `SSLError`,
  connection errors, and timeouts surface as a clean 502 with an actionable
  message (covers the Windows/antivirus TLS-interception case seen in dev).

### Migration notes

- Frontend requires Node 18+: `cd frontend && npm install`.
- Dev: `uvicorn backend.app:app --reload --port 8000` +
  `cd frontend && npm run dev` → http://localhost:5173.
- Single process: `cd frontend && npm run build`, then uvicorn serves
  http://localhost:8000. Restart uvicorn after rebuilding.
