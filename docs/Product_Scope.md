# Product Scope: Task Router

Status: DEFINE stage, sourced from `docs/research/SPRINT-PLAN.md` §2 (D1–D10, binding) and §8, cross-checked against `docs/research/task-router-artifact.md` and `docs/research/REFUTATIONS.md` §B–D. No product decisions are made in this document — they are already made; this document states them as scope.

## 1. Background & problem

In the voice of the fictional user this repo is built for (SPRINT-PLAN D8):

> I'm a solo developer. I pay for one LLM subscription and I write small scripts against it — a changelog formatter, a data cleaner, a quick classifier. Every one of those scripts calls the same expensive model, because picking a cheaper one for each task is manual work I don't do. I want the cheap model to be the default, with something behind it that catches the cheap model when it's wrong, so I don't have to babysit it. And when a request comes back wrong, or cheap, or expensive, I want to see *why the router put it there* — not just a log line, a walk through the decision.

The problem is not "which model is best" — it's that nobody routes their own requests by cost, and when something like this exists, it is a black box: you get an answer and a bill, not a reason.

## 2. What this proves to a recruiter

This repo proves the ability to instrument a decision pipeline well enough to replay and diff that pipeline's own past decisions — classify, tier selection, and escalation — under a forced alternative, which is narrower and harder than what general LLM-observability tools offer today (they replay a stored prompt against a swapped model; none of them replay the router's own decision sequence).

## 3. Proposed solution — behaviour

### 3.1 Request lifecycle (synchronous path)

1. **Classify.** A request is scored against a fixed set of surface features (length, instruction verbs, supplied context, output format, etc.) and assigned to one of three tiers: a local model tier, a mid cloud tier ("Sonnet tier"), or a top cloud tier ("Opus tier"). No model call happens to make this decision.
2. **Route.** The request goes to whichever tier the classifier picked.
3. **Answer.** That tier's model answers, and the answer is returned to the caller immediately. The caller never waits on anything below this line.
4. **Audit.** One record is written per request: which tier answered, what it would have cost at each other tier, and (once judged) the judge's score and any escalation.

### 3.2 Asynchronous safety net

- After the answer is returned, a background check judges it — **the judge is always the tier one level above** the tier that answered: local-tier answers are judged by the Sonnet tier, Sonnet-tier answers are judged by the Opus tier. Opus-tier answers are the top of the chain and are not judged (there is no tier above Opus to grade it, and grading a model with itself is exactly the failure mode this design avoids).
- The judge does not run on every request — it runs on a **sampled fraction**, configurable, so the safety net's own cost is visible and controllable rather than assumed to be free.
- A judged answer that scores below its use case's bar is **escalated one tier at a time** (local → Sonnet, or Sonnet → Opus) — never straight to the top — and the escalated answer replaces the original in the audit record.
- Every escalation becomes a labelled training example for a future retrained classifier. This only helps the classifier on near-duplicates of requests it has already seen wrong; it does not give the classifier the ability to see meaning it wasn't built to see (§4).

### 3.3 Replay-and-diff

Any past request in the audit log can be replayed with a different tier forced, and the outcome is diffed against what actually happened the first time — the classify, tier-selection, judge, and escalation steps all re-run under the forced tier, not just the model call. That full-pipeline replay, against a real historical request, is the capability this repo is built to demonstrate; a tool that only swaps the model on a stored prompt is doing something narrower.

The audit log and the routing config (which tier handles what, and the judge's sample rate) are both inspectable and, for routing config, editable without restarting anything.

## 4. Hard rules / honesty constraints

These are non-negotiable and must appear in the README, not just be true in the code:

- **No real money.** Every cloud call in this project runs on an existing subscription, never a metered API key. Any "saving" figure is calculated at **API list prices that were never billed** — every such figure must say so, in words, next to the number.
- **Savings are shown two ways: with judge tokens counted, and without.** A local-tier answer that gets judged by the Sonnet tier still cost one Sonnet-tier call — leaving that out overstates the local tier's saving. Both figures are reported; neither is hidden.
- **Classifier accuracy is reported as: number of labelled examples used, size of the held-out set, and 5-fold cross-validation accuracy with its spread** — not a single point estimate on a small held-out set, which is noise dressed as a result.
- **No claim that a retrained classifier ("v2") is better than the first one.** The held-out set is small; a one-item difference is not evidence. Report the numbers for both, side by side, without a verdict.
- **The classifier does not catch traps — the judge does, by design.** The classifier only sees surface features (length, verbs, punctuation, and the like); a trap is built to look like an easy request on exactly those features. Stating this plainly is part of the honesty bar, not a limitation to hide.
- **The judge is always the tier above, sampled, and never grades its own tier's work.** No model marks its own answer.
- **The local tier's model calls run with thinking mode explicitly turned off.** Left on, hidden reasoning tokens inflate the very latency and cost numbers this project exists to report honestly.

## 5. Out of scope

- **Fronting the operator's own coding-agent subscription through this router.** Considered and dropped — subscription auth for a coding agent cannot be pointed at a custom gateway without forwarding session credentials, which is not something this project will do. Nothing here is sized for it.
- **A feature that lets the classifier see semantic meaning (e.g. an embedding-based feature).** Traps are caught by the judge instead (§4); this keeps the classifier cheap and simple, which is the point of having a first-pass classifier at all.
- **Hosted or public deployment.** This runs locally, for one user, against one person's own subscription and own machine. Making it available to other people over the internet is a different project with different auth (an API key, not subscription auth) and isn't part of this scope.
- **A Streamlit dashboard.** The audit log and replay-and-diff are surfaced through a web dashboard instead; which toolkit builds that dashboard is a technology decision that belongs in `Tech_Scope.md`, not here.

## 6. Phases and the cut line

| Phase | Covers | What "done" means |
|---|---|---|
| **Phase A** | Provider wiring, the tier registry, the classifier and its training script, the synchronous request lifecycle (classify → route → answer → audit) — plus getting ≥60 requests hand-labelled | The synchronous path answers a real request end to end, on labelled data, with tests green. This is the smallest version of the router that is actually a router. |
| **Phase B** | The background judge and escalation, the replay read API, the web dashboard (audit list → decision detail → replay-and-diff → savings), the full labelled-data run, and the README's honest numbers | The safety net, the replay capability, and the recruiter-facing surface all exist and are demoed against real recorded runs. |

**The cut line sits at the end of Phase A.** If nothing beyond Phase A ever gets built, what exists is still complete and presentable: a router that classifies, routes, answers, and logs why — just without the safety net or the replay debugger. Phase B is what turns that into the thing described in §2; it is not needed to make Phase A honest or demoable on its own.

## 7. Open questions

None outstanding — D1–D10 in SPRINT-PLAN.md §2 resolve every product decision this document depends on.
