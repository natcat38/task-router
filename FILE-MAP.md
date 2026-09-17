# FILE-MAP

The directory index agents jump to instead of crawling the tree.

**Hand-maintained** — update it in the same commit that adds or moves a
top-level source directory.

| Directory | Purpose |
| --- | --- |
| `docs` | Product and tech scope docs (`Product_Scope.md`, `Tech_Scope.md`) that are the source of truth for what this router does and how it is built. |
| `docs/adr` | Architecture decision records, one per non-obvious design call (judge tier, replay semantics, provider auth). |
| `knowledge` | OKF knowledge bundle — the domain concepts (tiers, classifier, judge, replay) as markdown, reachable from `knowledge/index.md`. |
| `knowledge/domain` | Concept files for the router's core domain vocabulary: tiers, classifier, judge, replay. |
| `tests` | Python test suite, run with `uv run pytest`. |
| `.github/workflows` | CI: the pytest gate (`ci.yml`) and the OKF knowledge-bundle validator (`okf.yml`). |

6 top-level directories.
