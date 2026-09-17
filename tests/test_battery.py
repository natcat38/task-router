"""Tests for battery.py (Tech_Scope.md §5 S7 row): the battery's OWN logic
(labelled-row filtering, resumable checkpointing, retry/backoff, summary
math) against a fake provider and temp SQLite -- never a live model, per
the S7 test strategy ("the real run happens exactly once, manually
triggered, never in CI").
"""

from __future__ import annotations

import json
import shutil

import pytest
import yaml
from fastapi.testclient import TestClient

import battery
from api import create_app
from task_router import db as db_module
from task_router.fake_provider import FakeProvider


@pytest.fixture
def routing_yaml(tmp_path):
    dest = tmp_path / "routing.yaml"
    shutil.copy("routing.yaml", dest)
    return dest


def _set_sample_rate(routing_yaml_path, rate: float) -> None:
    config = yaml.safe_load(routing_yaml_path.read_text(encoding="utf-8"))
    config["judge_sample_rate"] = rate
    routing_yaml_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _prompts_fixture(tmp_path, rows):
    path = tmp_path / "prompts.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def _labelled_row(i, tier="local", use_case="summarise"):
    return {
        "id": f"p{i}",
        "tier": tier,
        "use_case": use_case,
        "prompt": f"Summarise item number {i} in one sentence.",
        "trap": False,
        "notes": "",
    }


# --- labelled-row filter ----------------------------------------------------


def test_load_labelled_rows_filters_null_tier_rows(tmp_path):
    rows = [
        _labelled_row(1),
        {"id": "p2", "tier": None, "use_case": "summarise", "prompt": "unlabelled", "trap": False, "notes": ""},
    ]
    path = _prompts_fixture(tmp_path, rows)

    labelled = battery.load_labelled_rows(path)

    assert [r["id"] for r in labelled] == ["p1"]


# --- resumability ------------------------------------------------------------


def test_resumed_run_skips_already_completed_ids(tmp_path, routing_yaml):
    rows = [_labelled_row(i) for i in range(3)]
    prompts_path = _prompts_fixture(tmp_path, rows)
    progress_path = tmp_path / "progress.json"
    db_path = tmp_path / "audit.sqlite"
    _set_sample_rate(routing_yaml, 0.0)  # no judge calls -- keep this test about resumability only

    fake = FakeProvider(text="answer", input_tokens=5, output_tokens=2)
    calls = []

    def counting_send(prompt, model):
        calls.append(prompt)
        return fake.send(prompt, model)

    battery.run_battery(
        prompts_path=prompts_path,
        progress_path=progress_path,
        db_path=db_path,
        routing_config_path=routing_yaml,
        send_fn=counting_send,
        select_tier_fn=lambda features: "local",
        sleep_fn=lambda s: None,
        print_fn=lambda s: None,
    )
    assert len(calls) == 3
    progress = battery.load_progress(progress_path)
    assert set(progress["completed"]) == {"p0", "p1", "p2"}

    calls.clear()
    resumed_progress = battery.run_battery(
        prompts_path=prompts_path,
        progress_path=progress_path,
        db_path=db_path,
        routing_config_path=routing_yaml,
        send_fn=counting_send,
        select_tier_fn=lambda features: "local",
        sleep_fn=lambda s: None,
        print_fn=lambda s: None,
    )
    assert calls == []  # every id already completed -- nothing re-sent
    assert set(resumed_progress["completed"]) == {"p0", "p1", "p2"}


def test_prompt_that_exhausts_retries_is_recorded_failed_and_run_continues(tmp_path, routing_yaml):
    rows = [_labelled_row(0), _labelled_row(1)]
    prompts_path = _prompts_fixture(tmp_path, rows)
    progress_path = tmp_path / "progress.json"
    db_path = tmp_path / "audit.sqlite"
    _set_sample_rate(routing_yaml, 0.0)

    def per_prompt_send(prompt, model):
        if "item number 0" in prompt:
            return {
                "text": "", "input_tokens": 0, "output_tokens": 0, "latency": 0.0,
                "cost": 0.0, "error": "usage limit reached, try again later",
            }
        return {"text": "ok", "input_tokens": 5, "output_tokens": 2, "latency": 0.0, "cost": 0.0, "error": None}

    progress = battery.run_battery(
        prompts_path=prompts_path,
        progress_path=progress_path,
        db_path=db_path,
        routing_config_path=routing_yaml,
        send_fn=per_prompt_send,
        select_tier_fn=lambda features: "local",
        max_retries=1,
        backoff_base_s=0.0,
        sleep_fn=lambda s: None,
        print_fn=lambda s: None,
    )

    assert "p0" in progress["failed"]
    assert "p1" in progress["completed"]  # the failure never crashed the whole run


# --- retry/backoff -----------------------------------------------------------


