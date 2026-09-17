"""S5 read API: `GET /runs`, `GET /runs/{id}/spans`, `POST /replay`
(Tech_Scope.md §4 / §5 S5 row). Fake provider + temp SQLite only -- no live
model, per the S5 test strategy.

`POST /replay` tests use `judge_sample_rate=0.0` so the synchronous judge
step inside `_run_pipeline` never fires (deterministic assertions: no
escalation, no judge score on either side of the diff). ADR 0002 governs
the replay semantics under test here: replay re-runs the WHOLE router
pipeline with `select_tier` overridden to `forced_tier`, producing a
brand-new, separate `run_id` -- never a correction of the source row --
because replay is non-deterministic.
"""

from __future__ import annotations

import json
import shutil
import sqlite3

import pytest
import yaml
from fastapi.testclient import TestClient

from api import create_app
from task_router.fake_provider import FakeProvider


@pytest.fixture
def routing_yaml(tmp_path):
    dest = tmp_path / "routing.yaml"
    shutil.copy("routing.yaml", dest)
    return dest


def _set_judge_sample_rate(routing_yaml_path, rate: float) -> None:
    config = yaml.safe_load(routing_yaml_path.read_text(encoding="utf-8"))
    config["judge_sample_rate"] = rate
    routing_yaml_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _per_model_send(prompt: str, model: str) -> dict:
    """A fake provider whose output text varies by model, so replay tests
    can assert `output_changed` against a real difference instead of a
    coincidentally-identical canned string."""
    return {
        "text": f"{model} says: {prompt}",
        "input_tokens": 10,
        "output_tokens": 5,
        "latency": 0.0,
        "cost": 0.0,
        "error": None,
    }


