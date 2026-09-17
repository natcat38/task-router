"""routing.yaml loader/validator/writer (Tech_Scope.md §2 shape, §4
`PUT /v1/routing-config` contract).

Simple in-process read-modify-write -- Tech_Scope §4's optional 409-race
handling ("two PUTs race") is deferred: this is a single-user local tool
where a lost edit from a genuine race is an acceptable, unlikely cost, and
implementing real concurrency control (file locking, an ETag/version
check) is not worth it here. Noted explicitly per the task brief.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml

DEFAULT_ROUTING_PATH = Path(__file__).resolve().parent.parent.parent / "routing.yaml"

KNOWN_TIERS = ("local", "sonnet", "opus")
MIN_THRESHOLD = 1
MAX_THRESHOLD = 5


class InvalidConfigError(ValueError):
    """Raised on a 422-worthy routing-config update: unknown tier name or
    an out-of-range threshold/sample rate."""


def _routing_path(path: Optional[Path] = None) -> Path:
    if path is not None:
        return Path(path)
    return Path(os.environ.get("ROUTING_CONFIG_PATH", str(DEFAULT_ROUTING_PATH)))


def load_config(path: Optional[Path] = None) -> dict:
    p = _routing_path(path)
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _validate(config: dict) -> None:
    for tier in config.get("tier_map", {}):
        if tier not in KNOWN_TIERS:
            raise InvalidConfigError(
                f"unknown tier {tier!r}; must be one of {KNOWN_TIERS}"
            )
    for use_case, settings in (config.get("use_cases") or {}).items():
        threshold = (settings or {}).get("judge_threshold")
        if threshold is not None and not (MIN_THRESHOLD <= threshold <= MAX_THRESHOLD):
            raise InvalidConfigError(
                f"judge_threshold for {use_case!r} must be between "
                f"{MIN_THRESHOLD} and {MAX_THRESHOLD}, got {threshold}"
            )
    rate = config.get("judge_sample_rate")
    if rate is not None and not (0.0 <= rate <= 1.0):
        raise InvalidConfigError(f"judge_sample_rate must be between 0 and 1, got {rate}")


def update_config(path: Optional[Path], partial: dict) -> dict:
    """Apply a partial update (only top-level keys present in `partial`
    change), validate the result, write it back, and return the full
    resulting config."""
    config = load_config(path)
    candidate = dict(config)

    if "tier_map" in partial:
        candidate["tier_map"] = {**config.get("tier_map", {}), **partial["tier_map"]}

    if "use_cases" in partial:
        merged_use_cases = dict(config.get("use_cases", {}))
        for use_case, settings in partial["use_cases"].items():
            merged_use_cases[use_case] = {
                **merged_use_cases.get(use_case, {}),
                **settings,
            }
        candidate["use_cases"] = merged_use_cases

    if "judge_sample_rate" in partial:
        candidate["judge_sample_rate"] = partial["judge_sample_rate"]

    _validate(candidate)

    p = _routing_path(path)
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(candidate, f, sort_keys=False)

    return candidate
