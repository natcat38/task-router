"""Tests for the model registry loader (Tech_Scope.md §2, S1 row).

Loads registry.yaml, exposes lookups by model id / tier, and computes cost
from the per-million-token list prices. Uses the repo-root registry.yaml
via REGISTRY_PATH (default) rather than a fixture, so a drift between the
committed file and this test is itself a signal.
"""

from __future__ import annotations

import pytest

from task_router.registry import ModelEntry, Registry, load_registry


def test_load_registry_returns_three_models():
    registry = load_registry()

    assert len(registry.models) == 3


def test_lookup_by_model_id():
    registry = load_registry()

    entry = registry.by_id("sonnet")

    assert isinstance(entry, ModelEntry)
    assert entry.provider == "claude_cli"
    assert entry.tier == "sonnet"
    assert entry.price_in_per_m == 2.0
    assert entry.price_out_per_m == 10.0


def test_lookup_by_tier():
    registry = load_registry()

    entry = registry.by_tier("local")

    assert entry.id == "qwen3:1.7b"
    assert entry.provider == "ollama"
    assert entry.price_in_per_m == 0.0
    assert entry.price_out_per_m == 0.0


def test_lookup_unknown_model_id_raises_key_error():
    registry = load_registry()

    with pytest.raises(KeyError):
        registry.by_id("does-not-exist")


def test_lookup_unknown_tier_raises_key_error():
    registry = load_registry()

    with pytest.raises(KeyError):
        registry.by_tier("does-not-exist")


@pytest.mark.parametrize(
    "model_id,input_tokens,output_tokens,expected",
    [
        # sonnet: $2/M in, $10/M out -> 1000 in + 500 out
        ("sonnet", 1000, 500, 2.0 * 0.001 + 10.0 * 0.0005),
        # opus: $5/M in, $25/M out -> 2000 in + 1000 out
        ("opus", 2000, 1000, 5.0 * 0.002 + 25.0 * 0.001),
        # local: always free regardless of token counts
        ("qwen3:1.7b", 10_000, 10_000, 0.0),
    ],
)
def test_cost_computed_from_registry_prices(model_id, input_tokens, output_tokens, expected):
    registry = load_registry()

    cost = registry.cost(model_id, input_tokens, output_tokens)

    assert cost == pytest.approx(expected)


def test_registry_path_env_override(tmp_path, monkeypatch):
    custom = tmp_path / "custom_registry.yaml"
    custom.write_text(
        "models:\n"
        "  - provider: ollama\n"
        "    id: test-model\n"
        "    tier: local\n"
        "    price_in_per_m: 0.0\n"
        "    price_out_per_m: 0.0\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REGISTRY_PATH", str(custom))

    registry = load_registry()

    assert len(registry.models) == 1
    assert registry.by_id("test-model").tier == "local"


def test_registry_is_a_dataclass_container():
    registry = load_registry()

    assert isinstance(registry, Registry)
    assert all(isinstance(m, ModelEntry) for m in registry.models)
