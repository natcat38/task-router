"""Export one battery run's SQLite database to a per-request CSV, and
recompute the README's headline numbers from that CSV.

The battery databases (`data/battery.sqlite`, `data/battery2.sqlite`) are
gitignored, so the README's Results numbers could not be checked from a
clone. This script writes the committed `data/results/run-a.csv` and
`data/results/run-b.csv`. The CSVs carry ids, tiers, scores and costs only:
no prompt text and no model output.

Usage:
    uv run python scripts/export_battery_csv.py \
        --db data/battery.sqlite --progress data/battery_progress.json \
        --out data/results/run-a.csv

    uv run python scripts/export_battery_csv.py --summarise data/results/run-a.csv

The database is opened read-only. The saving formulas are the ones
`GET /v1/stats` uses (api.py):
    excl judge = 1 - (answer_cost + escalation_cost) / all-Opus baseline
    incl judge = 1 - (answer_cost + escalation_cost + judge_cost) / baseline
where the baseline is the sum of each run's `cost_all_tiers["opus"]`.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path

TIER_ORDER = ("local", "sonnet", "opus")

COLUMNS = [
    "prompt_id",
    "run_id",
    "use_case",
    "tier_routed",
    "tier_final",
    "judge_score",
    "judge_label",
    "escalated",
    "escalation_hops",
    "reanswer_failed",
    "status",
    "answer_input_tokens",
    "answer_output_tokens",
    "answer_cost",
    "escalation_cost",
    "judge_cost",
    "cost_all_opus",
    "duplicate_row",
]


def _routed_tier(tier_final: str, chain: list[dict]) -> str:
    """The tier the classifier picked: one step below the first escalation
    target, or the final tier when nothing escalated."""
    if not chain:
        return tier_final
    first_target = chain[0]["tier"]
    return TIER_ORDER[max(TIER_ORDER.index(first_target) - 1, 0)]


def _answer_tokens(conn: sqlite3.Connection, run_id: str) -> tuple[int | None, int | None]:
    """Token counts of the first `chat` span, i.e. the routed answer call."""
    row = conn.execute(
        "SELECT attributes FROM spans WHERE run_id = ? AND name LIKE 'chat %' "
        "ORDER BY start_ns ASC LIMIT 1",
        (run_id,),
    ).fetchone()
    if row is None:
        return None, None
    attrs = json.loads(row[0])
    return attrs.get("gen_ai.usage.input_tokens"), attrs.get("gen_ai.usage.output_tokens")


def export(db_path: Path, progress_path: Path, out_path: Path) -> int:
    progress = json.loads(Path(progress_path).read_text(encoding="utf-8"))
    run_to_prompt = {o["run_id"]: pid for pid, o in progress["completed"].items()}

    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM runs ORDER BY created_at, run_id").fetchall()

    # A run that is not in the progress file re-ran a prompt that already
    # completed (Run B has one). Find its prompt id by matching input text.
    text_to_prompt = {
        r["input_text"]: run_to_prompt[r["run_id"]] for r in rows if r["run_id"] in run_to_prompt
    }

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for r in rows:
            chain = json.loads(r["escalation_chain"]) if r["escalation_chain"] else []
            in_tok, out_tok = _answer_tokens(conn, r["run_id"])
            costs = json.loads(r["cost_all_tiers"]) if r["cost_all_tiers"] else {}
            duplicate = r["run_id"] not in run_to_prompt
            writer.writerow(
                {
                    "prompt_id": run_to_prompt.get(r["run_id"]) or text_to_prompt.get(r["input_text"], ""),
                    "run_id": r["run_id"],
                    "use_case": r["use_case"],
                    "tier_routed": _routed_tier(r["tier_chosen"], chain),
                    "tier_final": r["tier_chosen"],
                    "judge_score": "" if r["judge_score"] is None else r["judge_score"],
                    "judge_label": r["judge_label"] or "",
                    "escalated": int(bool(r["escalated"])),
                    "escalation_hops": len(chain),
                    "reanswer_failed": int(any("re-answer failed" in s.get("reason", "") for s in chain)),
                    "status": r["status"],
                    "answer_input_tokens": "" if in_tok is None else in_tok,
                    "answer_output_tokens": "" if out_tok is None else out_tok,
                    "answer_cost": r["answer_cost"] or 0.0,
                    "escalation_cost": r["escalation_cost"] or 0.0,
                    "judge_cost": r["judge_cost"] or 0.0,
                    "cost_all_opus": costs.get("opus", 0.0),
                    "duplicate_row": int(duplicate),
                }
            )
    conn.close()
    return len(rows)


def summarise(csv_path: Path) -> dict:
    """Headline numbers from a results CSV (every row counts, duplicates
    included, exactly as GET /v1/stats counted them when the run was made)."""
    with Path(csv_path).open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    answer = sum(float(r["answer_cost"]) for r in rows)
    escalation = sum(float(r["escalation_cost"]) for r in rows)
    judge = sum(float(r["judge_cost"]) for r in rows)
    baseline = sum(float(r["cost_all_opus"]) for r in rows)
    actual = answer + escalation
    scores = Counter(float(r["judge_score"]) for r in rows if r["judge_score"] != "")
    return {
        "rows": len(rows),
        "distinct_prompts": len({r["prompt_id"] for r in rows}),
        "failures": sum(1 for r in rows if r["status"] != "ok"),
        "routed": dict(Counter(r["tier_routed"] for r in rows)),
        "final": dict(Counter(r["tier_final"] for r in rows)),
        "escalations": sum(int(r["escalated"]) for r in rows),
        "judge_scores": {k: scores[k] for k in sorted(scores, reverse=True)},
        "answer_cost": answer,
        "escalation_cost": escalation,
        "judge_cost": judge,
        "baseline_all_opus": baseline,
        "saved_excl_judge_pct": (1 - actual / baseline) * 100,
        "saved_incl_judge_pct": (1 - (actual + judge) / baseline) * 100,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", type=Path)
    parser.add_argument("--progress", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--summarise", type=Path, help="print headline numbers for a results CSV")
    args = parser.parse_args()
    if args.summarise:
        print(json.dumps(summarise(args.summarise), indent=2))
        return 0
    if not (args.db and args.progress and args.out):
        parser.error("--db, --progress and --out are required (or use --summarise)")
    n = export(args.db, args.progress, args.out)
    print(f"wrote {n} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
