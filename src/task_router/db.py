"""SQLite schema for the runs/spans (+ replays) audit-and-trace tables.

Tech_Scope.md §2 ("SQLite tables") and otel-replay-options.md §4 (the same
schema, restated). `runs` doubles as the OTel trace root and the audit
record -- `run_id` is the OTel trace_id, hex -- per Tech_Scope §2's "Calls
made" note explaining why this isn't split into two tables.

DB path comes from env `TASK_ROUTER_DB`, default `data/audit.sqlite`
(already gitignored). Call `init_db(get_connection())` once at process
start (api.py's `create_app()` does this); stdlib `sqlite3`, no ORM
(Tech_Scope §1).

`replays` is created here too even though S5 (replay read-API) is the slice
that reads/writes it -- the CREATE TABLE IF NOT EXISTS is trivial and one
schema-init call is simpler than two, so it costs nothing to have it exist
one slice early. No replay read/write code exists yet.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path("data") / "audit.sqlite"

RUNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    input_text TEXT NOT NULL,
    input_features TEXT,
    tier_chosen TEXT NOT NULL,
    model_used TEXT NOT NULL,
    output_text TEXT,
    judge_score REAL,
    judge_label TEXT,
    escalated INTEGER NOT NULL DEFAULT 0,
    escalation_chain TEXT,
    status TEXT NOT NULL,
    total_duration_ms INTEGER,
    cost_all_tiers TEXT,
    forced_tier TEXT,
    judge_cost REAL NOT NULL DEFAULT 0,
    use_case TEXT
)
"""

SPANS_SCHEMA = """
CREATE TABLE IF NOT EXISTS spans (
    span_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    parent_span_id TEXT,
    name TEXT NOT NULL,
    start_ns INTEGER NOT NULL,
    end_ns INTEGER NOT NULL,
    attributes TEXT,
    status TEXT
)
"""

REPLAYS_SCHEMA = """
CREATE TABLE IF NOT EXISTS replays (
    replay_id TEXT PRIMARY KEY,
    source_run_id TEXT NOT NULL REFERENCES runs(run_id),
    forced_tier TEXT NOT NULL,
    new_run_id TEXT NOT NULL REFERENCES runs(run_id),
    created_at TEXT NOT NULL,
    diff_summary TEXT
)
"""


def db_path(path: Optional[Path] = None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.environ.get("TASK_ROUTER_DB", str(DEFAULT_DB_PATH)))


def get_connection(path: Optional[Path] = None) -> sqlite3.Connection:
    """Open (creating the parent dir if needed) a connection with schema
    applied. Safe to call once per app/process; CREATE TABLE IF NOT EXISTS
    makes repeat calls against the same file idempotent."""
    p = db_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    """Add `column` to `table` if a pre-S4 DB file was created before this
    column existed. CREATE TABLE IF NOT EXISTS (above) only covers brand-new
    files; this covers the on-disk audit.sqlite an earlier slice already
    created."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(RUNS_SCHEMA)
    conn.execute(SPANS_SCHEMA)
    conn.execute(REPLAYS_SCHEMA)
    _ensure_column(conn, "runs", "judge_cost", "REAL NOT NULL DEFAULT 0")
    # S5: GET /runs needs a use_case filter (Tech_Scope §4), but no prior
    # slice persisted use_case on the runs row -- it was only ever a
    # request-time value passed to the judge job. Added here, nullable, so
    # pre-S5 DB files migrate cleanly (existing rows read back use_case=None).
    _ensure_column(conn, "runs", "use_case", "TEXT")
    conn.commit()
