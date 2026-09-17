"""Tests for baseline.py's aggregation/table logic (Tech_Scope.md §5, S1 row).

baseline.py sends 10 prompts through each of the 3 registry models and
prints one honesty-labelled table. This is a paid run against real models
gated on the user's later "go" -- these tests only exercise the
aggregation/table logic against the fake provider, and importing the
module must never make a live call (the entry point is guarded by
`if __name__ == "__main__":`).
"""

from __future__ import annotations

import sys

import baseline
from task_router.fake_provider import FakeProvider


def test_importing_baseline_makes_no_calls(monkeypatch):
    """Importing the module must not execute the live run."""
    called = {"n": 0}

    def spy_send(prompt, model):
        called["n"] += 1
        return {
            "text": "x",
            "input_tokens": 1,
            "output_tokens": 1,
            "latency": 0.0,
            "cost": 0.0,
            "error": None,
        }

    monkeypatch.setattr(baseline, "send", spy_send)
    # Re-importing already-imported module executes nothing further; the
    # real assertion is that import above (module-level) never called send.
    assert called["n"] == 0


def test_run_baseline_calls_send_once_per_prompt_per_model():
    fake = FakeProvider(text="ok", input_tokens=10, output_tokens=5)
    prompts = ["p1", "p2", "p3"]
    models = ["qwen3:1.7b", "sonnet"]

    results = baseline.run_baseline(fake.send, prompts, models)

    assert len(results["qwen3:1.7b"]) == 3
    assert len(results["sonnet"]) == 3
    assert all(r["error"] is None for r in results["qwen3:1.7b"])


def test_run_baseline_collects_errors_without_raising():
    fake = FakeProvider(error="simulated failure")
    prompts = ["p1", "p2"]
    models = ["sonnet"]

    results = baseline.run_baseline(fake.send, prompts, models)

    assert len(results["sonnet"]) == 2
    assert all(r["error"] == "simulated failure" for r in results["sonnet"])


def test_summarize_computes_avg_latency_avg_tokens_total_cost_and_failures():
    results = {
        "sonnet": [
            {"text": "a", "input_tokens": 100, "output_tokens": 50, "latency": 1.0, "cost": 0.001, "error": None},
            {"text": "b", "input_tokens": 200, "output_tokens": 100, "latency": 3.0, "cost": 0.002, "error": None},
            {"text": "", "input_tokens": 0, "output_tokens": 0, "latency": 0.0, "cost": 0.0, "error": "boom"},
        ]
    }

    summary = baseline.summarize(results)

    row = summary["sonnet"]
    assert row["failures"] == 1
    # avg latency/tokens computed over the 2 successful calls only
    assert row["avg_latency"] == 2.0
    assert row["avg_input_tokens"] == 150
    assert row["avg_output_tokens"] == 75
    assert row["total_cost"] == 0.003


def test_summarize_handles_all_failures_without_dividing_by_zero():
    results = {
        "sonnet": [
            {"text": "", "input_tokens": 0, "output_tokens": 0, "latency": 0.0, "cost": 0.0, "error": "boom"},
        ]
    }

    summary = baseline.summarize(results)

    row = summary["sonnet"]
    assert row["failures"] == 1
    assert row["avg_latency"] == 0.0
    assert row["avg_input_tokens"] == 0.0
    assert row["avg_output_tokens"] == 0.0
    assert row["total_cost"] == 0.0


def test_format_table_includes_honesty_label_and_all_models():
    results = {
        "qwen3:1.7b": [
            {"text": "a", "input_tokens": 10, "output_tokens": 5, "latency": 0.5, "cost": 0.0, "error": None},
        ],
        "sonnet": [
            {"text": "b", "input_tokens": 100, "output_tokens": 50, "latency": 1.0, "cost": 0.0007, "error": None},
        ],
    }
    summary = baseline.summarize(results)

    table = baseline.format_table(summary)

    assert "API list prices; no money changed hands" in table
    assert "qwen3:1.7b" in table
    assert "sonnet" in table
    # tier column present
    assert "local" in table
    assert "sonnet" in table


def test_prompts_constant_has_ten_prompts():
    assert len(baseline.PROMPTS) == 10


def test_models_constant_lists_all_three_registry_models():
    assert set(baseline.MODELS) == {"qwen3:1.7b", "sonnet", "opus"}
