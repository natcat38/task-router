"""Train the task-router classifier (Tech_Scope.md §2 / §5 S2 row).

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
--version exists so a future v2 retrain (Tech_Scope §5 S7) can save under a
different name; this script makes no v1-vs-v2 improvement claim anywhere.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
# pytest gets "src" on sys.path from pyproject.toml's [tool.pytest.ini_options]
# pythonpath setting; a plain `uv run python train.py` does not, since the
# package isn't installed (no [build-system] here -- same gap baseline.py
# has). Fixed locally here because this script must run standalone and
# print the "no labelled rows" message rather than crash on import.
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

from task_router.features import extract_features, features_to_vector
DEFAULT_PROMPTS_PATH = REPO_ROOT / "data" / "prompts.json"
DEFAULT_MODEL_DIR = REPO_ROOT / "models"
SEED = 42
NO_LABELLED_ROWS_MESSAGE = (
    "No labelled rows yet -- label data/prompts.json first "
    "(tier is null on every drafted row until the operator hand-labels it)."
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


def train_and_evaluate(rows: list[dict], seed: int = SEED) -> dict:
    """Fit + evaluate on already-labelled rows. Returns a dict of metrics
    plus the fitted full-data model, so callers (main(), tests) can report
    or save it without recomputing."""
    x, y = build_dataset(rows)

    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.25, random_state=seed, stratify=y
    )

    held_out_model = LogisticRegression(max_iter=1000)
    held_out_model.fit(x_train, y_train)
    held_out_accuracy = accuracy_score(y_test, held_out_model.predict(x_test))

    class_counts = {cls: int((y == cls).sum()) for cls in set(y)}
    n_folds = max(2, min(5, min(class_counts.values())))
    cv = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    cv_scores = cross_val_score(LogisticRegression(max_iter=1000), x, y, cv=cv)

    labels = sorted(set(y))
    cm = confusion_matrix(y_test, held_out_model.predict(x_test), labels=labels)

    full_model = LogisticRegression(max_iter=1000)
    full_model.fit(x, y)

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
        "held_out_accuracy": float(held_out_accuracy),
        "cv_mean": float(cv_scores.mean()),
        "cv_std": float(cv_scores.std()),
        "n_folds": n_folds,
        "confusion_matrix": cm,
        "confusion_matrix_labels": labels,
        "trap_results": trap_results,
        "model": full_model,
    }


def save_model(model, version: int, model_dir: Path = DEFAULT_MODEL_DIR) -> Path:
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    path = model_dir / f"classifier_v{version}.joblib"
    joblib.dump(model, path)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the task-router classifier.")
    parser.add_argument(
        "--version",
        type=int,
        default=1,
        help="Saved-model version tag, e.g. for a later v2 retrain (S7). "
        "No v1-vs-v2 improvement claim is made by this script.",
    )
    parser.add_argument("--prompts-path", type=Path, default=DEFAULT_PROMPTS_PATH)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    args = parser.parse_args(argv)

    rows = load_prompts(args.prompts_path)
    labelled = filter_labelled(rows)

    if not labelled:
        print(NO_LABELLED_ROWS_MESSAGE)
        return 0

    results = train_and_evaluate(labelled)
    model_path = save_model(results["model"], args.version, args.model_dir)

    print(f"n (labelled) = {results['n']}")
    print(f"held-out accuracy (seeded 25% split) = {results['held_out_accuracy']:.3f}")
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
    print(f"model saved to {model_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
