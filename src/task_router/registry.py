"""The model registry: loads registry.yaml and answers lookups + cost math.

Tech_Scope.md §2 (registry.yaml shape) and §5 (S1 row). Prices are API list
prices, never billed on this project's Max-subscription `claude -p` path
(Product_Scope §4 / §6 D10) -- `Registry.cost()` computes what a call
*would* have cost at those list prices, nothing more.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / "registry.yaml"


@dataclass(frozen=True)
class ModelEntry:
    provider: str
    id: str
    tier: str
    price_in_per_m: float
    price_out_per_m: float


@dataclass(frozen=True)
class Registry:
    models: tuple[ModelEntry, ...]

    def by_id(self, model_id: str) -> ModelEntry:
        for entry in self.models:
            if entry.id == model_id:
                return entry
        raise KeyError(f"no model registered with id {model_id!r}")

    def by_tier(self, tier: str) -> ModelEntry:
        for entry in self.models:
            if entry.tier == tier:
                return entry
        raise KeyError(f"no model registered for tier {tier!r}")

    def cost(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Cost in USD at this model's registered list prices.

        Prices are per-million-tokens (registry.yaml), so divide token
        counts by 1e6 before multiplying.
        """
        entry = self.by_id(model_id)
        return (input_tokens / 1_000_000) * entry.price_in_per_m + (
            output_tokens / 1_000_000
        ) * entry.price_out_per_m


def _registry_path() -> Path:
    return Path(os.environ.get("REGISTRY_PATH", str(DEFAULT_REGISTRY_PATH)))


def load_registry() -> Registry:
    path = _registry_path()
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    entries = tuple(
        ModelEntry(
            provider=m["provider"],
            id=m["id"],
            tier=m["tier"],
            price_in_per_m=float(m["price_in_per_m"]),
            price_out_per_m=float(m["price_out_per_m"]),
        )
        for m in data["models"]
    )
    return Registry(models=entries)