def test_with_retry_backs_off_on_usage_limit_then_succeeds():
    attempts = []

    def flaky_send(prompt, model):
        attempts.append(model)
        if len(attempts) < 3:
            return {
                "text": "", "input_tokens": 0, "output_tokens": 0, "latency": 0.0, "cost": 0.0,
                "error": "claude -p exited 1: Claude AI usage limit reached, resets at 3pm",
            }
        return {"text": "ok", "input_tokens": 5, "output_tokens": 2, "latency": 0.0, "cost": 0.0, "error": None}

    sleeps = []
    wrapped = battery.with_retry(flaky_send, max_retries=5, backoff_base_s=1.0, sleep_fn=sleeps.append)

    result = wrapped("prompt", "sonnet")

    assert result["error"] is None
    assert result["text"] == "ok"
    assert len(attempts) == 3
    assert len(sleeps) == 2  # backed off before attempts 2 and 3
    assert sleeps == [1.0, 2.0]  # exponential backoff: base * 2**attempt


def test_with_retry_gives_up_after_max_retries_and_returns_last_error():
    def always_fails(prompt, model):
        return {
            "text": "", "input_tokens": 0, "output_tokens": 0, "latency": 0.0, "cost": 0.0,
            "error": "429 too many requests",
        }

    sleeps = []
    wrapped = battery.with_retry(always_fails, max_retries=2, backoff_base_s=1.0, sleep_fn=sleeps.append)

    result = wrapped("prompt", "sonnet")

    assert result["error"] == "429 too many requests"
    assert len(sleeps) == 2  # retried exactly max_retries times, then gave up


def test_with_retry_does_not_retry_a_non_usage_limit_error():
    calls = []

    def hard_fail(prompt, model):
        calls.append(model)
        return {
            "text": "", "input_tokens": 0, "output_tokens": 0, "latency": 0.0, "cost": 0.0,
            "error": "unknown model 'bogus': KeyError",
        }

    sleeps = []
    wrapped = battery.with_retry(hard_fail, max_retries=5, backoff_base_s=1.0, sleep_fn=sleeps.append)

    result = wrapped("prompt", "bogus")

    assert result["error"] == "unknown model 'bogus': KeyError"
    assert len(calls) == 1  # no retry on a non-usage-limit error
    assert sleeps == []


@pytest.mark.parametrize(
    "error,expected",
    [
        ("Claude AI usage limit reached, resets at 3pm", True),
        ("429 rate limit exceeded", True),
        ("server overloaded, try again later", True),
        ("unknown model 'bogus': KeyError", False),
        ("ollama transport error: connection refused", False),
        (None, False),
        ("", False),
    ],
)
def test_is_usage_limit_error_matches_expected_markers(error, expected):
    assert battery.is_usage_limit_error(error) is expected


# --- summary math -------------------------------------------------------------


def _seed_run(conn, run_id, *, tier, cost_all_tiers, judge_cost=0.0, escalated=0):
    conn.execute(
        "INSERT INTO runs (run_id, created_at, input_text, tier_chosen, model_used, "
        "output_text, status, cost_all_tiers, judge_cost, escalated) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            run_id, "2026-01-01T00:00:00+00:00", "prompt", tier, "model", "answer",
            "ok", json.dumps(cost_all_tiers), judge_cost, escalated,
        ),
    )
    conn.commit()


def test_compute_summary_matches_hand_computed_savings(tmp_path, routing_yaml):
    db_path = tmp_path / "audit.sqlite"
    app = create_app(
        db_path=db_path,
        send_fn=lambda p, m: {"error": "unused"},
        select_tier_fn=lambda f: "local",
        routing_config_path=routing_yaml,
    )
    client = TestClient(app)
    conn = db_module.get_connection(db_path)

    _seed_run(conn, "r1", tier="local", cost_all_tiers={"local": 0.001, "sonnet": 0.01, "opus": 0.05}, judge_cost=0.002)
    _seed_run(
        conn, "r2", tier="sonnet",
        cost_all_tiers={"local": 0.0012, "sonnet": 0.01, "opus": 0.06},
        judge_cost=0.003, escalated=1,
    )

    progress = {"completed": {"p1": {"escalated": False}, "p2": {"escalated": True}}}

    summary = battery.compute_summary(client, progress)

    opus_total = 0.05 + 0.06
    actual_excl = 0.001 + 0.01
    actual_incl = actual_excl + 0.002 + 0.003
    expected_excl_pct = (1 - actual_excl / opus_total) * 100
    expected_incl_pct = (1 - actual_incl / opus_total) * 100

    assert summary["n_requests"] == 2
    assert summary["by_tier"] == {"local": 1, "sonnet": 1, "opus": 0}
    assert summary["n_escalated"] == 1
    assert summary["saved_pct_excl_judge"] == pytest.approx(expected_excl_pct)
    assert summary["saved_pct_incl_judge"] == pytest.approx(expected_incl_pct)
    assert summary["price_basis"] == "api_list_prices_no_money_changed_hands"


def test_format_summary_includes_honesty_label_and_counts():
    summary = {
        "n_requests": 2,
        "by_tier": {"local": 1, "sonnet": 1, "opus": 0},
        "n_escalated": 1,
        "saved_pct_excl_judge": 50.0,
        "saved_pct_incl_judge": 40.0,
        "price_basis": "api_list_prices_no_money_changed_hands",
    }
    text = battery.format_summary(summary)
    assert battery.HONESTY_LABEL in text
    assert "n_requests = 2" in text
    assert "n_escalated = 1" in text
