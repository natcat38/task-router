"""routing_config.py load/update/validate (Tech_Scope.md §4 PUT /v1/routing-config)."""

from __future__ import annotations

import shutil

import pytest

from task_router import routing_config


@pytest.fixture
def routing_yaml(tmp_path):
    dest = tmp_path / "routing.yaml"
    shutil.copy("routing.yaml", dest)
    return dest


def test_load_config_reads_the_shape_from_tech_scope(routing_yaml):
    config = routing_config.load_config(routing_yaml)
    assert config["tier_map"] == {"local": "qwen3:1.7b", "sonnet": "sonnet", "opus": "opus"}
    assert config["judge_sample_rate"] == 1.0
    assert config["use_cases"]["classify"]["judge_threshold"] == 5


def test_partial_update_only_changes_given_keys(routing_yaml):
    updated = routing_config.update_config(routing_yaml, {"judge_sample_rate": 0.5})
    assert updated["judge_sample_rate"] == 0.5
    assert updated["tier_map"] == {"local": "qwen3:1.7b", "sonnet": "sonnet", "opus": "opus"}

    reloaded = routing_config.load_config(routing_yaml)
    assert reloaded["judge_sample_rate"] == 0.5


def test_unknown_tier_raises_invalid_config_error(routing_yaml):
    with pytest.raises(routing_config.InvalidConfigError):
        routing_config.update_config(routing_yaml, {"tier_map": {"bogus": "model-x"}})


def test_threshold_out_of_range_raises_invalid_config_error(routing_yaml):
    with pytest.raises(routing_config.InvalidConfigError):
        routing_config.update_config(
            routing_yaml, {"use_cases": {"summarise": {"judge_threshold": 0}}}
        )
    with pytest.raises(routing_config.InvalidConfigError):
        routing_config.update_config(
            routing_yaml, {"use_cases": {"summarise": {"judge_threshold": 6}}}
        )


def test_use_case_partial_update_preserves_other_use_cases(routing_yaml):
    updated = routing_config.update_config(
        routing_yaml, {"use_cases": {"summarise": {"judge_threshold": 3}}}
    )
    assert updated["use_cases"]["summarise"]["judge_threshold"] == 3
    assert updated["use_cases"]["classify"]["judge_threshold"] == 5
