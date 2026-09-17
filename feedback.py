"""S7: turn each ESCALATED-AND-CONFIRMED-PASSING run into a weighted
training row for `train.py --version 2` (Tech_Scope.md §5 S7 row;
Product_Scope.md §3.2 last bullet: "every escalation becomes a labelled
training example"; task-router-artifact.md §06).

Only a run where `escalated` is true AND the final `judge_label` is
"pass" counts: that is a request the router routed too low, and later
CONFIRMED at a higher tier -- a real, judge-verified label. A run that
escalated all the way to opus and was never judged again (ADR 0001: opus
is the top of the chain, unjudged by construction) has no confirmed-good
label to teach from, so it contributes nothing here.

Each qualifying run becomes one training row shaped exactly like a
`data/prompts.json` row plus a `weight` field, weighted 3x an ordinary
hand-labelled row (Product_Scope §3.2 / task-router-artifact.md §06).
`train.py` consumes this as `sample_weight` during fitting, not by
duplicating the row three times -- see train.py's docstring.

IMPORTANT (REFUTATIONS #14 / Product_Scope §4): this only helps the
classifier on near-duplicates of a prompt it has already gotten wrong
once. features.py's 8 surface features (length, verbs, constraints, ...)
cannot see meaning, so feedback rows do not teach the classifier to
"understand" anything new -- they just move the decision boundary a little
for requests that look like ones it has already seen escalate. Do not read
a growing feedback set as evidence the classifier is learning to reason.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from task_router import db as db_module

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_FEEDBACK_PATH = REPO_ROOT / "data" / "feedback.json"

FEEDBACK_WEIGHT = 3


def extract_feedback_rows(runs: list[dict]) -> list[dict]:
    """`runs` is a list of `runs`-table rows (as dicts, with
    `escalation_chain` already JSON-decoded or None -- see
    `load_runs_from_db`). Returns one feedback row per run that escalated
    AND was ultimately confirmed passing, labelled with the tier that
    passed (`tier_chosen`, which `judge.judge_and_escalate` already
    overwrites to the winning tier -- Tech_Scope §2's `runs` schema note).
    """
    rows: list[dict] = []
    for run in runs:
        if not run.get("escalated"):
            continue
        if run.get("judge_label") != "pass":
            # Escalated but never confirmed passing (e.g. ran out of tiers
            # at opus, which is unjudged by construction) -- not a
            # confirmed-good label, so it is not trained on as one.
            continue
        rows.append(
            {
                "id": f"feedback-{run['run_id']}",
                "tier": run["tier_chosen"],
                "use_case": run.get("use_case"),
                "prompt": run["input_text"],
                "trap": False,
                "notes": (
                    f"S7 feedback: escalated from run {run['run_id']} "
                    f"(escalation_chain={json.dumps(run.get('escalation_chain'))})"
                ),
                "weight": FEEDBACK_WEIGHT,
            }
        )
    return rows


def load_runs_from_db(db_path: Optional[Path] = None) -> list[dict]:
    """All `runs` rows, JSON columns decoded, as plain dicts."""
    conn = db_module.get_connection(db_path)
    rows = conn.execute("SELECT * FROM runs").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["escalation_chain"] = json.loads(d["escalation_chain"]) if d.get("escalation_chain") else None
        result.append(d)
    return result


def build_feedback(db_path: Optional[Path] = None) -> list[dict]:
    return extract_feedback_rows(load_runs_from_db(db_path))


def save_feedback(rows: list[dict], path: Path = DEFAULT_FEEDBACK_PATH) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    return path


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Turn escalated-and-passed runs from the audit DB into weight-3 "
            "feedback rows for `train.py --version 2`."
        )
    )
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--feedback-path", type=Path, default=DEFAULT_FEEDBACK_PATH)
    args = parser.parse_args(argv)

    rows = build_feedback(args.db_path)
    path = save_feedback(rows, args.feedback_path)
    print(f"{len(rows)} feedback row(s) (weight={FEEDBACK_WEIGHT}) written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
