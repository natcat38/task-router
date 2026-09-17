"""db.py schema init (Tech_Scope.md §2 / otel-replay-options.md §4)."""

from __future__ import annotations

from task_router import db as db_module


def test_get_connection_creates_runs_spans_replays_tables(tmp_path):
    conn = db_module.get_connection(tmp_path / "audit.sqlite")
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"runs", "spans", "replays"} <= tables


def test_get_connection_is_idempotent_against_same_file(tmp_path):
    path = tmp_path / "audit.sqlite"
    db_module.get_connection(path)
    conn2 = db_module.get_connection(path)  # must not raise on re-init
    assert conn2.execute("SELECT 1").fetchone()[0] == 1


def test_runs_table_has_judge_cost_column_with_default(tmp_path):
    """S4 (judge cost counted in savings, Tech_Scope §5) adds `judge_cost`
    to `runs`. A pre-existing run row (inserted without the column) must
    still default to 0, not null, so GET /v1/stats can sum it unconditionally."""
    conn = db_module.get_connection(tmp_path / "audit.sqlite")
    conn.execute(
        "INSERT INTO runs (run_id, created_at, input_text, tier_chosen, "
        "model_used, status) VALUES ('r1','now','hi','local','qwen3:1.7b','ok')"
    )
    conn.commit()
    row = conn.execute("SELECT judge_cost FROM runs WHERE run_id='r1'").fetchone()
    assert row["judge_cost"] == 0


def test_init_db_migrates_a_pre_s4_db_missing_judge_cost(tmp_path):
    """Simulates a DB file created before S4 (RUNS_SCHEMA without
    judge_cost) -- init_db() must add the column rather than erroring on
    the next `get_connection()` call against that same file."""
    import sqlite3

    path = tmp_path / "audit.sqlite"
    pre_s4_conn = sqlite3.connect(path)
    pre_s4_conn.execute(
        "CREATE TABLE runs (run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
        "input_text TEXT NOT NULL, tier_chosen TEXT NOT NULL, model_used TEXT "
        "NOT NULL, status TEXT NOT NULL)"
    )
    pre_s4_conn.commit()
    pre_s4_conn.close()

    conn = db_module.get_connection(path)  # must not raise
    cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    assert "judge_cost" in cols
