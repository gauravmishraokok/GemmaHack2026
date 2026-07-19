# viGEMMAlya — Analyst Dashboard

React + Vite + Tailwind v4 + Recharts. Dark command-center UI for the AML
analyst: triage dashboard → case view (Timeline / Graph / Evidence /
Investigation / STR + confidence heat-map) → attest → FIU XML download, plus the
constrained-decoding live-rejection widget.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 — expects reasoning service on :8002
```

Configuration: `VITE_REASONING_URL` (defaults to `http://localhost:8002`). The
engine (:8001) is reached through the reasoning service's `/cases` proxy, so the
frontend needs no change on integration day.

Design notes: raw evidence panels carry a "⬒ Raw evidence" badge, everything
model-generated carries "✦ Gemma-generated" — the separation judges are told
about is visible in the chrome. Band/status colors follow a CVD-validated
palette and are never the only carrier of meaning (icons + labels everywhere).
The relationship graph is a dependency-free SVG force layout.
