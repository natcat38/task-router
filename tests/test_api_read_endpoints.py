"""GET /v1/models, GET /v1/stats, PUT /v1/routing-config (Tech_Scope.md §4 /
§5 S3 test strategy). No live provider calls anywhere in this file.

`test_get_stats_incl_judge_differs_when_judge_runs` covers the S4 addition
to `GET /v1/stats` -- see `tests/test_judge.py` for the judge/escalation
unit tests themselves.
"""

from __future__ import annotations

import shutil

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


@pytest.fixture
def app_and_client(tmp_path, routing_yaml):
    fake = FakeProvider(text="ok", input_tokens=100, output_tokens=50)
    app = create_app(
        db_path=tmp_path / "audit.sqlite",
        send_fn=fake.send,
        select_tier_fn=lambda features: "local",
        routing_config_path=routing_yaml,
    )
    return app, TestClient(app)


def test_get_models_lists_the_registry(app_and_client):
    _, client = app_and_client
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    ids = {m["id"] for m in resp.json()["models"]}
    assert ids == {"qwen3:1.7b", "sonnet", "opus"}


def test_get_stats_reports_both_saved_pct_fields_and_price_basis(
    tmp_path, routing_yaml
):
    # judge_sample_rate=0: no judge call is ever made, so judge cost is 0
    # and the two savings figures must match exactly.
    _set_judge_sample_rate(routing_yaml, 0.0)
    fake = FakeProvider(text="ok", input_tokens=100, output_tokens=50)
    app = create_app(
        db_path=tmp_path / "audit.sqlite",
        send_fn=fake.send,
        select_tier_fn=lambda features: "local",
        routing_config_path=routing_yaml,
    )
    client = TestClient(app)
    client.post("/v1/completions", json={"prompt": "hi", "use_case": "summarise"})
    client.post("/v1/completions", json={"prompt": "hi again", "use_case": "summarise"})

    resp = client.get("/v1/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_requests"] == 2
    assert body["by_tier"]["local"] == 2
    assert "saved_pct_excl_judge" in body
    assert "saved_pct_incl_judge" in body
    # Sampling gate is off -- no judge cost incurred, so the two figures match.
    assert body["saved_pct_excl_judge"] == body["saved_pct_incl_judge"]
    assert body["price_basis"] == "api_list_prices_no_money_changed_hands"
    # Local tier is free and cheaper than opus at list prices -> positive saving.
    assert body["saved_pct_excl_judge"] > 0


def test_get_stats_incl_judge_differs_when_judge_runs(tmp_path, routing_yaml):
    # judge_sample_rate=1.0 (routing.yaml's default): every local-tier
    # answer gets judged by sonnet, which costs a real sonnet call even
    # though "ok" isn't parseable as a judge score (ADR 0001 -- judge
    # tokens count against the saving regardless of the score outcome).
    fake = FakeProvider(text="ok", input_tokens=100, output_tokens=50)
    app = create_app(
        db_path=tmp_path / "audit.sqlite",
        send_fn=fake.send,
        select_tier_fn=lambda features: "local",
        routing_config_path=routing_yaml,
    )
    client = TestClient(app)
    client.post("/v1/completions", json={"prompt": "hi", "use_case": "summarise"})

    resp = client.get("/v1/stats")
    assert resp.status_code == 200
    body = resp.json()
    # Local tier itself is free, so excl-judge shows a full 100% saving --
    # incl-judge must be lower once the sonnet judge call's cost counts.
    assert body["saved_pct_excl_judge"] == 100.0
    assert body["saved_pct_incl_judge"] < body["saved_pct_excl_judge"]
    assert body["price_basis"] == "api_list_prices_no_money_changed_hands"


def test_get_stats_with_malformed_since_is_422(app_and_client):
    _, client = app_and_client
    resp = client.get("/v1/stats", params={"since": "not-a-date"})
    assert resp.status_code == 422


def test_put_routing_config_partial_update(app_and_client):
    _, client = app_and_client
    resp = client.put(
        "/v1/routing-config", json={"judge_sample_rate": 0.2}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["judge_sample_rate"] == 0.2
    # Untouched keys survive the partial update.
    assert body["tier_map"]["local"] == "qwen3:1.7b"
    assert body["use_cases"]["summarise"]["judge_threshold"] == 4


def test_put_routing_config_unknown_tier_is_422(app_and_client):
    _, client = app_and_client
    resp = client.put(
        "/v1/routing-config", json={"tier_map": {"nonexistent_tier": "some-model"}}
    )
    assert resp.status_code == 422


def test_put_routing_config_bad_threshold_is_422(app_and_client):
    _, client = app_and_client
    resp = client.put(
        "/v1/routing-config",
        json={"use_cases": {"summarise": {"judge_threshold": 9}}},
    )
    assert resp.status_code == 422
