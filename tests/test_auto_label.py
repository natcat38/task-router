"""Tests for auto_label.py: derive the cheapest judge-passing tier for
every currently-UNLABELLED `data/prompts.json` row (tier is null) by
forcing the pipeline to start at `local` and letting judge/escalate walk
up until a tier's answer passes (or opus is reached, the ceiling that is
never rejected). Fake provider + temp SQLite only -- never a live model,
same test strategy as battery.py / test_battery.py.

The fake `send_fn` below distinguishes a judge call from an answer/
re-answer call by the "STRICT JSON" marker `judge.build_judge_prompt`
always includes (same technique test_judge.py and test_battery.py use),
and distinguishes which tier is answering/judging by the model id
(`qwen3:1.7b` = local, `sonnet` = sonnet, `opus` = opus -- registry.yaml).
"""

from __future__ import annotations

import json
import shutil

import pytest
import yaml

import auto_label


@pytest.fixture
def routing_yaml(tmp_path):
    dest = tmp_path / "routing.yaml"
    shutil.copy("routing.yaml", dest)
    return dest


def _set_sample_rate(routing_yaml_path, rate: float) -> None:
    config = yaml.safe_load(routing_yaml_path.read_text(encoding="utf-8"))
    config["judge_sample_rate"] = rate
    routing_yaml_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def _unlabelled_row(i, use_case="summarise"):
    return {
        "id": f"u{i}",
        "tier": None,
        "use_case": use_case,
        "prompt": f"Summarise item number {i} in one sentence.",
        "trap": False,
        "notes": "",
    }


def _prompts_fixture(tmp_path, rows):
    path = tmp_path / "prompts.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def _result(text="", *, cost=0.0, input_tokens=10, output_tokens=5, error=None):
    return {
        "text": text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency": 0.0,
        "cost": cost,
        "error": error,
    }


def _scripted_send(local_score, sonnet_score):
    """local answers -> judged by sonnet (local_score). If it fails,
    escalates to sonnet's re-answer -> judged by opus (sonnet_score). If
    that also fails, escalates to opus's re-answer, which is never judged
    (ADR 0001 ceiling)."""

    def send_fn(prompt, model):
        if "STRICT JSON" in prompt:
            if model == "sonnet":
                return _result(json.dumps({"score": local_score, "reason": "r"}), cost=0.002)
            if model == "opus":
                return _result(json.dumps({"score": sonnet_score, "reason": "r"}), cost=0.01)
            raise AssertionError(f"unexpected judge model {model!r}")
        return _result(f"{model} answer", cost=0.001)

    return send_fn


# --- unlabelled-row filter ---------------------------------------------------


def test_load_unlabelled_rows_filters_labelled_rows(tmp_path):
    rows = [
        _unlabelled_row(1),
        {"id": "p2", "tier": "local", "use_case": "summarise", "prompt": "labelled", "trap": False, "notes": ""},
    ]
    path = _prompts_fixture(tmp_path, rows)

    unlabelled = auto_label.load_unlabelled_rows(path)

    assert [r["id"] for r in unlabelled] == ["u1"]


# --- derived-tier correctness -------------------------------------------------


def test_local_answer_that_passes_judge_is_labelled_local(tmp_path, routing_yaml):
    rows = [_unlabelled_row(0)]
    prompts_path = _prompts_fixture(tmp_path, rows)
    progress_path = tmp_path / "progress.json"
    auto_labels_path = tmp_path / "auto_labels.json"
    db_path = tmp_path / "auto_label.sqlite"

    progress = auto_label.run_auto_label(
        prompts_path=prompts_path,
        progress_path=progress_path,
        auto_labels_path=auto_labels_path,
        db_path=db_path,
        routing_config_path=routing_yaml,
        send_fn=_scripted_send(local_score=5, sonnet_score=5),
        sleep_fn=lambda s: None,
        print_fn=lambda s: None,
    )

    assert progress["completed"]["u0"]["derived_tier"] == "local"
    labels = json.loads(auto_labels_path.read_text(encoding="utf-8"))
    assert labels == {"u0": "local"}


