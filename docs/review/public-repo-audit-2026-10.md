# Public-repo audit, October 2026: outcomes

Audit run 2026-10-22, owner decisions 2026-11-09. Fixes landed in the "fix: public-repo audit findings" PR. Evidence for each finding (file and line) was in the audit report at the time; the outcome column says what changed.

| ID | Finding | Outcome |
|---|---|---|
| P1-1 | Headline numbers had no committed data | Fixed in this PR (decision D4). `data/results/run-a.csv` and `run-b.csv` hold one row per request, exported from the local battery databases by `scripts/export_battery_csv.py`. The README's Run A and Run B figures were recomputed from the CSVs and match. The README tables now point at them. |
| P1-2 | A failed escalation re-answer was marked escalated | Fixed in this PR. `judge.py` leaves `escalated=0`, labels the run `escalation_failed`, keeps the chain entry for the trace, and keeps the original answer. Test in `tests/test_judge.py`. The UI and `/v1/stats` need no change: the UI treats the label as free text and `/v1/stats` counts by final tier. |
| P1-3 | Stale `judge_score` after a two-hop escalation | Fixed in this PR. A score is cleared once its answer is replaced, so an unjudged final answer persists `NULL`. The replay diff's `judge_score_delta` is already `null` when either side is `NULL`. Test in `tests/test_judge.py`. |
| P1-4 | A fresh clone silently used the placeholder heuristic | Fixed in this PR. The README run steps now include `uv run python train.py`, and the `router.select_tier` span carries `router.selector` = `model` or `heuristic`. Tests in `tests/test_api_completions.py`. |
| P1-5 | `tier_map` was written but never read | Fixed in this PR. Answering, judging and escalation resolve tier to model id through `tier_map` (falling back to the registry's tier entry). `PUT /v1/routing-config` rejects a value that names no registered model. Tests: a PUT changes the model that answers; judging and escalation follow the map; an unregistered model is a 422. |
| P1-6 | README, ADRs and scope docs cited gitignored `docs/research/*` | Fixed in this PR (decision D4). Only `docs/research/otel-replay-options.md` is committed (public technical research, no personal data). The other cited notes (`SPRINT-PLAN.md`, `REFUTATIONS.md`, `claude-p-backend.md`, `ollama-local-tier.md`, `task-router-artifact.md`) hold account and plan details, a local username path or a third party's write-up, so they stay local. Each citation of them was replaced with the reasoning inline. `.gitignore` now tracks only the one file. |
| P2-1 | "Routed tiers" row showed the final tier | Fixed in this PR. The README now has a "Routed tier (classifier pick)" row and a "Final tier (after escalation)" row, and the Run B explanation uses the real routed share. |
| P2-2 | v1-vs-v2 table came from the 60-label era | Fixed in this PR. Labelled "historical, 60-label era". |
| P2-3 | Stale docstrings | Fixed in this PR (`db.py`, `classifier.py`). |
| P2-4 | Stale ROADMAP lines | Fixed in this PR. |
| P2-5 | Shipped `judge_sample_rate: 1.0` | Fixed in this PR. `routing.yaml` ships 0.2. `battery.py` used to rely on the file and only warn; it now applies `judge_sample_rate` (default 1.0) itself on a temporary copy of the config. README notes both. |
| P2-6 | "Read-only API" wording | Fixed in this PR. The README says the API writes, has no authentication, and is for local use only. |
| P2-7 | Shared sqlite connection across threads | Issue #29, left unfixed. |
| P2-8 | Replay errors in fixture mode | Fixed in this PR (README sentence: replay needs live models). |
| P2-9 | No topics, no release | Issue #31, owner action (decision D8). |
| P2-10 | Tooling files in the repo root | Kept by owner decision D5. `CLAUDE.md` and `.claude/settings.json` stay. |
| Fallback | A failed judge call looks the same as "not sampled" | README sentence added (a failed judge call leaves the answer unjudged and unescalated). |
| Fallback | Ollama down fails every local-routed request | Issue #30, left unfixed. README states that nothing falls back. |
| okf pin | Validator pinned to `@v1` | `okf.yml` now pins `natcat38/okf-portfolio-standard@a9d01a2b63545a4db537a1aaef0d05de1a0ea69a # v1.4.0`. A weekly `github-actions` Dependabot entry was added so the pin gets bump PRs. |

## Notes on the exported data

- Run B has 201 rows for 200 prompts. The extra row is a duplicate run of one prompt; it is flagged `duplicate_row=1` and, as in the original statistics, it counts toward the totals.
- Routed tier is derived: one tier below the first escalation target in the stored chain, or the final tier if nothing escalated. In Run B the classifier never picked opus (163 local, 38 sonnet). The README's earlier wording that the retrained classifier "learned the opus tier" was not supported by this data and was removed.
- Both runs predate the P1-2 and P1-3 fixes. Their rows reflect the old behaviour, which is why `reanswer_failed` and `escalation_hops` are in the CSV.
