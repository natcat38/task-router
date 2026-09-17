# Roadmap — task-router

**Current stage: Define**
**Next up:** answer the Define questions with the user.

Lifecycle: Define → Plan → Build → Verify → Review → Ship.
Agents: read this file at session start, state the current stage and next unchecked item before any other work, and update this file (checkboxes + Current stage + Next up) before ending. Product and design decisions belong to the user — elicit them with questions, never decide for them.

## 1 · Define — why this exists (before any code)

- [ ] One paragraph: who is this for, what pain does it remove? If the honest answer is "my resume", still pick a fictional real user — it forces every later decision.
- [ ] One sentence: what does this repo prove to a recruiter (stack keywords + one differentiator)?
- [ ] Name the cut line: the smallest version that is complete and presentable.
- [ ] `docs/Product_Scope.md`: background & problem · proposed solution (behaviour, not tech) · hard rules/validation with exact UI copy · decision matrix for any state machine · explicit out-of-scope list · phases with the cut line marked.

Exit: user has signed off the product scope. Skills: superpowers:brainstorming, grill-with-docs, feature-scope-docs.

## 2 · Plan — how it gets built

- [ ] `docs/Tech_Scope.md`: stack with versions · data model sketch · core logic/formulae with a worked example · numbered tasks in vertical slices (each ends runnable + committed) · ⚠️ gotchas · test strategy per slice.
- [ ] One ADR in `docs/adr/` per non-obvious decision, written when the decision is made, not after.
- [ ] `docs/Design_Direction.md` (any project with a UI): ground it in the subject's own world. Tokens: 4–6 named colors, 2–3 typefaces with roles, layout concept. One signature element; restraint everywhere else. Explicit loading/empty/error states with copy. Quality floor: focus visible, contrast, reduced motion, responsive to 375px. Self-check: "what would the generic default be, and where did I deviate?"

Exit: numbered vertical slices exist and the user approves. Skills: superpowers:writing-plans, to-issues, hallmark (design direction).

## 3 · Build — the only stage where feature code happens

- [ ] Day-1 hygiene, before feature work: sensible `.gitignore` · README stub with the purpose paragraph · OKF knowledge bundle + validator (local + CI) · CI running the test command (even if 0 tests yet) · /protect-repo once pushed public · Docker/compose for backing services · config via env vars from the start.
- [ ] Vertical slices from the Tech Scope, in order. Every slice: implement → test → commit with a message that names the slice. No slice starts while the previous one is red.

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
