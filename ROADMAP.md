# Roadmap — task-router

**Current stage: Build — Phase B in progress**
**Next up:** S8 (README + ADR recap + Jaeger screenshot + committed demo fixture). Operator HELD the live battery (2026-09-18): S7 code is merged but not run; README will state routing/saving numbers are pending until the operator says "go". Complete S8 before the weekly reset; pace around the 5-hour window.

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
  - [ ] **S8** README (honest numbers) + ADRs recap + Jaeger screenshot + committed demo fixture — Phase B
- [x] Phase A gate: **label `data/prompts.json`** — 60/200 rows labelled (local: 38, sonnet: 20, opus: 2). Build side of Phase A (S0–S3) is green. Phase A fully closed.

Exit: all slices to the cut line done, CI green. Skills: tdd, ponytail.

## 4 · Verify — does the real thing work

- [ ] Run the actual app end-to-end (not just tests): the happy path plus each hard rule from Product_Scope.
- [ ] UI: check the built screens against Design_Direction.md — states (loading/empty/error), 375px, keyboard focus.

Exit: no known broken flows. Skills: run, webapp-testing, diagnose.

## 5 · Review — quality gate before polish

- [ ] `/code-review high --fix` on the accumulated work.
- [ ] `/simplify` pass.
- [ ] UI: web-design-guidelines audit.

Exit: findings addressed or explicitly waived. Skills: code-review, simplify, web-design-guidelines.

## 6 · Ship — recruiter-ready

- [ ] README rewrite: screenshots, architecture diagram, run-in-3-commands, "why I built this".
- [ ] API docs/Swagger if applicable.
- [ ] Deployed demo link.
- [ ] Final pass with /repo-review.

Exit: /repo-review comes back clean. Skills: repo-review.

## House rules

- Docs before code; scope doc changes are cheaper than code changes.
- Enforcement lives in the backend; the UI mirrors it.
- One well-finished project beats three tutorial follow-alongs.
- If a stage feels like ceremony for a tiny project, shrink the doc to a few sentences — but never skip the stage.
