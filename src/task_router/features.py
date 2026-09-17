"""The 8 surface features fed to the classifier (Tech_Scope.md §2, S2 row).

length, instruction-verb count, constraint count, supplied-context present,
output-format specified, reasoning-word count, question count, and
numeric-token count -- all computable from the prompt text alone, no model
call. Per Product_Scope.md §4 and REFUTATIONS §B.14/§D.14: these features
are surface-only by design. A trap prompt (see data/prompts.json) is built
to score like an easy prompt on exactly these eight numbers, so this module
cannot see traps and is not trying to -- catching traps is the judge's job
(Tech_Scope.md §6), not the classifier's.
"""

from __future__ import annotations

import re

FEATURE_NAMES = (
    "length",
    "instruction_verb_count",
    "constraint_count",
    "context_present",
    "output_format_specified",
    "reasoning_word_count",
    "question_count",
    "numeric_token_count",
)

_INSTRUCTION_VERBS = (
    "extract", "pull", "summarise", "summarize", "classify", "reformat",
    "convert", "rewrite", "translate", "write", "draft", "compare", "judge",
    "rate", "score", "determine", "calculate", "compute", "list", "explain",
    "identify", "generate", "create", "transform", "reason", "analyse",
    "analyze", "work", "figure", "turn", "given",
)
_INSTRUCTION_VERB_RE = re.compile(
    r"\b(?:" + "|".join(_INSTRUCTION_VERBS) + r")\b", re.IGNORECASE
)

_NUMERIC_CONSTRAINT_RE = re.compile(
    r"\b(?:under|over|at least|no more than|no fewer than|maximum|minimum|"
    r"up to|within|exactly)\b[^.?!\n]{0,20}?\d+"
    r"|\d+\s*(?:words?|characters?|chars?|sentences?|items?|days?|weeks?|"
    r"mb|kb|gb|%|percent|files?|units?|seats?)",
    re.IGNORECASE,
)

_OUTPUT_FORMAT_RE = re.compile(
    r"\b(json|csv|xml|yaml|markdown|table|bullet(?:ed)?|numbered list|"
    r"checklist|sentences?|paragraphs?|docstring|tagline|haiku|"
    r"subject line|one[- ]line|two[- ]line|three[- ]line|iso format|"
    r"iso 8601)\b",
    re.IGNORECASE,
)

_REASONING_WORDS = (
    "because", "therefore", "since", "thus", "hence", "so that", "due to",
    "given that", "reason", "why", "step", "consequently",
)
_REASONING_WORD_RE = re.compile(
    r"\b(?:" + "|".join(_REASONING_WORDS) + r")\b", re.IGNORECASE
)

_NUMERIC_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?")


def extract_features(prompt: str) -> dict:
    """Compute the 8 surface features for a single prompt string."""
    return {
        "length": len(prompt.split()),
        "instruction_verb_count": len(_INSTRUCTION_VERB_RE.findall(prompt)),
        "constraint_count": len(_NUMERIC_CONSTRAINT_RE.findall(prompt)),
        "context_present": "\n" in prompt.strip(),
        "output_format_specified": bool(_OUTPUT_FORMAT_RE.search(prompt)),
        "reasoning_word_count": len(_REASONING_WORD_RE.findall(prompt)),
        "question_count": prompt.count("?"),
        "numeric_token_count": len(_NUMERIC_TOKEN_RE.findall(prompt)),
    }


def features_to_vector(features: dict) -> list[float]:
    """Flatten a features dict into the fixed-order numeric vector
    LogisticRegression expects, in FEATURE_NAMES order."""
    return [float(features[name]) for name in FEATURE_NAMES]
