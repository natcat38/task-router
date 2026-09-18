# Backend code review — REVIEW stage

Scope: `api.py`, `battery.py`, `feedback.py`, `train.py`, `src/task_router/*`
(providers, registry, classifier, features, judge, tracing, db, local_request,
routing_config). UI and docs excluded. Reviewed against `docs/Tech_Scope.md`
§3/§4, ADR 0001 (judge), ADR 0002 (replay), `docs/Product_Scope.md` §4
(honesty rules).

Skills run, in order: `agent-skills:code-review-and-quality`,
`agent-skills:code-simplification`, `agent-skills:doubt-driven-development`
(applied to the judge scheme and replay semantics). This session is a
non-interactive Sonnet subagent, so doubt-driven's fresh-context-reviewer
spawn was unavailable per that skill's own Loading Constraints (nested
subagent spawn is blocked); the degraded self-questioning fallback was used
instead, and cross-model review was skipped and is announced here rather
than silently omitted, per the skill's non-interactive rule.

## Findings, ranked

### 1. [HIGH — reported, not fixed] Escalation's real cost is never recorded; `GET /v1/stats` under/over-states savings on escalated runs

`judge.py:223` calls `reanswer = send_fn(prompt, judge_model.id)` to produce
the escalated tier's actual answer. `reanswer["cost"]` — the real dollar cost
of that call — is read nowhere: it isn't added to `total_judge_cost`
(`judge.py:181/203`, which only accumulates the *grading* calls' cost), and
it isn't written to any column. It is silently dropped.

Meanwhile `GET /v1/stats` (`api.py:357-367`) computes "actual cost" for each
row as `cost_all_tiers[tier_chosen]`. `cost_all_tiers` is frozen once, at
`api.py:229-234`, *before* the judge/escalation step runs, using the
token counts of the *original* (pre-escalation) answer. `judge.py:257`
later overwrites `tier_chosen` to the escalated tier. So for any escalated
run, `GET /v1/stats` looks up `cost_all_tiers[<new tier>]` — a hypothetical
"what would this same-length exchange have cost at that tier" figure
computed from the *wrong* answer's token counts — not the real cost of the
real escalation call. The real escalation cost is not represented in
`saved_pct_excl_judge` or `saved_pct_incl_judge` at all.

This is a genuine honesty-contract gap (`Product_Scope.md` §4: savings
figures must not be overstated, judge cost must be counted, "neither figure
is hidden") — the escalation-answer's own real cost is hidden by omission,
independent of the pre-existing `cost_all_tiers` estimate issue.

**Why reported instead of fixed:** `tests/test_battery.py:240-273`
(`test_compute_summary_matches_hand_computed_savings`) explicitly asserts
today's `cost_all_tiers[tier_chosen]` behavior as the expected formula for
an escalated row. Correcting this requires a schema/design decision (e.g. a
new `answer_cost` column written once at insert time, plus an
`escalation_cost` column accumulated in `judge.py`'s `UPDATE` at
`judge.py:248-263`, with `GET /v1/stats` summing those instead of indexing
`cost_all_tiers`) that also means rewriting the test above to match the
corrected semantics. That's a product decision, not a "clearly-correct,
safe" fix, so it is reported per the task's fix-only-high-confidence rule
rather than applied.

**Recommended fix (for the operator):**
1. `db.py`: add `answer_cost REAL NOT NULL DEFAULT 0` and
   `escalation_cost REAL NOT NULL DEFAULT 0` to `RUNS_SCHEMA` +
   `_ensure_column` migrations.
2. `api.py` INSERT (`api.py:236-255`): persist `answer_cost = cost_all_tiers[tier]`
   (the real cost of the call that was just made).
3. `judge.py`: accumulate `reanswer["cost"]` into a new
   `total_escalation_cost` and persist it as `escalation_cost` in the
   `UPDATE` at `judge.py:248-263`.
4. `api.py` `get_stats` (`api.py:346-367`): compute
   `actual_cost_excl_judge` from `answer_cost + escalation_cost`, not
   `cost_all_tiers[tier_chosen]`.
5. Update `tests/test_battery.py`'s hand-computed-savings test and
   `tests/test_judge.py` to assert the new columns.

### 2. [MEDIUM — fixed] `providers.py` could raise out of `send()` on malformed `claude -p` JSON, violating the "never raises" contract

`providers.py:_send_claude_cli` (pre-fix) extracted `usage["input_tokens"]`/
`usage["output_tokens"]` inside a `try/except (KeyError, TypeError)`, then
called `cost_fn(model_id, input_tokens, output_tokens)` **outside** that
block. `Registry.cost()` (`registry.py:52-54`) does `input_tokens / 1_000_000`
directly — if `claude -p`'s JSON had the right shape but a wrong-typed value
(e.g. `"input_tokens": "100"` as a string), that division raises `TypeError`
uncaught, propagating out of `send()` and up into `judge.run_judge()` /
`api.py`'s completions handler. `Tech_Scope.md` §1/§6 states `send()` "never
raises" as a hard interface guarantee every caller relies on to skip
try/except.

**Fix applied:** coerce `input_tokens`/`output_tokens` with `int(...)` inside
the existing try/except (now also catching `ValueError`), and wrap the
`cost_fn(...)` call in its own try/except so any computation failure still
returns the normal `_empty_error_result(...)` shape instead of raising.
Test added: `tests/test_providers.py::test_send_claude_cli_non_numeric_usage_becomes_error_field`.

### 3. [LOW — fixed] Fabricated spec citation in `judge.py`'s docstring

`judge.py:11-14` (pre-fix) quoted `Tech_Scope §3 step 7` as saying *"if
still under threshold and another tier remains, escalate again one step"* —
that exact sentence does not exist anywhere in `docs/Tech_Scope.md` (verified
by grepping the whole `docs/` tree for the phrase; no match). The
*behavior* it describes is correct and well-tested (multi-hop escalation,
e.g. local → sonnet → judged again by opus, exercised end-to-end in
`tests/test_judge.py:208-234`), and it's genuinely supported by real
citations — `Tech_Scope.md` §2 typing `escalation_chain` as an *array* of
`{tier, model, reason}`, and `Product_Scope.md` §3.2's "escalated one tier
at a time" — just not by the quoted sentence, which was invented.

**Fix applied:** reworded the docstring to cite the real basis instead of a
fabricated quotation. Behavior-preserving, doc-only change.

### 4. [LOW — reported only, pre-existing and already documented] `PUT /v1/routing-config` doesn't implement the `409`-on-race contract

`Tech_Scope.md` §4 specifies `409` "if two `PUT`s race." `routing_config.py`
does plain last-write-wins with no race detection, and its own module
docstring (`routing_config.py:4-8`) already says this was deliberately
deferred as not worth building for a single-user local tool. Not a silent
bug — it's a documented, accepted gap from a prior pass — but it is a real,
current divergence from the written API contract. Flagging for visibility
only; no change made (implementing real concurrency control, e.g. an ETag
or file lock, is a design decision, not a safe mechanical fix).

## Verified clean under doubt-driven scrutiny (judge scheme + replay semantics)

- **Judge tier-above, never same-tier, opus never judged**
  (`judge.py:40,47-50,189`) — matches ADR 0001, fully covered by
  `tests/test_judge.py:114-124,280-297`.
- **Escalation never skips a tier**; chaining beyond one hop only happens by
  re-judging the newly-escalated answer each loop iteration
  (`judge.py:186-243`) — this is intentional (matches the array-typed
  `escalation_chain` schema, see Finding 3) and is tested, not a bug.
- **Judge cost counted even when the reply is unparseable**
  (`judge.py:107-125`, tested at `tests/test_judge.py:192-203`) — matches
  ADR 0001's "judge tokens counted regardless of score outcome."
- **Replay re-runs the whole pipeline**, not a span/model swap: `api.py`'s
  `_run_pipeline` (shared by `/v1/completions` and `/replay`) runs
  classify → select_tier(forced) → answer → judge/escalate against the
  source run's stored `input_text`/`use_case`, produces a brand-new
  `run_id`/spans row, and is diffed against the source's *final* persisted
  values (`api.py:133-148`) — matches ADR 0002 exactly, including "new row,
  never a correction" and the non-determinism framing.
- **OTel `run_id == trace_id`**, and judge/escalate spans are explicitly
  re-parented under the captured root span context since they run outside
  the ambient span context of a `BackgroundTask` (`judge.py:168`,
  `api.py:199-204`) — correct, tested at
  `tests/test_api_completions.py:70-94`.
- **Labelled-rows filter**: `train.filter_labelled` (`train.py:66-68`) is
  the single source of truth, and `battery.py:175-181` explicitly reuses it
  rather than re-deriving the same check, so the two scripts can't drift.
- `providers.send()` dispatch, `--bare` avoidance, API-key-env stripping,
  `think: false` pinning (`local_request.py`), and the fake-provider test
  seam are all correctly implemented and tested.

## Verification

- `uv run pytest -q`: **162 passed**, 0 failed (includes the 1 new
  regression test added by this review).
- No other files in scope were modified.
