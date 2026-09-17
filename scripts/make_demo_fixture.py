"""Builds `data/fixtures/demo.sqlite` -- a deterministic, synthetic fixture
so the UI (and anyone cloning this repo) can see the dashboard fully
populated without Ollama running or a `claude -p` subscription on hand.

This is NOT battery output. The live routing/saving battery (`battery.py`)
has not been run yet -- the operator held it (see README "Battery status").
Every row here is hand-written, labelled synthetic below, so nobody mistakes
a demo screenshot for a real result.

Coverage (S8 requirement): at least one run per tier (local/sonnet/opus),
one escalation (local judged below threshold, escalated to sonnet), and one
replay pair (a stored run replayed with a forced tier, linked via the
`replays` table) -- Tech_Scope.md §2 schema, ADR 0001 (judge = tier above)
and ADR 0002 (pipeline replay).

Usage:
    uv run python scripts/make_demo_fixture.py

Deterministic: fixed run/span ids and timestamps, so re-running this script
produces byte-identical rows every time (verified by
tests/test_demo_fixture.py). The script deletes and rebuilds the file from
scratch rather than upserting, so it never accumulates stale rows.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from task_router import db as db_module  # noqa: E402

FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "demo.sqlite"

# A fixed base timestamp so every row's created_at is deterministic across
# runs -- this is a demo fixture, not a record of when anyone actually ran
# anything.
_BASE_TS = "2026-09-17T09:{minute:02d}:00+00:00"


def _ts(minute: int) -> str:
    return _BASE_TS.format(minute=minute)


def _ns(seconds_from_base: float) -> int:
    """Deterministic nanosecond timestamps for span start/end, spaced out
    so the waterfall view has plausible-looking (but fake) durations."""
    return int(seconds_from_base * 1_000_000_000)


COST_ALL_TIERS_TEMPLATE = {"local": 0.0, "sonnet": 0.00042, "opus": 0.00135}


def _insert_run(conn: sqlite3.Connection, **fields) -> None:
    columns = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    conn.execute(
        f"INSERT INTO runs ({columns}) VALUES ({placeholders})",
        list(fields.values()),
    )


def _insert_span(
    conn: sqlite3.Connection,
    *,
    span_id: str,
    run_id: str,
    parent_span_id,
    name: str,
    start_ns: int,
    end_ns: int,
    attributes: dict,
    status: str = "OK",
) -> None:
    conn.execute(
        "INSERT INTO spans (span_id, run_id, parent_span_id, name, start_ns, "
        "end_ns, attributes, status) VALUES (?,?,?,?,?,?,?,?)",
        (
            span_id,
            run_id,
            parent_span_id,
            name,
            start_ns,
            end_ns,
            json.dumps(attributes),
            status,
        ),
    )


def _features(length: int, verbs: int = 1, questions: int = 0) -> dict:
    return {
        "length": length,
        "instruction_verb_count": verbs,
        "constraint_count": 0,
        "context_present": length > 40,
        "output_format_specified": False,
        "reasoning_word_count": 0,
        "question_count": questions,
        "numeric_token_count": 0,
    }


def build_fixture(conn: sqlite3.Connection) -> None:
    # --- Run 1: local tier, clean pass, judged by sonnet and left alone ---
    run_local = "demo0000000000000000000000000001"
    _insert_run(
        conn,
        run_id=run_local,
        created_at=_ts(0),
        input_text="Reformat this list of names into 'Last, First' order:\nJohn Smith\nJane Doe",
        input_features=json.dumps(_features(14)),
        use_case="reformat",
        tier_chosen="local",
        model_used="qwen3:1.7b",
        output_text="Smith, John\nDoe, Jane",
        judge_score=5.0,
        judge_label="pass",
        escalated=0,
        escalation_chain=None,
        status="ok",
        total_duration_ms=812,
        cost_all_tiers=json.dumps(COST_ALL_TIERS_TEMPLATE),
        forced_tier=None,
        judge_cost=0.00042,
    )
    _insert_span(
        conn,
        span_id="demo0000000001",
        run_id=run_local,
        parent_span_id=None,
        name="router.classify",
        start_ns=_ns(0.0),
        end_ns=_ns(0.01),
        attributes={"router.features": json.dumps(_features(14))},
    )
    _insert_span(
        conn,
        span_id="demo0000000002",
        run_id=run_local,
        parent_span_id=None,
        name="router.select_tier",
        start_ns=_ns(0.01),
        end_ns=_ns(0.02),
        attributes={"router.tier": "local"},
    )
    _insert_span(
        conn,
        span_id="demo0000000003",
        run_id=run_local,
        parent_span_id=None,
        name="chat qwen3:1.7b",
        start_ns=_ns(0.02),
        end_ns=_ns(0.81),
        attributes={
            "gen_ai.provider.name": "ollama",
            "gen_ai.request.model": "qwen3:1.7b",
            "gen_ai.usage.input_tokens": 22,
            "gen_ai.usage.output_tokens": 9,
        },
    )
    _insert_span(
        conn,
        span_id="demo0000000004",
        run_id=run_local,
        parent_span_id=None,
        name="router.judge",
        start_ns=_ns(0.81),
        end_ns=_ns(1.9),
        attributes={"router.judge_tier": "sonnet", "gen_ai.request.model": "sonnet"},
    )

    # --- Run 2: sonnet tier, clean pass, judged by opus. Also the source
    # run for the replay pair below. ---
    run_sonnet = "demo0000000000000000000000000002"
    _insert_run(
        conn,
        run_id=run_sonnet,
        created_at=_ts(5),
        input_text=(
            "Summarise the following support ticket in two sentences for a "
            "weekly digest:\n\nCustomer reports the export button on the "
            "billing page returns a 500 error since yesterday's release. "
            "Affects all Pro-tier accounts. No workaround found yet."
        ),
        input_features=json.dumps(_features(58, verbs=1)),
        use_case="summarise",
        tier_chosen="sonnet",
        model_used="sonnet",
        output_text=(
            "Pro-tier customers are hitting a 500 error on the billing "
            "page's export button since yesterday's release, with no "
            "workaround yet."
        ),
        judge_score=5.0,
        judge_label="pass",
        escalated=0,
        escalation_chain=None,
        status="ok",
        total_duration_ms=2140,
        cost_all_tiers=json.dumps(COST_ALL_TIERS_TEMPLATE),
        forced_tier=None,
        judge_cost=0.00135,
    )
    _insert_span(
        conn,
        span_id="demo0000000005",
        run_id=run_sonnet,
        parent_span_id=None,
        name="router.classify",
        start_ns=_ns(5.0),
        end_ns=_ns(5.01),
        attributes={"router.features": json.dumps(_features(58))},
    )
    _insert_span(
        conn,
        span_id="demo0000000006",
        run_id=run_sonnet,
        parent_span_id=None,
        name="router.select_tier",
        start_ns=_ns(5.01),
        end_ns=_ns(5.02),
        attributes={"router.tier": "sonnet"},
    )
    _insert_span(
        conn,
        span_id="demo0000000007",
        run_id=run_sonnet,
        parent_span_id=None,
        name="chat sonnet",
        start_ns=_ns(5.02),
        end_ns=_ns(7.1),
        attributes={
            "gen_ai.provider.name": "anthropic",
            "gen_ai.request.model": "sonnet",
            "gen_ai.usage.input_tokens": 61,
            "gen_ai.usage.output_tokens": 34,
        },
    )
    _insert_span(
        conn,
        span_id="demo0000000008",
        run_id=run_sonnet,
        parent_span_id=None,
        name="router.judge",
        start_ns=_ns(7.1),
        end_ns=_ns(9.4),
        attributes={"router.judge_tier": "opus", "gen_ai.request.model": "opus"},
    )

    # --- Run 3: opus tier, top of the chain, never judged (ADR 0001) ---
    run_opus = "demo0000000000000000000000000003"
    _insert_run(
        conn,
        run_id=run_opus,
        created_at=_ts(10),
        input_text=(
            "Given these three vendor contracts, identify every clause that "
            "conflicts with our standard indemnification terms and explain "
            "why each one is a risk."
        ),
        input_features=json.dumps(_features(96, verbs=2)),
        use_case="analyse",
        tier_chosen="opus",
        model_used="opus",
        output_text=(
            "Three conflicting clauses found: (1) Vendor A caps liability "
            "below our floor, (2) Vendor B's indemnification excludes "
            "third-party IP claims, (3) Vendor C's termination clause "
            "voids our data-return guarantee."
        ),
        judge_score=None,
        judge_label=None,
        escalated=0,
        escalation_chain=None,
        status="ok",
        total_duration_ms=4360,
        cost_all_tiers=json.dumps(COST_ALL_TIERS_TEMPLATE),
        forced_tier=None,
        judge_cost=0.0,
    )
    _insert_span(
        conn,
        span_id="demo0000000009",
        run_id=run_opus,
        parent_span_id=None,
        name="router.classify",
        start_ns=_ns(10.0),
        end_ns=_ns(10.01),
        attributes={"router.features": json.dumps(_features(96))},
    )
    _insert_span(
        conn,
        span_id="demo0000000010",
        run_id=run_opus,
        parent_span_id=None,
        name="router.select_tier",
        start_ns=_ns(10.01),
        end_ns=_ns(10.02),
        attributes={"router.tier": "opus"},
    )
    _insert_span(
        conn,
        span_id="demo0000000011",
        run_id=run_opus,
        parent_span_id=None,
        name="chat opus",
        start_ns=_ns(10.02),
        end_ns=_ns(14.38),
        attributes={
            "gen_ai.provider.name": "anthropic",
            "gen_ai.request.model": "opus",
            "gen_ai.usage.input_tokens": 210,
            "gen_ai.usage.output_tokens": 88,
        },
    )

    # --- Run 4: local tier, judged below threshold, escalated to sonnet
    # (one-step escalation, ADR 0001 / Product_Scope §3.2) ---
    run_escalated = "demo0000000000000000000000000004"
    _insert_run(
        conn,
        run_id=run_escalated,
        created_at=_ts(15),
        input_text=(
            "Extract the total invoice amount and due date from this text "
            "and reply with just those two values:\n\nInvoice #4471. Net 30 "
            "from receipt. Balance due after the early-payment discount "
            "expires at end of month: see line 12 for the adjusted figure."
        ),
        input_features=json.dumps(_features(45, verbs=1)),
        use_case="extract",
        tier_chosen="sonnet",  # final tier after escalation
        model_used="sonnet",
        output_text="Total: $4,180.00. Due date: 30 days from receipt (adjusted figure on line 12 not resolved without the source document).",
        judge_score=4.0,
        judge_label="pass",
        escalated=1,
        escalation_chain=json.dumps(
            [{"tier": "sonnet", "model": "sonnet", "reason": "judge_score=2<4"}]
        ),
        status="ok",
        total_duration_ms=3120,
        cost_all_tiers=json.dumps(COST_ALL_TIERS_TEMPLATE),
        forced_tier=None,
        judge_cost=0.00042 + 0.00135,  # judged at local (sonnet call), then judged again post-escalation (opus call)
    )
    _insert_span(
        conn,
        span_id="demo0000000012",
        run_id=run_escalated,
        parent_span_id=None,
        name="router.classify",
        start_ns=_ns(15.0),
        end_ns=_ns(15.01),
        attributes={"router.features": json.dumps(_features(45))},
    )
    _insert_span(
        conn,
        span_id="demo0000000013",
        run_id=run_escalated,
        parent_span_id=None,
        name="router.select_tier",
        start_ns=_ns(15.01),
        end_ns=_ns(15.02),
        attributes={"router.tier": "local"},
    )
    _insert_span(
        conn,
        span_id="demo0000000014",
        run_id=run_escalated,
        parent_span_id=None,
        name="chat qwen3:1.7b",
        start_ns=_ns(15.02),
        end_ns=_ns(15.7),
        attributes={
            "gen_ai.provider.name": "ollama",
            "gen_ai.request.model": "qwen3:1.7b",
            "gen_ai.usage.input_tokens": 38,
            "gen_ai.usage.output_tokens": 11,
        },
    )
    _insert_span(
        conn,
        span_id="demo0000000015",
        run_id=run_escalated,
        parent_span_id=None,
        name="router.judge",
        start_ns=_ns(15.7),
        end_ns=_ns(17.9),
        attributes={
            "router.judge_tier": "sonnet",
            "gen_ai.request.model": "sonnet",
            "router.judge_score": 2,
        },
    )
    _insert_span(
        conn,
        span_id="demo0000000016",
        run_id=run_escalated,
        parent_span_id=None,
        name="router.escalate",
        start_ns=_ns(17.9),
        end_ns=_ns(18.0),
        attributes={"router.escalate_reason": "judge_score=2<4", "router.escalate_to_tier": "sonnet"},
    )
    _insert_span(
        conn,
        span_id="demo0000000017",
        run_id=run_escalated,
        parent_span_id=None,
        name="chat sonnet",
        start_ns=_ns(18.0),
        end_ns=_ns(20.1),
        attributes={
            "gen_ai.provider.name": "anthropic",
            "gen_ai.request.model": "sonnet",
            "gen_ai.usage.input_tokens": 51,
            "gen_ai.usage.output_tokens": 28,
        },
    )

    # --- Run 5: the replay of run_sonnet, forced to opus (ADR 0002:
    # pipeline replay, non-deterministic, new run_id, linked via `replays`) ---
    run_replay_new = "demo0000000000000000000000000005"
    _insert_run(
        conn,
        run_id=run_replay_new,
        created_at=_ts(25),
        input_text=(
            "Summarise the following support ticket in two sentences for a "
            "weekly digest:\n\nCustomer reports the export button on the "
            "billing page returns a 500 error since yesterday's release. "
            "Affects all Pro-tier accounts. No workaround found yet."
        ),
        input_features=json.dumps(_features(58)),
        use_case="summarise",
        tier_chosen="opus",
        model_used="opus",
        output_text=(
            "All Pro-tier accounts have been unable to export billing data "
            "since yesterday's release due to a 500 error on the export "
            "button; no workaround exists yet, so a hotfix should be "
            "prioritised."
        ),
        judge_score=None,  # opus is unjudged, same as any other opus run
        judge_label=None,
        escalated=0,
        escalation_chain=None,
        status="ok",
        total_duration_ms=3980,
        cost_all_tiers=json.dumps(COST_ALL_TIERS_TEMPLATE),
        forced_tier="opus",
        judge_cost=0.0,
    )
    _insert_span(
        conn,
        span_id="demo0000000018",
        run_id=run_replay_new,
        parent_span_id=None,
        name="router.classify",
        start_ns=_ns(25.0),
        end_ns=_ns(25.01),
        attributes={"router.features": json.dumps(_features(58))},
    )
    _insert_span(
        conn,
        span_id="demo0000000019",
        run_id=run_replay_new,
        parent_span_id=None,
        name="router.select_tier",
        start_ns=_ns(25.01),
        end_ns=_ns(25.02),
        attributes={"router.tier": "opus", "router.tier_forced": True},
    )
    _insert_span(
        conn,
        span_id="demo0000000020",
        run_id=run_replay_new,
        parent_span_id=None,
        name="chat opus",
        start_ns=_ns(25.02),
        end_ns=_ns(29.0),
        attributes={
            "gen_ai.provider.name": "anthropic",
            "gen_ai.request.model": "opus",
            "gen_ai.usage.input_tokens": 61,
            "gen_ai.usage.output_tokens": 41,
        },
    )

    diff_summary = {
        "tier_changed": True,
        "model_changed": True,
        "judge_score_delta": None,  # source was judged (5.0), replay (opus) is unjudged
        "output_changed": True,
    }
    conn.execute(
        "INSERT INTO replays (replay_id, source_run_id, forced_tier, "
        "new_run_id, created_at, diff_summary) VALUES (?,?,?,?,?,?)",
        (
            "demo-replay-0000000000000001",
            run_sonnet,
            "opus",
            run_replay_new,
            _ts(25),
            json.dumps(diff_summary),
        ),
    )


def make_demo_fixture(path: Path = FIXTURE_PATH) -> Path:
    """Delete any existing fixture file and rebuild it from scratch, so the
    result is byte-for-byte deterministic across runs (no leftover rows
    from a previous version of this script)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    conn = db_module.get_connection(path)
    try:
        build_fixture(conn)
        conn.commit()
    finally:
        conn.close()
    return path


if __name__ == "__main__":
    out = make_demo_fixture()
    print(f"wrote demo fixture: {out}")
