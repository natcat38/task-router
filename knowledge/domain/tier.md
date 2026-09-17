---
type: Domain Entity
title: Tier
description: One of three answering levels a request can be routed to — local, Sonnet, or Opus — ordered cheapest to most capable.
resource: docs/Tech_Scope.md
tags: [domain, routing, cost]
timestamp: 2026-09-18T00:00:00Z
---

# Schema

Three tiers, in order:

1. **local** — `qwen3:1.7b` via Ollama's native `/api/chat`, always called with
   `"think": false`. Free, run on the operator's own machine.
2. **sonnet** — `claude -p --model sonnet`, authenticated via the operator's
   own Claude subscription (OAuth), never `--bare`.
3. **opus** — `claude -p --model opus`, same subscription auth. The top of
   the chain; nothing judges an Opus answer.

# Examples

`registry.yaml` lists each tier's model id and its API list price per million
input/output tokens. Every request's audit row records what it would have
cost at all three tiers (`cost_all_tiers`), even though only one tier's model
was actually called.

# Citations

The [classifier](/domain/classifier.md) picks a starting tier; the
[judge](/domain/judge.md) can escalate a request exactly one tier up; a
[replay](/domain/replay.md) forces a tier and re-runs the pipeline against it.
See `docs/adr/0003-provider-auth-subscription-with-apikey-slot.md` for why
cloud tiers run on subscription auth, not a metered API key.
