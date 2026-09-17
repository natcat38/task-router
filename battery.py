"""S7: run the labelled `data/prompts.json` rows through the router once,
end to end, with the judge sampled at 1.0 (Tech_Scope.md §5 S7 row / §6;
Product_Scope.md §3.2; ADR 0001).

This is a PAID run against real models (claude -p on the Max subscription,
plus a running local Ollama) and is gated on the operator's explicit "go" --
nothing in this module calls a real model unless `main()` runs with
`--dry-run` omitted, and `main()` only ever runs under
`if __name__ == "__main__":` (Tech_Scope §5 S7 test strategy: "the real run
happens exactly once, manually triggered, never in CI").

battery.py does NOT reimplement classify -> route -> answer -> judge ->
escalate. It builds the exact same FastAPI app api.py's `create_app()`
builds and drives it through `POST /v1/completions` (then reads the final
persisted row back via the existing `GET /runs/{id}/spans` read API) via
Starlette's TestClient -- which runs the whole ASGI request, including the
`BackgroundTask` that schedules `judge.judge_and_escalate`, to completion
before the call returns. That is the ONE mechanism this module relies on to
avoid duplicating routing/judge/escalation logic: every behaviour below is
either (a) already in api.py/judge.py, exercised through its real HTTP
surface, or (b) genuinely new to the battery -- resumable checkpointing and
retry/backoff -- and nothing else.

Resumable & paced (claude-p-backend.md §2/§5): Max plan usage resets on a
rolling 5-hour window (~225 messages/5h on Max 5x is the binding
constraint, not token cost), so a battery of ~120-150 real calls plus an
Opus-judge step (near-doubling the call count) is expected to span >=2
windows and to survive being interrupted by a usage-limit response mid-run.
Progress is checkpointed to `data/battery_progress.json` after every
prompt, keyed by prompt id, so re-running `battery.py` skips whatever
already completed and continues; the docs don't give an exact
token-to-message conversion for a usage-limit response, so a provider error
that LOOKS like a usage/rate limit (see `is_usage_limit_error`) gets a
bounded exponential backoff-and-retry inside a single prompt's attempt, and
a prompt that still fails after that is recorded under
`progress["failed"]` and the run moves on to the next prompt rather than
crashing (claude-p-backend.md §5).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Callable, Optional

from fastapi.testclient import TestClient

import train
from api import create_app
from task_router import routing_config as routing_config_module
from task_router.fake_provider import FakeProvider
from task_router.providers import send as default_send

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_PROMPTS_PATH = REPO_ROOT / "data" / "prompts.json"
DEFAULT_PROGRESS_PATH = REPO_ROOT / "data" / "battery_progress.json"

HONESTY_LABEL = "API list prices; no money changed hands"

DEFAULT_MAX_RETRIES = 5
# Generous default: a real Max-plan usage-limit window resets on the order
# of hours, not seconds, so a short backoff would just burn through retries
# uselessly. --backoff-base-s is overridable from the CLI for a shorter wait
# when smoke-testing the retry path against a script that recovers fast.
DEFAULT_BACKOFF_BASE_S = 30.0

# Heuristic, not a structured field: providers.py's claude_cli/ollama paths
# both surface a failure as a plain `error` string (exit code + stderr, or a
# transport exception), not the CLI's own JSON `subtype`
# (`error_max_budget_usd` etc, claude-p-backend.md §1) -- so this matches on
# the kind of wording Anthropic's support/CLI docs use for an
# exhausted-usage response. A false positive just costs a few retries before
# giving up anyway; a false negative just skips straight to "record and
# move on" (also safe) -- neither failure mode corrupts anything.
_USAGE_LIMIT_MARKERS = (
    "usage limit",
    "rate limit",
    "rate_limit",
    "429",
    "quota",
    "resets at",
    "try again later",
    "overloaded",
)


def is_usage_limit_error(error: Optional[str]) -> bool:
    """Does this provider error look like a usage/rate-limit response
    rather than a hard failure (bad model id, malformed JSON, connection
    refused)? See module-level note above for why this is a heuristic."""
    if not error:
        return False
    lowered = error.lower()
    return any(marker in lowered for marker in _USAGE_LIMIT_MARKERS)


def with_retry(
    base_send_fn: Callable[[str, str], dict],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
    sleep_fn: Callable[[float], None] = time.sleep,
    retry_log: Optional[list] = None,
) -> Callable[[str, str], dict]:
    """Wrap a providers.send-shaped function (never raises) with
    retry/backoff on a usage-limit-looking error.

    This is the ONE place battery.py adds behaviour beyond the existing
    pipeline: whatever is returned here is handed to `api.create_app()` as
    `send_fn`, so every call the pipeline itself makes -- the answer, the
    judge call, the re-answer on escalation -- gets the same retry
    treatment for free, without battery.py ever touching routing/judge/
    escalation logic directly.

    Backs off `backoff_base_s * 2**attempt` seconds between attempts (0,
    1, 2, ... up to `max_retries` retries beyond the first try). A call
    that still errors with a usage-limit-looking message after all retries
    is returned as-is (its `error` field intact) so the caller (api.py's
    pipeline, and ultimately `run_battery`) can record it and move on
    rather than crash the whole run.
    """

    def wrapped(prompt: str, model: str) -> dict:
        attempt = 0
        while True:
            result = base_send_fn(prompt, model)
            if not result.get("error") or not is_usage_limit_error(result["error"]):
                return result
            if attempt >= max_retries:
                return result
            wait_s = backoff_base_s * (2**attempt)
            if retry_log is not None:
                retry_log.append(
                    {
                        "model": model,
                        "attempt": attempt + 1,
                        "error": result["error"],
                        "wait_s": wait_s,
                    }
                )
            sleep_fn(wait_s)
            attempt += 1

    return wrapped


def load_progress(path: Path) -> dict:
    """The checkpoint file: `{"completed": {prompt_id: outcome}, "failed":
    {prompt_id: {"error": ...}}}`. Missing file (first run ever) is an
    empty checkpoint, not an error."""
    p = Path(path)
    if not p.exists():
        return {"completed": {}, "failed": {}}
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("completed", {})
    data.setdefault("failed", {})
    return data


def save_progress(path: Path, progress: dict) -> None:
    """Write-then-rename so an interruption mid-write (a usage-limit
    response arriving, the process being killed) never leaves a truncated,
    unreadable progress file behind for the next resumed run to trip over."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, sort_keys=True)
    tmp.replace(path)


