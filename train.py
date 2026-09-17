"""Train the task-router classifier (Tech_Scope.md §2 / §5 S2 row / S7 row).

Loads data/prompts.json, filters to hand-labelled rows only (tier is null
on every drafted row until the operator labels it -- running this over the
unlabelled rows is silent corruption, not a feature: REFUTATIONS Minor #20),
fits a LogisticRegression on the 8 features from features.py, and reports:

- n (the labelled count)
- a seeded 25% held-out accuracy
- 5-fold cross-validation accuracy, mean +/- spread
- the confusion matrix
- how each labelled trap row was routed

Product_Scope.md §4: classifier accuracy is reported as n, held-out size,
and CV mean+spread -- never a single point estimate dressed as a result.

`--version 2` (S7) retrains on the SAME labelled rows PLUS `feedback.py`'s
weighted feedback rows (escalations the battery confirmed passing at a
higher tier, weight 3 -- Product_Scope §3.2), evaluated on the EXACT SAME
held-out ids as v1 (`split_held_out`), so a v1-vs-v2 difference reflects
the feedback rows and nothing else -- not a different random split over a
differently-sized dataset. Feedback rows are folded in via `sample_weight`
at fit time (weight 3 vs 1 for an ordinary labelled row), not by literally
duplicating the row three times, which would distort StratifiedKFold's
class balancing for no benefit. v1 and v2 are always printed side by side;
this script makes no v1-vs-v2 improvement claim anywhere (the held-out set
is ~15 items -- Product_Scope §4, REFUTATIONS §D.13).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.model_selection import StratifiedKFold, train_test_split

from task_router.features import extract_features, features_to_vector
DEFAULT_PROMPTS_PATH = REPO_ROOT / "data" / "prompts.json"
DEFAULT_FEEDBACK_PATH = REPO_ROOT / "data" / "feedback.json"
DEFAULT_MODEL_DIR = REPO_ROOT / "models"
SEED = 42
NO_LABELLED_ROWS_MESSAGE = (
    "No labelled rows yet -- label data/prompts.json first "
    "(tier is null on every drafted row until the operator hand-labels it)."
)
NO_IMPROVEMENT_CLAIM_NOTE = (
    "NOTE: v1 and v2 are reported side by side with NO claim that v2 is better -- "
    "the held-out set is ~15 items, carrying roughly a +/-20-point spread "
    "(Product_Scope Sec4 / REFUTATIONS Sec D.13)."
)


def load_prompts(path: Path = DEFAULT_PROMPTS_PATH) -> list[dict]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def filter_labelled(rows: list[dict]) -> list[dict]:
    """Keep only rows the operator has hand-labelled (tier is not null)."""
    return [r for r in rows if r.get("tier") is not None]


def build_dataset(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    x = [features_to_vector(extract_features(r["prompt"])) for r in rows]
    y = [r["tier"] for r in rows]
    return np.array(x, dtype=float), np.array(y)


def split_held_out(rows: list[dict], seed: int = SEED) -> tuple[list[dict], list[dict]]:
    """Seeded 25% held-out split, stratified by tier, returned as (the
    remaining train rows, the held-out rows) -- as row dicts (not arrays)
    so the SET OF IDS this split picked can be reused later. `train_v1_and_v2`
    reuses v1's held-out ids for v2 instead of drawing a fresh random split
    over a differently-sized (feedback-augmented) dataset -- a v1-vs-v2
    comparison on two different held-out sets would be meaningless."""
    ids = [r["id"] for r in rows]
    tiers = [r["tier"] for r in rows]
    _train_ids, test_ids = train_test_split(
        ids, test_size=0.25, random_state=seed, stratify=tiers
    )
    test_id_set = set(test_ids)
    train_rows = [r for r in rows if r["id"] not in test_id_set]
    held_out_rows = [r for r in rows if r["id"] in test_id_set]
    return train_rows, held_out_rows


def _cross_val_accuracy(
    x: np.ndarray, y: np.ndarray, weights: np.ndarray, seed: int
) -> tuple[np.ndarray, int]:
    """Weight-aware K-fold CV, implemented by hand (rather than
    `sklearn.model_selection.cross_val_score`) so v1 (all weights = 1) and
    v2 (feedback rows weighted 3) share one code path -- weight=1 for every
    row is mathematically identical to an unweighted fit, so this changes
    nothing for v1's numbers."""
    class_counts = {cls: int((y == cls).sum()) for cls in set(y)}
    n_folds = max(2, min(5, min(class_counts.values())))
    cv = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    scores = []
    for train_idx, test_idx in cv.split(x, y):
        model = LogisticRegression(max_iter=1000)
        model.fit(x[train_idx], y[train_idx], sample_weight=weights[train_idx])
        scores.append(accuracy_score(y[test_idx], model.predict(x[test_idx])))
    return np.array(scores), n_folds


