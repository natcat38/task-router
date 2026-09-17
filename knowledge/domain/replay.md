---
type: Domain Entity
title: Replay
description: Re-running a past request through the whole router pipeline with one tier forced, then diffing the outcome against what actually happened.
resource: docs/adr/0002-replay-forced-tier-diff.md
tags: [domain, replay, debugging]
timestamp: 2026-09-18T00:00:00Z
---

# Schema

`POST /replay {source_run_id, forced_tier}` re-runs `classify → select_tier
→ answer`, then the same judge/escalate logic a live request would go
through, with `select_tier`'s output overridden to `forced_tier`. The
classifier still runs — its real output is visible in the diff even though
it is overridden. The result is diffed against the original run's stored
row: tier, model, output, judge score.

Replay is explicitly **not deterministic** — model outputs vary run to run,
so replaying the same `source_run_id`/`forced_tier` twice can produce two
different answers or escalation outcomes. A replay is stored as a new row,
never presented as a corrected version of the original.

# Examples

A request originally answered by `local` is replayed with `forced_tier:
opus` → the diff shows `tier_changed: true`, a new judge score (or none,
since Opus is unjudged), and whether the output text changed.

# Citations

This is pipeline replay, not span replay: existing LLM-observability tools
swap the model on a stored prompt and skip classification entirely. See
[tier](/domain/tier.md) for the tiers a replay can force and
[judge](/domain/judge.md) for the logic replay re-runs downstream of the
forced tier.
