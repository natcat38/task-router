# 0002: Replay re-runs the whole router pipeline with a forced tier, non-deterministically

## Status
Accepted

## Context
The project's differentiator over existing LLM observability tooling is a "replay and diff" feature. It would be easy to overclaim novelty here: Phoenix's Span Replay and Langfuse's Playground both already let a user take a stored prompt and re-run it against a different model (`SPRINT-PLAN.md` §1, `REFUTATIONS.md` #3). If this project's replay is described only as "replay with a different model," it duplicates existing, shipped tooling and a reviewer who knows either product will call it out.

What neither Phoenix nor Langfuse does is replay the *router's own decision*: they swap the model on a stored span/prompt directly, bypassing classification entirely. Nothing in either product re-runs `classify → select_tier → answer` and its downstream judge/escalate logic with one part of that pipeline pinned. `REFUTATIONS.md` #3 requires the plan to narrow its claim to exactly this gap.

## Decision
Replay takes a stored request (`source_run_id`) and a `forced_tier`, then re-runs it through the **entire** router pipeline — `classify → select_tier → answer`, followed by the same judge/escalate logic that a live request would go through — with `select_tier`'s output overridden to `forced_tier` instead of whatever the classifier would have chosen. The result is diffed against the original run's stored row (tier, answer, judge score, cost). This is pipeline replay, not span replay: the classifier still runs (so its output is visible in the diff even though it's overridden), and escalation can still fire on the forced-tier answer.

Replay is explicitly **not deterministic**. Model outputs vary run to run even with the same prompt and tier, so re-running the same `source_run_id` and `forced_tier` twice can produce two different answers, judge scores, and possibly different escalation outcomes. The UI and README must not imply a replay reproduces the original run bit-for-bit — it reproduces the *routing decision path*, not the exact output.

## Consequences
- The README's claim is narrowed to: "this replays the router's tier decision through judge/escalate; Phoenix and Langfuse replay a swapped-model span, not a routing decision." This is defensible against a reviewer who checks either product.
- Because replay is non-deterministic, the "diff" view must present the replayed run as a new, separate row (its own judge score, its own escalation outcome) rather than as a corrected version of the original — treating it as authoritative would silently misrepresent variance as signal.
- Replay cost is real: forcing a tier still calls that tier's model, and if the forced tier triggers escalation, that runs too. Replays are not free re-checks and should be budgeted the same as any other `claude -p` call.

## Alternatives Considered

### Span-only replay (swap model on the stored prompt, matching Phoenix/Langfuse)
- Pros: simpler to build, matches existing prior art exactly.
- Cons: this is the feature that already exists elsewhere; building it would not differentiate this project and the README could not claim anything new.
- Rejected: duplicates existing tooling with no added value.

### Deterministic replay (cache/pin the original model outputs, replay only the routing logic)
- Pros: reproducible diffs, cheaper (no repeat model calls).
- Cons: doesn't actually exercise the forced tier's model — it would just recompute a routing decision against pre-recorded text, which can't show what a different tier's *answer* would have looked like, defeating the point of "what if this had gone to a different tier."
- Rejected: the whole value of forced-tier replay is seeing a real answer from the forced tier, which requires a live call and therefore non-determinism.