def train_and_evaluate(
    rows: list[dict],
    seed: int = SEED,
    *,
    feedback_rows: Optional[list[dict]] = None,
    held_out_rows: Optional[list[dict]] = None,
) -> dict:
    """Fit + evaluate on already-labelled `rows`. Returns a dict of metrics
    plus the fitted full-data model, so callers (main(), tests) can report
    or save it without recomputing.

    `feedback_rows` (S7, optional): extra weighted rows from `feedback.py`
    -- folded into TRAINING only via `sample_weight` (each row's own
    `weight`, default 1), never eligible for the held-out set (they are
    synthesized from escalations, not part of the original hand-labelled
    id space `split_held_out` draws from).

    `held_out_rows` (S7, optional): reuse this EXACT set of rows as the
    held-out test set instead of drawing a fresh seeded split -- this is
    what lets v1 and v2 be compared on identical held-out examples. When
    omitted (the v1 / plain path), a fresh seeded 25% split is drawn here.
    """
    feedback_rows = feedback_rows or []

    if held_out_rows is None:
        train_rows, held_out_rows = split_held_out(rows, seed=seed)
    else:
        held_out_ids = {r["id"] for r in held_out_rows}
        train_rows = [r for r in rows if r["id"] not in held_out_ids]

    combined_train_rows = train_rows + feedback_rows
    x_train, y_train = build_dataset(combined_train_rows)
    train_weights = np.array([r.get("weight", 1) for r in combined_train_rows], dtype=float)

    x_test, y_test = build_dataset(held_out_rows)

    held_out_model = LogisticRegression(max_iter=1000)
    held_out_model.fit(x_train, y_train, sample_weight=train_weights)
    held_out_accuracy = accuracy_score(y_test, held_out_model.predict(x_test))

    labels = sorted(set(y_train) | set(y_test))
    cm = confusion_matrix(y_test, held_out_model.predict(x_test), labels=labels)

    all_rows = rows + feedback_rows
    x_all, y_all = build_dataset(all_rows)
    all_weights = np.array([r.get("weight", 1) for r in all_rows], dtype=float)
    cv_scores, n_folds = _cross_val_accuracy(x_all, y_all, all_weights, seed)

    full_model = LogisticRegression(max_iter=1000)
    full_model.fit(x_all, y_all, sample_weight=all_weights)

    trap_rows = [r for r in rows if r.get("trap")]
    trap_results = []
    for r in trap_rows:
        vec = np.array([features_to_vector(extract_features(r["prompt"]))])
        predicted_tier = full_model.predict(vec)[0]
        trap_results.append(
            {"id": r["id"], "actual_tier": r["tier"], "predicted_tier": predicted_tier}
        )

    return {
        "n": len(rows),
        "n_feedback": len(feedback_rows),
        "held_out_ids": sorted(r["id"] for r in held_out_rows),
        "held_out_accuracy": float(held_out_accuracy),
        "cv_mean": float(cv_scores.mean()),
        "cv_std": float(cv_scores.std()),
        "n_folds": n_folds,
        "confusion_matrix": cm,
        "confusion_matrix_labels": labels,
        "trap_results": trap_results,
        "model": full_model,
    }


