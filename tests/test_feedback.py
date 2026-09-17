"""Tests for feedback.py (Tech_Scope.md §5 S7 row; Product_Scope.md §3.2):
an escalated run that was ultimately CONFIRMED PASSING becomes exactly one
weight-3 training row labelled with the tier that passed. A run that never
escalated, or one that escalated all the way to opus without ever being
re-judged (ADR 0001: opus is unjudged, top of the chain), contributes
nothing -- there is no confirmed-good label to teach from.
"""

from __future__ import annotations

import json

import feedback
from task_router import db as db_module


def _run(run_id, *, tier_chosen, use_case, input_text, escalated, judge_label, escalation_chain):
    return {
        "run_id": run_id,
        "tier_chosen": tier_chosen,
        "use_case": use_case,
        "input_text": input_text,
        "escalated": escalated,
        "judge_label": judge_label,
        "escalation_chain": escalation_chain,
    }


def test_escalated_and_passed_run_becomes_weight_3_feedback_row():
    runs = [
        _run(
            "r1", tier_chosen="sonnet", use_case="summarise", input_text="Summarise this thing.",
            escalated=1, judge_label="pass",
            escalation_chain=[{"tier": "sonnet", "model": "sonnet", "reason": "judge_score=2<4"}],
        ),
    ]

    rows = feedback.extract_feedback_rows(runs)

    assert len(rows) == 1
    row = rows[0]
    assert row["tier"] == "sonnet"  # labelled with the tier that PASSED
    assert row["weight"] == 3
    assert row["prompt"] == "Summarise this thing."
    assert row["use_case"] == "summarise"
    assert row["id"] == "feedback-r1"
    assert row["trap"] is False


def test_non_escalated_run_contributes_no_feedback_row():
    runs = [
        _run("r1", tier_chosen="local", use_case="extract", input_text="x",
             escalated=0, judge_label="pass", escalation_chain=None),
    ]
    assert feedback.extract_feedback_rows(runs) == []


def test_escalated_but_never_confirmed_passing_contributes_no_feedback_row():
    """Escalated all the way to opus (unjudged, ADR 0001) -- judge_label
    never becomes "pass", so there is no confirmed-good label to train on."""
    runs = [
        _run(
            "r1", tier_chosen="opus", use_case="reason", input_text="x",
            escalated=1, judge_label="escalated",
            escalation_chain=[
                {"tier": "sonnet", "model": "sonnet", "reason": "judge_score=2<4"},
                {"tier": "opus", "model": "opus", "reason": "judge_score=2<4"},
            ],
        ),
    ]
    assert feedback.extract_feedback_rows(runs) == []


def test_multiple_runs_only_qualifying_ones_produce_rows():
    runs = [
        _run("r1", tier_chosen="sonnet", use_case="summarise", input_text="a",
             escalated=1, judge_label="pass", escalation_chain=[{"tier": "sonnet", "model": "sonnet", "reason": "x"}]),
        _run("r2", tier_chosen="local", use_case="extract", input_text="b",
             escalated=0, judge_label="pass", escalation_chain=None),
        _run("r3", tier_chosen="opus", use_case="reason", input_text="c",
             escalated=1, judge_label="escalated", escalation_chain=[{"tier": "opus", "model": "opus", "reason": "x"}]),
    ]
    rows = feedback.extract_feedback_rows(runs)
    assert [r["id"] for r in rows] == ["feedback-r1"]


def test_build_feedback_reads_runs_from_db(tmp_path):
    conn = db_module.get_connection(tmp_path / "audit.sqlite")
    conn.execute(
        "INSERT INTO runs (run_id, created_at, input_text, use_case, tier_chosen, "
        "model_used, output_text, status, escalated, judge_label, escalation_chain) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "r1", "2026-01-01T00:00:00+00:00", "Summarise this.", "summarise", "sonnet",
            "sonnet", "answer", "ok", 1, "pass",
            json.dumps([{"tier": "sonnet", "model": "sonnet", "reason": "judge_score=2<4"}]),
        ),
    )
    conn.commit()

    rows = feedback.build_feedback(tmp_path / "audit.sqlite")

    assert len(rows) == 1
    assert rows[0]["tier"] == "sonnet"
    assert rows[0]["weight"] == 3


def test_save_feedback_writes_json_file(tmp_path):
    rows = [
        {"id": "feedback-r1", "tier": "sonnet", "use_case": "summarise",
         "prompt": "x", "trap": False, "notes": "", "weight": 3},
    ]

    path = feedback.save_feedback(rows, tmp_path / "feedback.json")

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == rows


def test_main_writes_feedback_file_and_reports_count(tmp_path, capsys):
    conn = db_module.get_connection(tmp_path / "audit.sqlite")
    conn.execute(
        "INSERT INTO runs (run_id, created_at, input_text, use_case, tier_chosen, "
        "model_used, output_text, status, escalated, judge_label) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("r1", "2026-01-01T00:00:00+00:00", "x", "extract", "local", "qwen3:1.7b", "y", "ok", 0, "pass"),
    )
    conn.commit()

    exit_code = feedback.main(
        ["--db-path", str(tmp_path / "audit.sqlite"), "--feedback-path", str(tmp_path / "feedback.json")]
    )

    assert exit_code == 0
    assert (tmp_path / "feedback.json").exists()
    assert "0 feedback row(s)" in capsys.readouterr().out
