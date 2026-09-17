# Project Knowledge

task-router: routes each LLM request to a cheap tier by default, catches the
cheap tier's mistakes with an async judge, and replays past requests through
the whole pipeline under a forced tier.

## Domain

- [Tier](/domain/tier.md) — the three answering tiers (local, Sonnet, Opus) a request can be routed to.
- [Classifier](/domain/classifier.md) — the 8-feature LogisticRegression first pass that picks a tier before any model call.
- [Judge](/domain/judge.md) — the async, sampled quality check run by the tier above the one that answered.
- [Replay](/domain/replay.md) — re-running the whole router pipeline against a past request with a tier forced.
