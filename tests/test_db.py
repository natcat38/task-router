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
