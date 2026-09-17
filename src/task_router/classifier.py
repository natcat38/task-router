"""Tier selection: a trained model if one exists, else a documented
deterministic heuristic.

Tech_Scope.md §5 S3 row and §3 step 3 (`router.select_tier` scores the
feature vector, picks a tier). train.py (S2) saves a LogisticRegression to
`models/classifier_v<version>.joblib` once the operator has hand-labelled
>=60 prompts (Product_Scope §6 Phase A gate). That labelling has not
happened yet at S3 build time -- no model file exists -- so this module
must work end-to-end with nothing on disk.

Fallback heuristic (`heuristic_select_tier`, used only when no model file
loads): a small weighted score over the same 8 surface features
features.py already computes. Heavier reasoning load, more explicit
constraints, and longer prompts push toward a higher tier; a short,
unconstrained prompt stays on the free local tier, which matches the
product's stated default of "the cheap model is the default"
(Product_Scope §1). This is a placeholder to make the API answerable
before real labels exist -- it is not a decision boundary trained on data,
and it is not meant to survive S2's actual training run.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

import joblib

from task_router.features import features_to_vector

DEFAULT_MODEL_PATH = (
    Path(__file__).resolve().parent.parent.parent / "models" / "classifier_v1.joblib"
)

TIERS = ("local", "sonnet", "opus")

SelectTierFn = Callable[[dict], str]

# Heuristic thresholds: tuned by hand for plausibility, not fit to data.
_SONNET_SCORE_THRESHOLD = 3
_OPUS_SCORE_THRESHOLD = 7
_LONG_PROMPT_WORDS = 120


def heuristic_select_tier(features: dict) -> str:
    """Deterministic fallback tier choice, used only when no trained model
    is available on disk. See module docstring for why this exists and why
    it is not tuned on real data."""
    score = (
        2 * features["reasoning_word_count"]
        + features["constraint_count"]
        + features["question_count"]
        + (2 if features["output_format_specified"] else 0)
        + (3 if features["length"] > _LONG_PROMPT_WORDS else 0)
    )
    if score >= _OPUS_SCORE_THRESHOLD:
        return "opus"
    if score >= _SONNET_SCORE_THRESHOLD:
        return "sonnet"
    return "local"


def _model_path() -> Path:
    return Path(os.environ.get("TASK_ROUTER_MODEL_PATH", str(DEFAULT_MODEL_PATH)))


def load_classifier(path: Optional[Path] = None):
    """Load the trained sklearn model if the file exists, else None.

    joblib.load unpickles -- normally unsafe on untrusted input, but this
    only ever loads a file train.py (this same repo, run by the operator on
    this same machine) just wrote to `models/`. There is no network or
    third-party source for this file, so the trust boundary is "did I run
    train.py myself," not "did I download this."
    """
    p = path or _model_path()
    if not p.exists():
        return None
    return joblib.load(p)


def select_tier(features: dict, model=None) -> str:
    """Pick a tier for `features`.

    `model` is injectable so tests can pass a stub without a real joblib
    file (e.g. `select_tier(features, model=StubModel())`). When omitted,
    this tries to load the real trained model from disk and falls back to
    the heuristic above when none exists.
    """
    if model is None:
        model = load_classifier()
    if model is None:
        return heuristic_select_tier(features)
    vector = [features_to_vector(features)]
    return str(model.predict(vector)[0])
