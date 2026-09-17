# task-router — repo working rules

This repo follows the addyosmani/agent-skills lifecycle on the house ROADMAP. The
table below is the binding skills contract for every session in this repo: the
owner skill(s) per stage, and the duplicate-purpose skills that must **not** be
invoked here. Copied verbatim from `docs/research/SPRINT-PLAN.md` §4.

## Skills workflow (addyosmani lifecycle on the house ROADMAP)

| Stage | Owner skill(s) | Do NOT invoke in this repo (duplicate purpose) |
|---|---|---|
| Define | `spec-driven-development` → `docs/Product_Scope.md`. `interview-me` is **skipped**: D1–D10 answer it. | `superpowers:brainstorming`, `feature-scope-docs`, `grill-with-docs` |
| Plan | `planning-and-task-breakdown` from §5; `api-and-interface-design` for `/v1` + read API; `documentation-and-adrs` (ADRs written by a Sonnet subagent from §2) | `superpowers:writing-plans`, `to-issues` |
| Build | `incremental-implementation` + `observability-and-instrumentation` in parallel; `test-driven-development`; `source-driven-development` for claude -p / Ollama / OTel | `superpowers:test-driven-development`, `tdd`, `superpowers:executing-plans` |
| Verify | `test-driven-development`, `debugging-and-error-recovery` | — |
| Review | `code-review-and-quality` → `code-simplification` → `doubt-driven-development` on judge scheme + replay semantics | `ponytail-review` on the same diff |
| Ship | `git-workflow-and-versioning`, `documentation-and-adrs`, `shipping-and-launch` (no hosted deploy) | — |

`new-repo` runs first (ROADMAP.md, OKF bundle, /protect-repo). `ponytail` stays on for code shape.
