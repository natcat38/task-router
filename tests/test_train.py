"""Tests for train.py (Tech_Scope.md §5 S2 row).

Runs train's fit/eval helpers against a small SYNTHETIC labelled fixture
built here, never against the real data/prompts.json -- that file is 200
drafted rows with tier: null until the operator hand-labels it, and running
metrics code over it would be exactly the silent corruption REFUTATIONS
Minor #20 warns about. This suite proves the *logic* (filtering, fitting,
metric shapes), not any accuracy claim about the real data.
"""

from __future__ import annotations

import json

import train


def _make_synthetic_rows() -> list[dict]:
    """10 labelled rows per tier (30 total) plus a few unlabelled (null
    tier) rows to exercise the labelled-row filter, and some trap rows
    scattered across tiers to exercise the per-trap report."""
    local_prompts = [
        "Extract the email from: contact us at a@b.com",
        "Pull the date out of: due March 3rd 2024",
        "Convert this to JSON: name,age\\nSam,29",
        "What time is the meeting, per this note: 9:30am Monday",
        "Extract the SKU: SKU-1122 x2 units",
        "Reformat this date: 03/14/2026",
        "Pull the tracking number: FedEx 12345",
        "Extract the hashtag: #buildinpublic",
        "Convert tabs to spaces in this snippet: def f():\\n\\tpass",
        "What status code is returned for a missing user, per this doc: 404",
    ]
    sonnet_prompts = [
        "Summarise this thread in two sentences: customer complained, agent refunded them.",
        "Classify this ticket by priority: the whole team is locked out before a demo.",
        "Analyse this SQL query for performance issues: SELECT * FROM orders",
        "Summarise this incident in plain language: a runaway job exhausted the connection pool.",
        "Classify this feedback as a bug or a feature request: please add PDF export.",
        "Analyse this churn data and name the strongest signal: churned users log in twice a month.",
        "Summarise this PR description in one line for a changelog entry.",
        "Classify this log entry by severity: disk usage at 92 percent, cleanup recommended.",
        "Analyse this A/B test result and state which variant won and why.",
        "Summarise this five-star and one-star review pair in two balanced sentences.",
    ]
    opus_prompts = [
        "Work out the total cost: three items at $12.50 with a 10 percent discount, then 8 percent tax.",
        "Reason through this staffing problem: a shift needs 2 people, 5 are available, 2 have the same day off.",
        "Every cat in the room is asleep. Milo is awake and in the room. Is Milo a cat?",
        "Determine which loan costs less in total interest between two offers with different rates and terms.",
        "Nobody on the team has ever missed a deadline. Sam just missed one. Is Sam on the team?",
        "Work out how many days it takes to clear a backlog that grows faster than the team clears it.",
        "Compare two onboarding flows and judge which converts better, with reasoning.",
        "Every employee badge grants server room access. Priya's badge does not. Is Priya an employee?",
        "Work through a seating arrangement where three couples cannot sit next to each other.",
        "Judge which of two error-handling approaches is safer for a payments system, and explain why.",
    ]

    rows = []
    n = 0
    for tier, prompts in (("local", local_prompts), ("sonnet", sonnet_prompts), ("opus", opus_prompts)):
        for i, prompt in enumerate(prompts):
            n += 1
            rows.append(
                {
                    "id": f"s{n:03d}",
                    "tier": tier,
                    "use_case": "misc",
                    "prompt": prompt,
                    "trap": tier == "opus" and i in (2, 4, 7),
                    "notes": "",
                }
            )

    # A handful of drafted-but-unlabelled rows -- must be dropped by the filter.
    for i in range(3):
        n += 1
        rows.append(
            {
                "id": f"s{n:03d}",
                "tier": None,
                "use_case": "misc",
                "prompt": f"Unlabelled draft prompt number {i}.",
                "trap": False,
                "notes": "",
            }
        )

    return rows


def test_filter_labelled_drops_null_tier_rows():
    rows = _make_synthetic_rows()

    labelled = train.filter_labelled(rows)

    assert len(labelled) == 30
    assert all(r["tier"] is not None for r in labelled)
    assert len(labelled) < len(rows)


def test_train_and_evaluate_produces_model_and_shaped_metrics():
    rows = _make_synthetic_rows()
    labelled = train.filter_labelled(rows)

    results = train.train_and_evaluate(labelled, seed=42)

    assert results["n"] == len(labelled)
    assert 0.0 <= results["held_out_accuracy"] <= 1.0
    assert 0.0 <= results["cv_mean"] <= 1.0
    assert results["cv_std"] >= 0.0
    assert results["n_folds"] >= 2

    cm = results["confusion_matrix"]
    n_labels = len(results["confusion_matrix_labels"])
    assert cm.shape == (n_labels, n_labels)
    assert n_labels == 3  # local, sonnet, opus all present in the fixture

    assert hasattr(results["model"], "predict")

    expected_trap_count = sum(1 for r in labelled if r.get("trap"))
    assert expected_trap_count == 3
    assert len(results["trap_results"]) == expected_trap_count
    for trap_result in results["trap_results"]:
        assert set(trap_result) == {"id", "actual_tier", "predicted_tier"}


def test_save_model_writes_a_joblib_file(tmp_path):
    rows = _make_synthetic_rows()
    labelled = train.filter_labelled(rows)
    results = train.train_and_evaluate(labelled, seed=42)

    path = train.save_model(results["model"], version=1, model_dir=tmp_path)

    assert path.exists()
    assert path.suffix == ".joblib"


def test_main_handles_zero_labelled_rows_cleanly(tmp_path, capsys):
    unlabelled_only = [
        {"id": "p001", "tier": None, "use_case": "extract", "prompt": "x", "trap": False, "notes": ""}
    ]
    prompts_path = tmp_path / "prompts.json"
    prompts_path.write_text(json.dumps(unlabelled_only), encoding="utf-8")

    exit_code = train.main(
        ["--prompts-path", str(prompts_path), "--model-dir", str(tmp_path / "models")]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "no labelled rows" in captured.out.lower()
    assert not (tmp_path / "models").exists()


def test_main_trains_and_saves_on_synthetic_labelled_data(tmp_path, capsys):
    rows = _make_synthetic_rows()
    prompts_path = tmp_path / "prompts.json"
    prompts_path.write_text(json.dumps(rows), encoding="utf-8")
    model_dir = tmp_path / "models"

    exit_code = train.main(
        ["--prompts-path", str(prompts_path), "--model-dir", str(model_dir), "--version", "1"]
    )

    assert exit_code == 0
    assert (model_dir / "classifier_v1.joblib").exists()
    captured = capsys.readouterr()
    assert "n (labelled) = 30" in captured.out