def test_local_fails_sonnet_passes_is_labelled_sonnet(tmp_path, routing_yaml):
    rows = [_unlabelled_row(0)]
    prompts_path = _prompts_fixture(tmp_path, rows)
    progress_path = tmp_path / "progress.json"
    auto_labels_path = tmp_path / "auto_labels.json"
    db_path = tmp_path / "auto_label.sqlite"

    progress = auto_label.run_auto_label(
        prompts_path=prompts_path,
        progress_path=progress_path,
        auto_labels_path=auto_labels_path,
        db_path=db_path,
        routing_config_path=routing_yaml,
        send_fn=_scripted_send(local_score=2, sonnet_score=5),
        sleep_fn=lambda s: None,
        print_fn=lambda s: None,
    )

    assert progress["completed"]["u0"]["derived_tier"] == "sonnet"
    labels = json.loads(auto_labels_path.read_text(encoding="utf-8"))
    assert labels == {"u0": "sonnet"}


def test_fails_through_to_opus_is_labelled_opus(tmp_path, routing_yaml):
    rows = [_unlabelled_row(0)]
    prompts_path = _prompts_fixture(tmp_path, rows)
    progress_path = tmp_path / "progress.json"
    auto_labels_path = tmp_path / "auto_labels.json"
    db_path = tmp_path / "auto_label.sqlite"

    progress = auto_label.run_auto_label(
        prompts_path=prompts_path,
        progress_path=progress_path,
        auto_labels_path=auto_labels_path,
        db_path=db_path,
        routing_config_path=routing_yaml,
        send_fn=_scripted_send(local_score=2, sonnet_score=2),
        sleep_fn=lambda s: None,
        print_fn=lambda s: None,
    )

    assert progress["completed"]["u0"]["derived_tier"] == "opus"
    labels = json.loads(auto_labels_path.read_text(encoding="utf-8"))
    assert labels == {"u0": "opus"}


def test_run_forces_judge_sample_rate_to_one_even_if_routing_yaml_says_otherwise(tmp_path, routing_yaml):
    """Auto-labelling REQUIRES a judge on every prompt to derive a tier --
    force sample_rate 1.0 for the run regardless of the routing.yaml on
    disk, and never mutate that file in the process."""
    _set_sample_rate(routing_yaml, 0.0)
    before = routing_yaml.read_text(encoding="utf-8")

    rows = [_unlabelled_row(0)]
    prompts_path = _prompts_fixture(tmp_path, rows)
    progress_path = tmp_path / "progress.json"
    auto_labels_path = tmp_path / "auto_labels.json"
    db_path = tmp_path / "auto_label.sqlite"

    progress = auto_label.run_auto_label(
        prompts_path=prompts_path,
        progress_path=progress_path,
        auto_labels_path=auto_labels_path,
        db_path=db_path,
        routing_config_path=routing_yaml,
        send_fn=_scripted_send(local_score=5, sonnet_score=5),
        sleep_fn=lambda s: None,
        print_fn=lambda s: None,
    )

    assert progress["completed"]["u0"]["derived_tier"] == "local"  # judge DID run
    assert routing_yaml.read_text(encoding="utf-8") == before  # operator's file untouched


# --- resumability -------------------------------------------------------------


def test_resumed_run_skips_already_completed_ids(tmp_path, routing_yaml):
    rows = [_unlabelled_row(i) for i in range(3)]
    prompts_path = _prompts_fixture(tmp_path, rows)
    progress_path = tmp_path / "progress.json"
    auto_labels_path = tmp_path / "auto_labels.json"
    db_path = tmp_path / "auto_label.sqlite"

    calls = []
    base_send = _scripted_send(local_score=5, sonnet_score=5)

    def counting_send(prompt, model):
        calls.append((prompt, model))
        return base_send(prompt, model)

    auto_label.run_auto_label(
        prompts_path=prompts_path,
        progress_path=progress_path,
        auto_labels_path=auto_labels_path,
        db_path=db_path,
        routing_config_path=routing_yaml,
        send_fn=counting_send,
        sleep_fn=lambda s: None,
        print_fn=lambda s: None,
    )
    assert set(auto_label.load_progress(progress_path)["completed"]) == {"u0", "u1", "u2"}

    calls.clear()
    resumed = auto_label.run_auto_label(
        prompts_path=prompts_path,
        progress_path=progress_path,
        auto_labels_path=auto_labels_path,
        db_path=db_path,
        routing_config_path=routing_yaml,
        send_fn=counting_send,
        sleep_fn=lambda s: None,
        print_fn=lambda s: None,
    )
    assert calls == []  # every id already completed -- nothing re-sent
    assert set(resumed["completed"]) == {"u0", "u1", "u2"}


