"""S8: the committed demo fixture (`data/fixtures/demo.sqlite`) must exist,
load, and contain representative rows so the UI can demo with no model
running -- and regenerating it via `scripts/make_demo_fixture.py` must be
deterministic (same bytes in, same rows out), so it never silently drifts
from what's committed.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from make_demo_fixture import make_demo_fixture  # noqa: E402

FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "demo.sqlite"


def _row_tuples(conn: sqlite3.Connection, table: str) -> list[tuple]:
    return sorted(
        tuple(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()
    )


def test_committed_fixture_exists_and_loads():
    assert FIXTURE_PATH.exists(), (
        "data/fixtures/demo.sqlite is missing -- run "
        "`uv run python scripts/make_demo_fixture.py` and commit it"
    )
    conn = sqlite3.connect(FIXTURE_PATH)
    conn.row_factory = sqlite3.Row
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"runs", "spans", "replays"} <= tables

    runs = conn.execute("SELECT * FROM runs").fetchall()
    spans = conn.execute("SELECT * FROM spans").fetchall()
    replays = conn.execute("SELECT * FROM replays").fetchall()

    assert len(runs) >= 5
    assert len(spans) > 0
    assert len(replays) >= 1

    tiers = {row["tier_chosen"] for row in runs}
    assert {"local", "sonnet", "opus"} <= tiers, (
        "fixture must cover all three tiers, per S8"
    )
    assert any(row["escalated"] for row in runs), (
        "fixture must include at least one escalated run, per S8"
    )
    assert any(row["forced_tier"] is not None for row in runs), (
        "fixture must include at least one replay-produced run "
        "(forced_tier set), per S8"
    )


def test_regenerating_the_fixture_is_deterministic(tmp_path):
    out1 = make_demo_fixture(tmp_path / "a.sqlite")
    out2 = make_demo_fixture(tmp_path / "b.sqlite")

    conn1 = sqlite3.connect(out1)
    conn2 = sqlite3.connect(out2)
    for table in ("runs", "spans", "replays"):
        assert _row_tuples(conn1, table) == _row_tuples(conn2, table), (
            f"table {table!r} differs between two fresh runs of "
            "make_demo_fixture -- it must be deterministic"
        )


def test_committed_fixture_matches_a_fresh_regeneration(tmp_path):
    """Guards against the committed .sqlite drifting from what the script
    currently produces (e.g. someone edits the script but forgets to
    re-run and re-commit the fixture)."""
    fresh = make_demo_fixture(tmp_path / "fresh.sqlite")

    committed_conn = sqlite3.connect(FIXTURE_PATH)
    fresh_conn = sqlite3.connect(fresh)
    for table in ("runs", "spans", "replays"):
        assert _row_tuples(committed_conn, table) == _row_tuples(fresh_conn, table), (
            f"committed data/fixtures/demo.sqlite's {table!r} table doesn't "
            "match scripts/make_demo_fixture.py's current output -- "
            "regenerate and recommit the fixture"
        )
