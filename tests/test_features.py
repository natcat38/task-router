"""Tests for the 8 surface features (Tech_Scope.md §2, S2 row).

Hand-built prompts with known expected feature values -- each of the 8
features gets asserted on at least one crafted input, per Tech_Scope §5's
test strategy for this slice.
"""

from __future__ import annotations

from task_router.features import FEATURE_NAMES, extract_features, features_to_vector


def test_question_count_counts_question_marks():
    f = extract_features("Is Milo a cat? Is he awake?")

    assert f["question_count"] == 2


def test_instruction_verb_count_for_summarise():
    f = extract_features("Summarise: the quick brown fox jumps over the lazy dog.")

    assert f["instruction_verb_count"] >= 1


def test_context_present_true_for_multiline_reference_text():
    prompt = "Extract the email addresses from this text:\n\nContact us at a@b.com or c@d.com."

    f = extract_features(prompt)

    assert f["context_present"] is True


def test_context_present_false_for_single_line_prompt():
    f = extract_features("Write a haiku about debugging a production incident.")

    assert f["context_present"] is False


def test_output_format_specified_true_for_json_request():
    f = extract_features("Convert this row into a JSON object with matching keys.")

    assert f["output_format_specified"] is True


def test_output_format_specified_false_when_no_format_named():
    f = extract_features("Why did the server crash last night?")

    assert f["output_format_specified"] is False


def test_reasoning_word_count_counts_reasoning_words():
    f = extract_features("This works because it is fast, and therefore we should ship it.")

    assert f["reasoning_word_count"] >= 2


def test_numeric_token_count():
    f = extract_features("I have 3 apples, 42 oranges, and 1 basket.")

    assert f["numeric_token_count"] == 3


def test_constraint_count_detects_numeric_constraint():
    f = extract_features("Keep it under 100 words and reply as a bulleted list.")

    assert f["constraint_count"] >= 1


def test_length_counts_words():
    f = extract_features("one two three four five")

    assert f["length"] == 5


def test_features_to_vector_matches_feature_names_order_and_length():
    f = extract_features("Summarise this in three sentences. Why does it matter?")

    vec = features_to_vector(f)

    assert len(FEATURE_NAMES) == 8
    assert len(vec) == 8
    assert all(isinstance(v, float) for v in vec)
    assert vec[FEATURE_NAMES.index("question_count")] == 1.0