def train_v1_and_v2(
    labelled_rows: list[dict], feedback_rows: list[dict], seed: int = SEED
) -> dict:
    """Train v1 (labelled rows only) and v2 (labelled rows + weighted S7
    feedback rows), evaluated on the SAME held-out ids, so any difference
    between them reflects the feedback rows and nothing else -- not a
    different random split. Returns `{"v1": <results dict>, "v2": <results
    dict>}`; no key here ever asserts or implies one is better than the
    other (Product_Scope §4)."""
    v1 = train_and_evaluate(labelled_rows, seed=seed)
    v1_held_out_ids = set(v1["held_out_ids"])
    v2_held_out_rows = [r for r in labelled_rows if r["id"] in v1_held_out_ids]
    v2 = train_and_evaluate(
        labelled_rows,
        seed=seed,
        feedback_rows=feedback_rows,
        held_out_rows=v2_held_out_rows,
    )
    return {"v1": v1, "v2": v2}


def load_feedback(path: Path = DEFAULT_FEEDBACK_PATH) -> list[dict]:
    """S7 weighted feedback rows (feedback.py's output). Returns [] if the
    file doesn't exist yet -- a plain `--version 1` run never touches this,
    and `--version 2` before any escalation has ever been confirmed
    passing is a legitimate (if uninteresting) v2-equals-v1 run."""
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_model(model, version: int, model_dir: Path = DEFAULT_MODEL_DIR) -> Path:
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    path = model_dir / f"classifier_v{version}.joblib"
    joblib.dump(model, path)
    return path


def _print_metrics(results: dict, label: str) -> None:
    print(f"--- {label} ---")
    n_line = f"n (labelled) = {results['n']}"
    if results.get("n_feedback"):
        n_line += f" + {results['n_feedback']} feedback row(s) (weight 3)"
    print(n_line)
    print(
        f"held-out accuracy (seeded 25% split, {len(results['held_out_ids'])} ids) = "
        f"{results['held_out_accuracy']:.3f}"
    )
    print(
        f"{results['n_folds']}-fold CV accuracy = "
        f"{results['cv_mean']:.3f} +/- {results['cv_std']:.3f}"
    )
    print(f"confusion matrix (labels={results['confusion_matrix_labels']}):")
    print(results["confusion_matrix"])
    print("per-trap routing (classifier cannot see traps by construction -- "
          "Product_Scope §4 -- this just shows where each one landed):")
    for t in results["trap_results"]:
        print(f"  {t['id']}: actual={t['actual_tier']} predicted={t['predicted_tier']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the task-router classifier.")
    parser.add_argument(
        "--version",
        type=int,
        default=1,
        help="1 = plain retrain (default). 2 = S7 retrain: labelled rows + "
        "feedback.py's weighted feedback rows, evaluated on the same "
        "held-out ids as v1, printed side by side. No v1-vs-v2 improvement "
        "claim is made by this script.",
    )
    parser.add_argument("--prompts-path", type=Path, default=DEFAULT_PROMPTS_PATH)
    parser.add_argument("--feedback-path", type=Path, default=DEFAULT_FEEDBACK_PATH)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    args = parser.parse_args(argv)

    rows = load_prompts(args.prompts_path)
    labelled = filter_labelled(rows)

    if not labelled:
        print(NO_LABELLED_ROWS_MESSAGE)
        return 0

    if args.version != 2:
        results = train_and_evaluate(labelled)
        model_path = save_model(results["model"], args.version, args.model_dir)
        _print_metrics(results, f"v{args.version}")
        print(f"model saved to {model_path}")
        return 0

    feedback_rows = load_feedback(args.feedback_path)
    comparison = train_v1_and_v2(labelled, feedback_rows)
    model_path = save_model(comparison["v2"]["model"], 2, args.model_dir)

    _print_metrics(comparison["v1"], "v1 (no feedback)")
    _print_metrics(comparison["v2"], f"v2 (+{len(feedback_rows)} weighted feedback rows)")
    print(NO_IMPROVEMENT_CLAIM_NOTE)
    print(f"model saved to {model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
