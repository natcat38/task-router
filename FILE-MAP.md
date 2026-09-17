# FILE-MAP

The directory index agents jump to instead of crawling the tree.

**Hand-maintained** — update it in the same commit that adds or moves a
top-level source directory.

| Directory | Purpose |
| --- | --- |
| `docs` | Product and tech scope docs (`Product_Scope.md`, `Tech_Scope.md`) that are the source of truth for what this router does and how it is built. |
| `docs/adr` | Architecture decision records, one per non-obvious design call (judge tier, replay semantics, provider auth). |
| `data` | Classifier training data: `prompts.json` (200 drafted rows across the 9 use cases, `tier: null` until the operator hand-labels them). |
| `knowledge` | OKF knowledge bundle — the domain concepts (tiers, classifier, judge, replay) as markdown, reachable from `knowledge/index.md`. |
| `knowledge/domain` | Concept files for the router's core domain vocabulary: tiers, classifier, judge, replay. |
| `scripts` | One-off manual smoke tests that aren't part of the pytest suite or CI (e.g. `smoke_claude.py`, the S0 Windows-stdin + think:false check) — run by hand, never automatically. |
| `src/task_router` | The installable `task_router` package — application code, starting with the pinned local-tier (Ollama) request body in `local_request.py`. |
| `tests` | Python test suite, run with `uv run pytest`. |
| `.github/workflows` | CI: the pytest + UI gate (`ci.yml`) and the OKF knowledge-bundle validator (`okf.yml`). |
| `ui` | The React dashboard (Vite + TS + Tailwind) that reads the router's API: runs list, waterfall, replay-diff, stats (Tech_Scope §1, §4). Its own `package.json` — never touches the Python project. |
| `ui/src/api` | Typed client for the read API (`client.ts`, `types.ts` matching Tech_Scope §4 exactly) and the tier-color system (`tiers.ts`) shared by every page. |
| `ui/src/components` | The app shell (nav rail + tier legend, `AppShell.tsx`), the tier chip, and the shared loading/empty/error state components. |
| `ui/src/pages` | The four dashboard routes: runs list, run waterfall, replay-diff, stats. |

10 top-level directories.
