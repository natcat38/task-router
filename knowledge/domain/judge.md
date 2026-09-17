---
type: Domain Entity
title: Judge
description: The async, sampled quality check that scores a routed answer using the tier one level above the tier that answered.
resource: docs/adr/0001-judge-tier-above-sampled.md
tags: [domain, routing, quality]
timestamp: 2026-09-18T00:00:00Z
---

# Schema

The judge runs after the answer is already returned to the caller — it never
blocks the response. It always uses the [tier](/domain/tier.md) one level
above the tier that answered: local answers are judged by Sonnet, Sonnet
answers are judged by Opus. Opus answers are unjudged — there is no tier
above Opus. No tier ever grades its own output.

Judging runs on a configurable `judge_sample_rate` (1.0 during the initial
labelled battery), not on every request, so the judge's own cost stays
visible rather than assumed free. A score below the request's use-case
threshold triggers escalation exactly one tier up (never straight to the
top), and the escalated answer replaces the original in the audit record.

# Examples

A `local`-tier answer scores 2/5 against a `summarise` threshold of 4 →
escalates to `sonnet`; the Sonnet answer replaces `output_text` and
`escalation_chain` records `{tier: sonnet, reason: "judge_score=2<4"}`.

# Citations

Because the [classifier](/domain/classifier.md) cannot see semantic traps,
the judge is the layer that catches them. Judge tokens are counted in the
savings figure reported by `GET /v1/stats`, both with and without them
included. A [replay](/domain/replay.md) re-runs judge/escalate logic too.
