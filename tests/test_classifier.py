"""classifier.select_tier: the no-model fallback heuristic and the
injectable-model seam (Tech_Scope.md §5 S3 row: "IMPORTANT: no trained
model exists yet ... must have a deterministic fallback")."""

from __future__ import annotations

from task_router import classifier
from task_router.features import extract_features


def test_no_model_file_falls_back_to_heuristic(tmp_path, monkeypatch):
    monkeypatch.setenv("TASK_ROUTER_MODEL_PATH", str(tmp_path / "does_not_exist.joblib"))
    assert classifier.load_classifier() is None


def test_heuristic_routes_short_plain_prompt_to_local():
    features = extract_features("List three fruits.")
    assert classifier.select_tier(features) == "local"


def test_heuristic_routes_reasoning_heavy_prompt_higher():
    features = extract_features(
        "Explain step by step why this happens, because the reasoning "
        "matters, and therefore justify each conclusion given the context, "
        "since the outcome depends on it."
    )
    tier = classifier.select_tier(features)
    assert tier in ("sonnet", "opus")


def test_select_tier_uses_injected_model_stub_over_heuristic():
    class StubModel:
        def predict(self, vectors):
            return ["opus"]

    features = extract_features("List three fruits.")  # would be "local" by heuristic
    assert classifier.select_tier(features, model=StubModel()) == "opus"
