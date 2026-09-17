"""S1 baseline: send 10 prompts through each of the 3 registry models and
print one table (model, tier, avg latency, avg tokens, total cost at list
prices, failures) -- Tech_Scope.md §5, S1 row.

This is a paid run against real models (claude -p on the Max subscription,
plus a running local Ollama). It is gated on the user's later "go": the
aggregation/table logic (`run_baseline`, `summarize`, `format_table`) is
unit-tested against the fake provider only (tests/test_baseline.py), and
the live entry point is guarded by `if __name__ == "__main__":` so
importing this module for tests never calls a real model.
"""

from __future__ import annotations

from task_router.providers import send
from task_router.registry import load_registry

HONESTY_LABEL = "API list prices; no money changed hands"

PROMPTS = [
    "Summarise the plot of a two-sentence short story about a lighthouse keeper.",
    "List three benefits of unit testing.",
    "Rewrite this sentence in passive voice: The cat chased the mouse.",
    "What is the capital of Australia?",
    "Extract the numbers from this text: I have 3 apples and 12 oranges.",
    "Classify this review as positive or negative: 'The food was cold and slow to arrive.'",
    "Explain what a hash map is in one paragraph.",
    "Write a haiku about autumn rain.",
    "Convert 98.6 Fahrenheit to Celsius.",
    "Give one pro and one con of remote work.",
]

MODELS = ["qwen3:1.7b", "sonnet", "opus"]


def run_baseline(send_fn, prompts, models) -> dict:
    """Call `send_fn(prompt, model)` for every prompt x model. Never raises
    -- `send_fn` (production: providers.send) already guarantees that."""
    results: dict[str, list[dict]] = {model: [] for model in models}
    for model in models:
        for prompt in prompts:
            results[model].append(send_fn(prompt, model))
    return results


def summarize(results: dict) -> dict:
    """Reduce raw per-call results to one summary row per model.

    Averages (latency, tokens) are computed over successful calls only --
    a failed call has no latency/token reading worth averaging in. Total
    cost sums every successful call's cost (failed calls cost nothing).
    """
    summary = {}
    for model, calls in results.items():
        successes = [c for c in calls if c["error"] is None]
        failures = [c for c in calls if c["error"] is not None]
        n = len(successes)

        summary[model] = {
            "failures": len(failures),
            "avg_latency": (sum(c["latency"] for c in successes) / n) if n else 0.0,
            "avg_input_tokens": (sum(c["input_tokens"] for c in successes) / n) if n else 0.0,
            "avg_output_tokens": (sum(c["output_tokens"] for c in successes) / n) if n else 0.0,
            "total_cost": sum(c["cost"] for c in successes),
        }
    return summary


def format_table(summary: dict) -> str:
    registry = load_registry()
    header = f"{'model':<12} {'tier':<8} {'avg_latency_s':>14} {'avg_in_tok':>11} {'avg_out_tok':>12} {'total_cost_usd':>15} {'failures':>9}"
    lines = [header, "-" * len(header)]
    for model, row in summary.items():
        tier = registry.by_id(model).tier
        lines.append(
            f"{model:<12} {tier:<8} {row['avg_latency']:>14.3f} "
            f"{row['avg_input_tokens']:>11.1f} {row['avg_output_tokens']:>12.1f} "
            f"{row['total_cost']:>15.6f} {row['failures']:>9}"
        )
    lines.append("")
    lines.append(HONESTY_LABEL)
    return "\n".join(lines)


if __name__ == "__main__":
    raw_results = run_baseline(send, PROMPTS, MODELS)
    print(format_table(summarize(raw_results)))