def test_prompt_that_exhausts_retries_is_recorded_failed_and_run_continues(tmp_path, routing_yaml):
    rows = [_unlabelled_row(0), _unlabelled_row(1)]
    prompts_path = _prompts_fixture(tmp_path, rows)
    progress_path = tmp_path / "progress.json"
    auto_labels_path = tmp_path / "auto_labels.json"
    db_path = tmp_path / "auto_label.sqlite"

    def flaky_send(prompt, model):
        if "STRICT JSON" not in prompt and "item number 0" in prompt:
            return _result(error="usage limit reached, try again later")
        if "STRICT JSON" in prompt:
            return _result(json.dumps({"score": 5, "reason": "r"}), cost=0.001)
        return _result(f"{model} answer", cost=0.001)

    progress = auto_label.run_auto_label(
        prompts_path=prompts_path,
        progress_path=progress_path,
        auto_labels_path=auto_labels_path,
        db_path=db_path,
        routing_config_path=routing_yaml,
        send_fn=flaky_send,
        max_retries=1,
        backoff_base_s=0.0,
        sleep_fn=lambda s: None,
        print_fn=lambda s: None,
    )

    assert "u0" in progress["failed"]
    assert "u1" in progress["completed"]  # the failure never crashed the whole run
    labels = json.loads(auto_labels_path.read_text(encoding="utf-8"))
    assert "u0" not in labels
    assert labels["u1"] == "local"


# --- --merge (free, no model calls) -------------------------------------------


def test_merge_fills_only_null_rows_and_sets_tier_source(tmp_path):
    rows = [
        {"id": "p1", "tier": "sonnet", "use_case": "summarise", "prompt": "hand-labelled", "trap": False, "notes": ""},
        {"id": "p2", "tier": None, "use_case": "summarise", "prompt": "unlabelled, has an auto label", "trap": False, "notes": ""},
        {"id": "p3", "tier": None, "use_case": "summarise", "prompt": "unlabelled, no auto label yet", "trap": False, "notes": ""},
    ]
    prompts_path = tmp_path / "prompts.json"
    prompts_path.write_text(json.dumps(rows), encoding="utf-8")
    auto_labels_path = tmp_path / "auto_labels.json"
    auto_labels_path.write_text(json.dumps({"p2": "opus"}), encoding="utf-8")

    auto_label.merge_auto_labels(
        prompts_path=prompts_path,
        auto_labels_path=auto_labels_path,
        print_fn=lambda s: None,
    )

    merged = {r["id"]: r for r in json.loads(prompts_path.read_text(encoding="utf-8"))}
    assert merged["p1"]["tier"] == "sonnet"
    assert merged["p1"]["tier_source"] == "hand"
    assert merged["p2"]["tier"] == "opus"
    assert merged["p2"]["tier_source"] == "judge_auto"
    assert merged["p3"]["tier"] is None
    assert "tier_source" not in merged["p3"]


def test_merge_never_overwrites_an_already_labelled_row(tmp_path):
    rows = [
        {"id": "p1", "tier": "local", "use_case": "summarise", "prompt": "hand-labelled", "trap": False, "notes": ""},
    ]
    prompts_path = tmp_path / "prompts.json"
    prompts_path.write_text(json.dumps(rows), encoding="utf-8")
    auto_labels_path = tmp_path / "auto_labels.json"
    # Even if an auto label somehow exists for an already-labelled id, the
    # hand label must win.
    auto_labels_path.write_text(json.dumps({"p1": "opus"}), encoding="utf-8")

    auto_label.merge_auto_labels(
        prompts_path=prompts_path,
        auto_labels_path=auto_labels_path,
        print_fn=lambda s: None,
    )

    merged = json.loads(prompts_path.read_text(encoding="utf-8"))
    assert merged[0]["tier"] == "local"
    assert merged[0]["tier_source"] == "hand"