def load_labelled_rows(prompts_path: Path = DEFAULT_PROMPTS_PATH) -> list[dict]:
    """Labelled-only rows (tier is not null) -- reuses train.py's own
    filter (rather than re-deriving the same `tier is not None` check
    here) so battery.py and train.py can never quietly disagree about what
    counts as labelled (Tech_Scope §6: running either script over the
    unlabelled rows is silent corruption, not a feature)."""
    return train.filter_labelled(train.load_prompts(prompts_path))


def compute_summary(client: TestClient, progress: dict) -> dict:
    """Reuse the real `GET /v1/stats` endpoint (same savings-percentage
    math api.py already implements and tests) rather than recomputing the
    with/without-judge savings formula here. `client`'s app must be backed
    by the same DB the battery just wrote to, so the stats reflect exactly
    the rows this run (plus any prior resumed runs) produced. Escalation
    count is battery-specific bookkeeping (not part of `/v1/stats`), added
    alongside it.
    """
    stats = client.get("/v1/stats").json()
    n_escalated = sum(1 for o in progress["completed"].values() if o.get("escalated"))
    return {**stats, "n_escalated": n_escalated}


def format_summary(summary: dict) -> str:
    lines = [
        "--- battery summary ---",
        f"n_requests = {summary['n_requests']}",
        f"by_tier = {summary['by_tier']}",
        f"n_escalated = {summary['n_escalated']}",
        f"saved_pct_excl_judge = {summary['saved_pct_excl_judge']:.1f}%",
        f"saved_pct_incl_judge = {summary['saved_pct_incl_judge']:.1f}%",
        HONESTY_LABEL,
    ]
    return "\n".join(lines)


