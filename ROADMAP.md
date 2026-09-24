# Roadmap — task-router

**Current stage: DONE — Define→Ship complete; 82 hand + 118 judge-derived labels, retrained; re-score on the hand-corrected labels is optional**
**Next up:** nothing required. Optional follow-ups: a formal `/repo-review`; a hosted demo (needs an API key — out of scope, D4); more/balanced opus labels + a sub-1.0 `judge_sample_rate` re-run if the operator later wants the router to show a positive saving.

**Post-ship addition (2026-09-18/20):** `auto_label.py` (PR #19) derived tiers for the 140 unlabelled rows (forced-`local`, escalate to first judge-pass). Operator ran it (140/140) → merged to 200 labels (60 hand + 140 judge_auto, `tier_source`-tagged, PR #20) → retrained (held-out 0.52 / 5-fold CV 0.645±0.058, opus now learnable). Operator re-ran the full 200-row scoring battery → **Run B: +50.9% excl-judge / +8.1% incl-judge** (both positive) vs the earlier **Run A (60 hand): −11.6% / −68.6%**. Both in the README with a prominent self-referential caveat (Run B's 140 labels came from the same lenient judge that scores it; Run A is the more trustworthy measure). PRs #19–#21.

**2026-09-24:** operator reviewed a 69-candidate worksheet and hand-labelled 30 prompts as opus (p135–p156, p179–p184, p186, p187) → 200 labels = 82 hand + 118 judge_auto; tiers local 102 / sonnet 57 / opus 41. Retrained: held-out 0.46 / 5-fold CV 0.525±0.047 (lower, reported straight — the surface features can't separate opus; opus recall 2/10). PR #22. Stray logs, scratch DBs and stale branches cleaned up.

**Open (optional, operator's call):** re-score on the hand-corrected labels (`uv run python battery.py --db-path data/battery3.sqlite --progress-path data/battery3_progress.json`, ~400 paid calls) for the least-circular savings number; `v0.1.0` tag + CHANGELOG (`git-workflow-and-versioning`, the one §4 Ship skill never run); `/repo-review`.

Lifecycle: Define → Plan → Build → Verify → Review → Ship.
Agents: read this file at session start, state the current stage and next unchecked item before any other work, and update this file (checkboxes + Current stage + Next up) before ending. Product and design decisions belong to the user — elicit them with questions, never decide for them.

## 1 · Define — why this exists (before any code)

- [x] One paragraph: who is this for, what pain does it remove? If the honest answer is "my resume", still pick a fictional real user — it forces every later decision.
- [x] One sentence: what does this repo prove to a recruiter (stack keywords + one differentiator)?
- [x] Name the cut line: the smallest version that is complete and presentable.
- [x] `docs/Product_Scope.md`: background & problem · proposed solution (behaviour, not tech) · hard rules/validation with exact UI copy · decision matrix for any state machine · explicit out-of-scope list · phases with the cut line marked.

Exit: user has signed off the product scope. ✅ Signed off 2026-09-18. Skills: superpowers:brainstorming, grill-with-docs, feature-scope-docs.

## 2 · Plan — how it gets built

- [x] `docs/Tech_Scope.md`: stack with versions · data model sketch · core logic/formulae with a worked example · numbered tasks in vertical slices (each ends runnable + committed) · ⚠️ gotchas · test strategy per slice.
- [x] One ADR in `docs/adr/` per non-obvious decision, written when the decision is made, not after. (0001 judge, 0002 replay, 0003 provider auth)
- [x] `docs/Design_Direction.md` — written in S6a: IBM Plex Sans/Mono, restrained blue-slate palette, tier-color trio (teal local / amber sonnet / rose opus) as the signature element; states + quality floor covered.

Exit: numbered vertical slices exist and the user approves. ⏳ Awaiting Build sign-off. Skills: superpowers:writing-plans, to-issues, hallmark (design direction).

## 3 · Build — the only stage where feature code happens

- [x] Day-1 hygiene, before feature work: `.gitignore` · README stub · OKF knowledge bundle + validator (local + CI) · CI (`uv run pytest`) green on first push · /protect-repo (ruleset active) · config via env vars from the start. Docker/compose: **N/A** — Ollama runs natively on the GPU, SQLite is embedded stdlib.
- [ ] Vertical slices from the Tech Scope, in order. Every slice: implement → test → commit with a message that names the slice. No slice starts while the previous one is red.
  - [x] **S0** environment bring-up + `claude -p`/Ollama smoke + `think:false` request-body pin — PR #1 (`eb3ba50`)
  - [x] **S1** Providers + baseline (registry.yaml, providers.py, fake provider, baseline.py built; not run live) — PR #2 (`10183c8`)
  - [x] **S2** Prompts + classifier (prompts.json 200 drafted, `tier:null` → STOP for labelling; features.py; train.py) — PR #3 (`e0173db`)
  - [x] *(chore)* src-layout packaging so scripts import standalone — PR #4 (`ff1186e`)
  - [x] **S3** Synchronous API (`/v1/completions`, models, stats, routing-config) + OTel SQLite tracing — PR #5 (`5e06caf`) — **Phase A exit ✅**
  - [x] **S4** Background judge (tier above, sampled) + one-step escalation — PR #6 (`aa927e8`). Operator labels (60) committed; classifier v1 trained: held-out 0.80, CV 0.70±0.03 (⚠ only 2 opus labels — opus effectively unlearnable, 5-fold degraded to 2-fold; more opus/sonnet labels would help, non-blocking).
  - [x] **S5** Read API (`GET /runs`, `/runs/{id}/spans`, `POST /replay` forced-tier diff) — PR #7 (`95dd11d`)
  - [x] **S6** React UI (list → waterfall → replay-diff → stats) — PR #8 (`1b385aa`); built in 3 chunks (scaffold/pages/waterfall); `ui` CI now a required check (Node 22)
  - [x] **S7 (code only)** `battery.py` (resumable, retry/backoff, labelled-rows-only, `--dry-run`) + `feedback.py` (weight-3 escalation feedback) + `train.py --version 2` (same held-out ids as v1, no improvement claim) — tests green, NOT run against real models. ⏳ The live paid battery run itself still awaits explicit operator "go" before executing.
  - [x] **S8** honest README + ADR links + committed demo fixture (`data/fixtures/demo.sqlite`) + Jaeger instructions — PR #10 (`0af377c`). ⏳ Jaeger *screenshot* + live battery numbers pending the operator's "go".
- [x] Phase A gate: **label `data/prompts.json`** — 60/200 rows labelled (local: 38, sonnet: 20, opus: 2). Build side of Phase A (S0–S3) is green. Phase A fully closed.

Exit: all slices to the cut line done, CI green. Skills: tdd, ponytail.

## 4 · Verify — does the real thing work ✅

- [x] Ran the actual app end-to-end (real Ollama + FastAPI + React UI + Jaeger). Found and fixed two real bugs the mocked tests missed: **missing CORS** (UI couldn't reach the API — PR #11) and the **OTLP base-endpoint path** (Jaeger export needed `/v1/traces` — PR #13). Live smoke + all read endpoints confirmed.
- [x] UI checked in-browser: runs list / waterfall / replay panel / stats all render real data; responsive card layout at narrow width; error/empty states present. Screenshots captured (`docs/img/`).

Exit: no known broken flows. ✅ (Battery numbers still pending — see Build note.) Skills: run, webapp-testing, diagnose.

## 5 · Review — quality gate before polish ✅

- [x] Backend code-review (code-review-and-quality → code-simplification → doubt-driven on judge/replay) — findings in `docs/review/backend-review.md`. All addressed: `send()` never-raises hole + docstring (PR #14), the HIGH escalation-cost honesty defect (PR #15), plus CORS (#11) and OTLP (#12/#13) from Verify. Judge/replay semantics validated correct under scrutiny.
- [x] Simplification folded into the review pass (ponytail on).
- [ ] UI web-design-guidelines audit — not run (optional; the UI was built with frontend-design + meets the Design_Direction quality floor).

Exit: findings addressed. ✅ Skills: code-review, simplify, web-design-guidelines.

## Battery (ran 2026-09-18)

- [x] Operator ran the battery (60/60, 0 failures) after the UTF-8 `claude -p` decode fix (PR #17). Real numbers now in README "Results (measured)": routed local 27 / sonnet 26 / opus 7; 17 escalations; **saved −11.6% excl-judge / −68.6% incl-judge** (router cost more than all-Opus on this run — honest, with the three reasons + levers). `feedback.py` → 11 weighted rows; `train.py --version 2` held-out 0.40 vs v1 0.80 (v2 did **not** improve; reported side by side, no claim). Run artifacts (`data/battery.sqlite`, `data/feedback.json`) kept local/gitignored.

## 6 · Ship — recruiter-ready (mostly done)

- [x] README: real UI + Jaeger screenshots, ASCII architecture diagram, run-in-3-commands + env table, "why/who" framing, honesty section, ADR links (PRs #10/#13).
- [x] API docs: the seven-endpoint contract is in `docs/Tech_Scope.md` §4 (FastAPI also serves `/docs` Swagger at runtime).
- [ ] Deployed demo link — **N/A by design** (local-only, D4; hosted use needs an API key — the provider slot exists but isn't exercised).
- [ ] Final `/repo-review` — optional; available if the operator wants a formal recruiter-readiness audit. Substantive quality work already done in Verify + Review.

Exit: recruiter-ready. Outstanding: the **battery** (blocked by the harness — operator must run it) to fill live routing/saving numbers + train v2. Skills: repo-review.

## House rules

- Docs before code; scope doc changes are cheaper than code changes.
- Enforcement lives in the backend; the UI mirrors it.
- One well-finished project beats three tutorial follow-alongs.
- If a stage feels like ceremony for a tiny project, shrink the doc to a few sentences — but never skip the stage.
