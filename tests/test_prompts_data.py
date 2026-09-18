"""Data-integrity check for data/prompts.json (Tech_Scope.md §2 / §5 S2 row).

200 drafted rows. The operator hand-labels tiers over time (Phase A gate,
Product_Scope §6), so `tier` may be null (not yet labelled) or one of the
three valid tier values -- exactly 20 traps, and all 9 use cases
represented. Cheap assertions -- this is not a test of prompt quality.

`tier_source` (auto_label.py's `--merge`) is an OPTIONAL field: a row may
or may not have it (rows never touched by a merge have neither key), and
when present it must be `"hand"` (the operator's original labels) or
`"judge_auto"` (filled by auto_label.py --merge) -- never anything else.
"""

from __future__ import annotations

import json
from pathlib import Path

PROMPTS_PATH = Path(__file__).resolve().parent.parent / "data" / "prompts.json"
EXPECTED_USE_CASES = {
    "extract", "reformat", "qa_context", "summarise", "classify",
    "analyse", "reason", "create", "judge",
}
VALID_TIER_VALUES = {None, "local", "sonnet", "opus"}
VALID_TIER_SOURCE_VALUES = {"hand", "judge_auto"}


def _load() -> list[dict]:
    with PROMPTS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def test_exactly_200_rows():
    rows = _load()

    assert len(rows) == 200


def test_rows_have_valid_tier_values():
    rows = _load()

    assert len(rows) == 200
    assert sum(1 for r in rows if r["trap"] is True) == 20
    assert {r["use_case"] for r in rows} == EXPECTED_USE_CASES
    assert all(r["tier"] in VALID_TIER_VALUES for r in rows)


def test_exactly_20_traps():
    rows = _load()

    assert sum(1 for r in rows if r["trap"] is True) == 20


def test_every_use_case_present():
    rows = _load()

    use_cases = {r["use_case"] for r in rows}

    assert use_cases == EXPECTED_USE_CASES


def test_ids_are_unique_and_well_formed():
    rows = _load()

    ids = [r["id"] for r in rows]

    assert len(ids) == len(set(ids))
    assert all(i.startswith("p") and len(i) == 4 and i[1:].isdigit() for i in ids)


def test_every_row_has_a_non_empty_prompt():
    rows = _load()

    assert all(isinstance(r["prompt"], str) and r["prompt"].strip() for r in rows)


def test_tier_source_is_optional_but_valid_when_present():
    rows = _load()

    for r in rows:
        if "tier_source" in r:
            assert r["tier_source"] in VALID_TIER_SOURCE_VALUES
