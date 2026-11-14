# QueuePilot dashboard (frontend/, owned by WIN)

React 19 + Vite + TypeScript + Tailwind v4 + Recharts.

```
cd frontend && npm install && npm run dev      # http://localhost:5173
```
Backend (repo root): `uvicorn api.main:app --reload` on :8000. Override with `VITE_API=http://host:8000`.
If the API is down, the dashboard shows saved real responses from `src/data/*.json` and says OFFLINE.

## Panels
01 Forecast (`/forecast` example + errors) · 02 Plan (`staffing_plan` + `staffing_comparison`) ·
03 Route (`/simulate`, 3 strategies, closures, priority) · 04 Replay (`timeline` from `trace: true`).

## Demo links (scenario set from the URL)
- `/?close=C2&from=60&len=120` C2 closed 60–180 min
- `/?priority=10` 10% priority people
- `&t=22` start the replay at frame 22 (= minute 110)

## Files
`src/api.ts` API types + fetch + offline fallback · `src/scenario.ts` counters, controls, URL parsing ·
`src/components/*Panel.tsx` one file per panel · `Frame.tsx` panel chrome · `Guard.tsx` per-panel error boundary.

Refresh offline data after engine changes: `curl -s localhost:8000/forecast > src/data/forecast.json` and
`curl -s -X POST localhost:8000/simulate -H 'content-type: application/json' -d '{"runs":60,"trace":true}' > src/data/simulate.json`.
