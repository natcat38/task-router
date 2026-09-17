"""POST /v1/completions end to end (Tech_Scope.md §5 S3 test strategy):
runs/spans land correctly with parent/child nesting, gen_ai.* attributes,
cost_all_tiers computed for all three tiers, and forced_tier honoured --
against a fake provider and a stub classifier, never a live model.
"""

from __future__ import annotations

import json
import shutil

import pytest
from fastapi.testclient import TestClient

from api import create_app
from task_router.fake_provider import FakeProvider


@pytest.fixture
def routing_yaml(tmp_path):
    dest = tmp_path / "routing.yaml"
    shutil.copy("routing.yaml", dest)
    return dest


@pytest.fixture
def client(tmp_path, routing_yaml):
    fake = FakeProvider(text="hi there", input_tokens=10, output_tokens=5)
    app = create_app(
        db_path=tmp_path / "audit.sqlite",
        send_fn=fake.send,
        select_tier_fn=lambda features: "local",
        routing_config_path=routing_yaml,
    )
    return TestClient(app), tmp_path / "audit.sqlite"


def _rows(db_path, table):
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    conn.close()
    return rows


def test_completion_writes_one_run_row_with_expected_fields(client):
    test_client, db_path = client
    resp = test_client.post(
        "/v1/completions", json={"prompt": "Summarise this.", "use_case": "summarise"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tier_chosen"] == "local"
    assert body["model_used"] == "qwen3:1.7b"
    assert body["output_text"] == "hi there"
    assert set(body["cost_all_tiers"]) == {"local", "sonnet", "opus"}

    runs = _rows(db_path, "runs")
    assert len(runs) == 1
    run = runs[0]
    assert run["run_id"] == body["run_id"]
    assert run["tier_chosen"] == "local"
    assert run["model_used"] == "qwen3:1.7b"
    assert run["status"] == "ok"
    assert json.loads(run["cost_all_tiers"]) == body["cost_all_tiers"]


def test_completion_spans_land_with_correct_parent_child_nesting(client):
    test_client, db_path = client
    resp = test_client.post(
        "/v1/completions", json={"prompt": "Summarise this.", "use_case": "summarise"}
    )
    run_id = resp.json()["run_id"]

    spans = _rows(db_path, "spans")
    by_name = {s["name"]: s for s in spans}
    assert "router.classify" in by_name
    assert "router.select_tier" in by_name
    assert "chat qwen3:1.7b" in by_name

    # All spans belong to this request's trace (run_id = trace_id).
    for s in spans:
        assert s["run_id"] == run_id

    root_candidates = [s for s in spans if s["parent_span_id"] is None]
    non_root = [s for s in spans if s["parent_span_id"] is not None]
    # The FastAPI auto-instrumented request span is the root; our three
    # hand-rolled spans are its direct children.
    assert len(root_candidates) == 1
    root_span_id = root_candidates[0]["span_id"]
    for s in non_root:
        assert s["parent_span_id"] == root_span_id


def test_chat_span_carries_gen_ai_attributes(client):
    test_client, db_path = client
    test_client.post(
        "/v1/completions", json={"prompt": "Summarise this.", "use_case": "summarise"}
    )
    spans = _rows(db_path, "spans")
    chat_span = next(s for s in spans if s["name"] == "chat qwen3:1.7b")
    attrs = json.loads(chat_span["attributes"])
    assert attrs["gen_ai.provider.name"] == "ollama"
    assert attrs["gen_ai.request.model"] == "qwen3:1.7b"
    assert attrs["gen_ai.usage.input_tokens"] == 10
    assert attrs["gen_ai.usage.output_tokens"] == 5


def test_forced_tier_skips_classifier_and_is_recorded(tmp_path, routing_yaml):
    fake = FakeProvider(text="opus answer", input_tokens=20, output_tokens=8)
    called = {"select_tier": False}

    def spy_select_tier(features):
        called["select_tier"] = True
        return "local"

    app = create_app(
        db_path=tmp_path / "audit.sqlite",
        send_fn=fake.send,
        select_tier_fn=spy_select_tier,
        routing_config_path=routing_yaml,
    )
    test_client = TestClient(app)

    resp = test_client.post(
        "/v1/completions",
        json={"prompt": "Do a hard thing.", "use_case": "reason", "forced_tier": "opus"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tier_chosen"] == "opus"
    assert body["model_used"] == "opus"
    assert called["select_tier"] is False

    runs = _rows(tmp_path / "audit.sqlite", "runs")
    assert runs[0]["forced_tier"] == "opus"
    assert runs[0]["tier_chosen"] == "opus"


def test_unknown_use_case_is_422(client):
    test_client, _ = client
    resp = test_client.post(
        "/v1/completions", json={"prompt": "hi", "use_case": "not_a_real_use_case"}
    )
    assert resp.status_code == 422


def test_missing_prompt_is_422(client):
    test_client, _ = client
    resp = test_client.post("/v1/completions", json={"use_case": "summarise"})
    assert resp.status_code == 422


def test_provider_error_is_500_and_still_audited(tmp_path, routing_yaml):
    fake = FakeProvider(error="ollama transport error: boom")
    app = create_app(
        db_path=tmp_path / "audit.sqlite",
        send_fn=fake.send,
        select_tier_fn=lambda features: "local",
        routing_config_path=routing_yaml,
    )
    test_client = TestClient(app)

    resp = test_client.post(
        "/v1/completions", json={"prompt": "hi", "use_case": "summarise"}
    )
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "provider_error"

    runs = _rows(tmp_path / "audit.sqlite", "runs")
    assert runs[0]["status"] == "error"