def _seed_run(db_path, run_id, *, tier, model, use_case, status="ok", created_at, judge_score=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO runs (run_id, created_at, input_text, tier_chosen, model_used, "
        "output_text, status, use_case, judge_score) VALUES (?,?,?,?,?,?,?,?,?)",
        (run_id, created_at, "seed prompt", tier, model, f"{model} out", status, use_case, judge_score),
    )
    conn.commit()
    conn.close()


def _seed_span(db_path, span_id, run_id, *, parent_span_id, name, start_ns, end_ns, status="OK"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO spans (span_id, run_id, parent_span_id, name, start_ns, end_ns, "
        "attributes, status) VALUES (?,?,?,?,?,?,?,?)",
        (span_id, run_id, parent_span_id, name, start_ns, end_ns, json.dumps({"k": "v"}), status),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def app_and_db(tmp_path, routing_yaml):
    fake = FakeProvider(text="ok", input_tokens=10, output_tokens=5)
    db_path = tmp_path / "audit.sqlite"
    app = create_app(
        db_path=db_path,
        send_fn=fake.send,
        select_tier_fn=lambda features: "local",
        routing_config_path=routing_yaml,
    )
    return app, db_path


# --- GET /runs --------------------------------------------------------


def test_get_runs_pagination_math_and_slicing(app_and_db):
    app, db_path = app_and_db
    client = TestClient(app)
    for i in range(5):
        _seed_run(
            db_path, f"run{i}", tier="local", model="qwen3:1.7b", use_case="summarise",
            created_at=f"2026-01-0{i + 1}T00:00:00+00:00",
        )

    resp = client.get("/runs", params={"page": 1, "page_size": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["pagination"] == {
        "page": 1, "page_size": 2, "total_items": 5, "total_pages": 3,
    }
    assert len(body["data"]) == 2
    # Newest first: run4 (2026-01-05) then run3 (2026-01-04).
    assert [r["run_id"] for r in body["data"]] == ["run4", "run3"]

    resp_last = client.get("/runs", params={"page": 3, "page_size": 2})
    assert resp_last.status_code == 200
    last_body = resp_last.json()
    assert last_body["pagination"]["total_pages"] == 3
    assert [r["run_id"] for r in last_body["data"]] == ["run0"]


def test_get_runs_filters_by_tier_use_case_and_status(app_and_db):
    app, db_path = app_and_db
    client = TestClient(app)
    _seed_run(db_path, "r_local", tier="local", model="qwen3:1.7b", use_case="summarise", status="ok", created_at="2026-01-01T00:00:00+00:00")
    _seed_run(db_path, "r_sonnet", tier="sonnet", model="sonnet", use_case="reason", status="ok", created_at="2026-01-02T00:00:00+00:00")
    _seed_run(db_path, "r_error", tier="local", model="qwen3:1.7b", use_case="summarise", status="error", created_at="2026-01-03T00:00:00+00:00")

    by_tier = client.get("/runs", params={"tier": "sonnet"}).json()
    assert [r["run_id"] for r in by_tier["data"]] == ["r_sonnet"]
    assert by_tier["pagination"]["total_items"] == 1

    by_use_case = client.get("/runs", params={"use_case": "reason"}).json()
    assert [r["run_id"] for r in by_use_case["data"]] == ["r_sonnet"]

    by_status = client.get("/runs", params={"status": "error"}).json()
    assert [r["run_id"] for r in by_status["data"]] == ["r_error"]

    combined = client.get(
        "/runs", params={"tier": "local", "use_case": "summarise", "status": "ok"}
    ).json()
    assert [r["run_id"] for r in combined["data"]] == ["r_local"]


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page": -1}])
def test_get_runs_out_of_range_pagination_is_422(app_and_db, params):
    app, _ = app_and_db
    client = TestClient(app)
    resp = client.get("/runs", params=params)
    assert resp.status_code == 422


def test_get_runs_empty_table_reports_zero_totals(app_and_db):
    app, _ = app_and_db
    client = TestClient(app)
    resp = client.get("/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["pagination"] == {"page": 1, "page_size": 20, "total_items": 0, "total_pages": 0}


# --- GET /runs/{id}/spans ----------------------------------------------


def test_get_run_spans_returns_run_and_ordered_spans(app_and_db):
    app, db_path = app_and_db
    client = TestClient(app)
    _seed_run(db_path, "run_x", tier="local", model="qwen3:1.7b", use_case="summarise", created_at="2026-01-01T00:00:00+00:00")
    _seed_span(db_path, "span_root", "run_x", parent_span_id=None, name="root", start_ns=100, end_ns=500)
    _seed_span(db_path, "span_child", "run_x", parent_span_id="span_root", name="router.classify", start_ns=150, end_ns=200)

    resp = client.get("/runs/run_x/spans")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run"]["run_id"] == "run_x"
    assert body["run"]["tier_chosen"] == "local"
    assert body["run"]["use_case"] == "summarise"
    span_names_in_order = [s["name"] for s in body["spans"]]
    assert span_names_in_order == ["root", "router.classify"]
    assert body["spans"][1]["parent_span_id"] == "span_root"
    assert body["spans"][0]["attributes"] == {"k": "v"}


def test_get_run_spans_unknown_run_id_is_404(app_and_db):
    app, _ = app_and_db
    client = TestClient(app)
    resp = client.get("/runs/does-not-exist/spans")
    assert resp.status_code == 404


# --- POST /replay --------------------------------------------------------


@pytest.fixture
def replay_app_and_db(tmp_path, routing_yaml):
    _set_judge_sample_rate(routing_yaml, 0.0)  # no judge calls -> deterministic diff
    db_path = tmp_path / "audit.sqlite"
    app = create_app(
        db_path=db_path,
        send_fn=_per_model_send,
        select_tier_fn=lambda features: "local",
        routing_config_path=routing_yaml,
    )
    return app, db_path


def test_replay_creates_new_run_and_replays_row_with_expected_diff(replay_app_and_db):
    app, db_path = replay_app_and_db
    client = TestClient(app)

    original = client.post(
        "/v1/completions", json={"prompt": "Summarise this.", "use_case": "summarise"}
    )
    assert original.status_code == 200
    source_run_id = original.json()["run_id"]
    assert original.json()["tier_chosen"] == "local"

    resp = client.post(
        "/replay", json={"source_run_id": source_run_id, "forced_tier": "opus"}
    )
    assert resp.status_code == 200
    body = resp.json()
    new_run_id = body["new_run_id"]
    assert new_run_id != source_run_id

    # Hand-computed expected diff: forced tier (opus) differs from the
    # source's routed tier (local) -> tier and model both changed; the fake
    # provider's per-model text differs -> output changed; judge sampling
    # is off on both sides -> no score to diff.
    assert body["diff_summary"] == {
        "tier_changed": True,
        "model_changed": True,
        "judge_score_delta": None,
        "output_changed": True,
    }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    replays = conn.execute("SELECT * FROM replays").fetchall()
    assert len(replays) == 1
    replay_row = replays[0]
    assert replay_row["replay_id"] == body["replay_id"]
    assert replay_row["source_run_id"] == source_run_id
    assert replay_row["forced_tier"] == "opus"
    assert replay_row["new_run_id"] == new_run_id
    assert json.loads(replay_row["diff_summary"]) == body["diff_summary"]

    new_run = conn.execute("SELECT * FROM runs WHERE run_id = ?", (new_run_id,)).fetchone()
    assert new_run["tier_chosen"] == "opus"
    assert new_run["model_used"] == "opus"
    assert new_run["input_text"] == "Summarise this."
    assert new_run["use_case"] == "summarise"
    conn.close()


def test_replay_same_forced_tier_as_source_reports_no_tier_or_model_change(replay_app_and_db):
    app, db_path = replay_app_and_db
    client = TestClient(app)

    original = client.post(
        "/v1/completions", json={"prompt": "Summarise this.", "use_case": "summarise"}
    )
    source_run_id = original.json()["run_id"]  # answered at "local"

    resp = client.post(
        "/replay", json={"source_run_id": source_run_id, "forced_tier": "local"}
    )
    assert resp.status_code == 200
    diff = resp.json()["diff_summary"]
    assert diff["tier_changed"] is False
    assert diff["model_changed"] is False
    # Same prompt, same model -> the fake provider's per-model text is
    # identical, so nothing to report as changed.
    assert diff["output_changed"] is False


def test_replay_unknown_source_run_id_is_404(replay_app_and_db):
    app, _ = replay_app_and_db
    client = TestClient(app)
    resp = client.post(
        "/replay", json={"source_run_id": "does-not-exist", "forced_tier": "opus"}
    )
    assert resp.status_code == 404


def test_replay_bad_forced_tier_is_422(replay_app_and_db):
    app, db_path = replay_app_and_db
    client = TestClient(app)
    _seed_run(db_path, "run_seed", tier="local", model="qwen3:1.7b", use_case="summarise", created_at="2026-01-01T00:00:00+00:00")

    resp = client.post(
        "/replay", json={"source_run_id": "run_seed", "forced_tier": "gpt5"}
    )
    assert resp.status_code == 422