def run_battery(
    *,
    prompts_path: Path = DEFAULT_PROMPTS_PATH,
    progress_path: Path = DEFAULT_PROGRESS_PATH,
    db_path: Optional[Path] = None,
    routing_config_path: Optional[Path] = None,
    send_fn: Optional[Callable[[str, str], dict]] = None,
    select_tier_fn=None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
    sleep_fn: Callable[[float], None] = time.sleep,
    print_fn: Callable[[str], None] = print,
) -> dict:
    """Run the labelled-prompt battery once, skipping any prompt id already
    recorded under `progress["completed"]` (resumable across an
    interruption or a usage cap, and across >=2 five-hour windows --
    claude-p-backend.md §5). Returns the final progress dict.

    `send_fn` defaults to the real `providers.send` (wrapped with retry) --
    pass a fake for tests/dry-run. `select_tier_fn` defaults to the real
    trained classifier (or its heuristic fallback) via api.py's own
    default, exactly as a live request would route.

    ADR 0001 / Tech_Scope §2 call for `judge_sample_rate: 1.0` during the
    battery. This function does not silently rewrite the operator's
    routing.yaml to force that -- it only warns if the loaded config's rate
    isn't 1.0, since routing.yaml is a live, operator-editable file
    (Tech_Scope §4) and a surprise overwrite is worse than a warning here.

    Never raises: a prompt that still fails after `with_retry`'s bounded
    retries is recorded under `progress["failed"]` and the loop continues.
    """
    rows = load_labelled_rows(prompts_path)
    progress = load_progress(progress_path)

    try:
        config = routing_config_module.load_config(routing_config_path)
        sample_rate = config.get("judge_sample_rate", 0.0)
        if sample_rate != 1.0:
            print_fn(
                f"WARNING: judge_sample_rate is {sample_rate}, not 1.0 -- ADR 0001 calls "
                "for 1.0 during the battery so every routed answer is checked while the "
                "classifier is unproven. Continuing anyway; routing.yaml is not being "
                "rewritten automatically."
            )
    except FileNotFoundError:
        pass

    base_send = send_fn or default_send
    retrying_send = with_retry(
        base_send,
        max_retries=max_retries,
        backoff_base_s=backoff_base_s,
        sleep_fn=sleep_fn,
    )

    app = create_app(
        db_path=db_path,
        send_fn=retrying_send,
        select_tier_fn=select_tier_fn,
        routing_config_path=routing_config_path,
    )
    client = TestClient(app)

    total = len(rows)
    already_done = sum(1 for r in rows if r["id"] in progress["completed"])
    print_fn(f"battery: {total} labelled row(s), {already_done} already completed, resuming")

    for i, row in enumerate(rows, start=1):
        prompt_id = row["id"]
        if prompt_id in progress["completed"]:
            continue

        print_fn(f"[{i}/{total}] {prompt_id} ({row['use_case']}) ...")
        resp = client.post(
            "/v1/completions",
            json={"prompt": row["prompt"], "use_case": row["use_case"]},
        )

        if resp.status_code != 200:
            try:
                error = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
            except (ValueError, AttributeError):
                error = f"HTTP {resp.status_code}"
            progress["failed"][prompt_id] = {"error": error}
            print_fn(f"  FAILED: {error}")
            save_progress(progress_path, progress)
            continue

        run_id = resp.json()["run_id"]
        # Read the FINAL persisted row (post background judge/escalation --
        # already complete by the time TestClient's .post() returned) back
        # through the existing read API rather than opening our own SQLite
        # connection -- same reuse-not-duplicate rule as the pipeline call
        # above.
        run = client.get(f"/runs/{run_id}/spans").json()["run"]

        outcome = {
            "run_id": run_id,
            "tier_chosen": run["tier_chosen"],
            "model_used": run["model_used"],
            "escalated": bool(run["escalated"]),
            "judge_score": run["judge_score"],
            "judge_cost": run["judge_cost"],
            "cost_all_tiers": run["cost_all_tiers"],
        }
        progress["completed"][prompt_id] = outcome
        progress["failed"].pop(prompt_id, None)
        print_fn(
            f"  ok: tier={outcome['tier_chosen']} escalated={outcome['escalated']} "
            f"judge_score={outcome['judge_score']}"
        )
        save_progress(progress_path, progress)

    print_fn(format_summary(compute_summary(client, progress)))
    return progress


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the S7 labelled-prompt battery once (real claude -p / Ollama calls "
            "unless --dry-run). Resumable: re-running continues where it left off."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Use an in-process fake provider instead of real Ollama/claude -p calls -- "
            "for smoke-testing the battery loop itself. Never used for the real S7 run."
        ),
    )
    parser.add_argument("--prompts-path", type=Path, default=DEFAULT_PROMPTS_PATH)
    parser.add_argument("--progress-path", type=Path, default=DEFAULT_PROGRESS_PATH)
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--routing-config-path", type=Path, default=None)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--backoff-base-s", type=float, default=DEFAULT_BACKOFF_BASE_S)
    args = parser.parse_args(argv)

    send_fn = None
    if args.dry_run:
        send_fn = FakeProvider(text="dry-run answer", input_tokens=50, output_tokens=20).send

    run_battery(
        prompts_path=args.prompts_path,
        progress_path=args.progress_path,
        db_path=args.db_path,
        routing_config_path=args.routing_config_path,
        send_fn=send_fn,
        max_retries=args.max_retries,
        backoff_base_s=args.backoff_base_s,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
