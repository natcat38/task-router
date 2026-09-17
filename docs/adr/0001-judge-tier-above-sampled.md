# 0001: Async judge is the tier above the answering tier, sampled

## Status
Accepted

## Context
The router needs a quality check on routed answers so bad cheap-tier answers get caught and escalated. The original design (`task-router-artifact.md` §01–§02, the shared "Glitch Cat Club" artifact) used a single all-Opus judge for every tier: local and Sonnet answers were both scored by Opus, with sampling framed as a future optimization ("proof verified 100%; in production verify a sample and dial down as trust grows," §02).

That design has a bias problem the artifact never addresses: when the router picks Sonnet, having Sonnet judge Sonnet's own answer is self-grading, and self-grading bias is well documented (`REFUTATIONS.md` #15). An all-Opus judge avoids self-grading only by cost — every judged request pays for an Opus call regardless of which tier answered, which erases the point of routing to a cheap tier in the first place.

## Decision
The async judge is always the tier **one above** the tier that answered: local answers are judged by Sonnet, Sonnet answers are judged by Opus, Opus answers are unjudged (there is no tier above Opus). Judging runs at a configurable `judge_sample_rate` in `routing.yaml`, set to 1.0 for the initial battery so every routed answer is checked while the classifier is unproven; it is expected to drop as trust in the classifier grows.

## Consequences
- No tier ever grades its own output, which removes the self-grading bias present in same-tier judging.
- Opus answers go unjudged by construction — there is no tier above Opus to catch a bad Opus answer. This is accepted as a gap, not solved here.
- Judge tokens are counted in the savings figure. A local-tier answer that gets judged by Sonnet still costs one Sonnet call, so the "saved vs all-Opus" stat is reported both with and without judge tokens included; reporting only the without-judge number would overstate savings.
- The classifier is a cheap surface-feature first pass (length, verbs, constraints, context, format, reasoning words, questions, numbers) and cannot see semantic traps by construction (`REFUTATIONS.md` #14). Trap detection is the judge's job, not the classifier's — a trap that slips past classification is still caught (and escalated) by the tier-above judge scoring it low. The README and this ADR both state this explicitly so a reviewer does not mistake trap-catching for a classifier feature.

## Alternatives Considered

### All-Opus judge (the artifact's original design)
- Pros: single fixed judge tier, no self-grading, simple to reason about.
- Cons: doubles cost on every judged local-tier request relative to a tier-above scheme's local→Sonnet hop; still leaves a savings figure that undercounts true cost when judge tokens aren't reported.
- Rejected: not because it is wrong, but because it hides the judge cost inside a flat "verified" step rather than making the marginal judge cost visible per tier, which is what the savings-honesty requirement (D10) needs.

### Same-tier judge (Sonnet judges Sonnet, Opus judges Opus)
- Pros: cheapest possible judging.
- Cons: self-grading bias (REFUTATIONS #15) — a model is least likely to catch its own systematic errors.
- Rejected on bias grounds alone.
