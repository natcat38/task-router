---
type: Domain Entity
title: Classifier
description: The 8-feature LogisticRegression first pass that assigns a tier to a request without calling any model.
resource: docs/Tech_Scope.md
tags: [domain, routing, ml]
timestamp: 2026-09-18T00:00:00Z
---

# Schema

`features.py` computes 8 surface features from the raw request, no model call
involved:

1. length (token or char count)
2. instruction-verb count
3. constraint count (numeric/format constraints stated)
4. supplied-context present (boolean)
5. output-format specified (boolean/enum)
6. reasoning-word count ("because", "therefore", "step", ...)
7. question count
8. numeric-token count

A `LogisticRegression` trained on hand-labelled requests (`train.py`) scores
the feature vector and picks one of the three [tiers](/domain/tier.md).

# Examples

Request: "Summarise this changelog into three bullet points." → length low,
1 instruction verb, context attached, output-format specified → classifier
picks `local`.

# Citations

Because all 8 features are surface-only, the classifier cannot see semantic
traps by construction — a trap is built to look like an easy request on
exactly these numbers. Trap detection is the [judge](/domain/judge.md)'s job,
not the classifier's. See `docs/adr/0001-judge-tier-above-sampled.md`.
