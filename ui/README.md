# task-router UI

The dashboard for the task-router API: runs list → span waterfall →
replay-and-diff → stats. Vite + React + TypeScript, styled with Tailwind
using the tokens in `../docs/Design_Direction.md`.

## Develop

```
npm install
npm run dev
```

By default the app talks to the router API at `http://localhost:8000`.
Point it elsewhere by setting `VITE_API_BASE` (see `.env.example`).

## Test & build

```
npm test     # vitest run
npm run build
```

## Layout

- `src/api` — typed client for the router's read API (`GET /runs`,
  `GET /runs/{id}/spans`, `POST /replay`, `GET /v1/stats`,
  `GET /v1/models`) plus the tier-color system (`local` / `sonnet` /
  `opus`) shared by every page.
- `src/components` — the app shell (nav rail + tier legend) and shared
  loading/empty/error states.
- `src/pages` — the four dashboard routes.
