"""Auto-labeller: derive the cheapest judge-passing tier for every
currently-UNLABELLED `data/prompts.json` row (`tier is None`) so the
~140 blanks can be filled and the classifier retrained on more than the
operator's original 60 hand-labelled rows.

For each unlabelled prompt: run it through the real router pipeline with
`forced_tier="local"` and the judge sampled at 1.0 (auto-labelling
REQUIRES a judge on every prompt -- there is no other way to know whether
`local` was good enough). Judge/escalate then does what it already does
for every request (judge.py, ADR 0001): local's answer is judged by
sonnet; if it scores below the use case's threshold, escalate one tier
and judge the sonnet answer with opus; if that also fails, escalate to
opus, which is the ceiling and is never judged (never rejected). The
FINAL `tier_chosen` persisted for that run -- after judge/escalate has
finished -- is the cheapest tier that passed, i.e. the derived label.

Like battery.py, this module does NOT reimplement classify -> route ->
answer -> judge -> escalate. It builds the same FastAPI app api.py's
`create_app()` builds and drives it through `POST /v1/completions` (then
reads the final persisted row back via `GET /runs/{id}/spans`) via
Starlette's TestClient, which runs the whole ASGI request -- including
the `BackgroundTask` that schedules `judge.judge_and_escalate` -- to
completion before the call returns. Resumable checkpointing and
retry/backoff are reused directly from battery.py (`with_retry`,
`load_progress`/`save_progress`) rather than duplicated here; the ONE
thing genuinely new here is forcing `judge_sample_rate` to 1.0 for the
run without mutating the operator's live, editable routing.yaml, and
writing the derived-label mapping to `data/auto_labels.json`.

This is a PAID run against real models exactly like battery.py, and is
gated the same way: nothing here calls a real model unless `main()` runs
with `--dry-run` omitted, and `main()` only ever runs under
`if __name__ == "__main__":`.

`--merge` (separate, FREE, no model calls) reads `data/auto_labels.json`
and fills the derived tier into every still-null row of
`data/prompts.json`, stamping `tier_source` on every row ("hand" for the
operator's original labels, "judge_auto" for a row this merge just
filled) so the two provenances stay distinguishable in the README. It
never overwrites an already-non-null tier.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

import yaml
from fastapi.testclient import TestClient

import battery
import train
from api import create_app
from task_router import routing_config as routing_config_module
from task_router.fake_provider import FakeProvider
from task_router.providers import send as default_send

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_PROMPTS_PATH = REPO_ROOT / "data" / "prompts.json"
DEFAULT_PROGRESS_PATH = REPO_ROOT / "data" / "auto_label_progress.json"
DEFAULT_AUTO_LABELS_PATH = REPO_ROOT / "data" / "auto_labels.json"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "auto_label.sqlite"

# Reused, not re-picked: the same generous default as battery.py, for the
# same reason (a real Max-plan usage-limit window resets on the order of
# hours, not seconds).
DEFAULT_MAX_RETRIES = battery.DEFAULT_MAX_RETRIES
DEFAULT_BACKOFF_BASE_S = battery.DEFAULT_BACKOFF_BASE_S

HAND_SOURCE = "hand"
JUDGE_AUTO_SOURCE = "judge_auto"

# Re-exported so tests/callers can use auto_label.load_progress /
# save_progress without reaching into battery.py directly -- same
# checkpoint file shape ({"completed": {...}, "failed": {...}}).
load_progress = battery.load_progress
save_progress = battery.save_progress


def load_unlabelled_rows(prompts_path: Path = DEFAULT_PROMPTS_PATH) -> list[dict]:
    """Rows the operator has NOT hand-labelled yet (`tier is None`) --
    the mirror image of train.py's `filter_labelled` / battery.py's
    `load_labelled_rows`. Reuses `train.load_prompts` rather than
    re-deriving prompts.json's own load logic here."""
    return [r for r in train.load_prompts(prompts_path) if r.get("tier") is None]


@contextlib.contextmanager
def forced_judge_sample_rate_config(routing_config_path: Optional[Path] = None):
    """Auto-labelling requires the judge to run on every single prompt --
    there is no other way to discover whether `local`'s answer was good
    enough. Yields a path to a TEMP copy of the real routing.yaml (or
    whichever config `routing_config_path` points at) with
    `judge_sample_rate` forced to 1.0, so a live operator config with a
    lower sample rate (dialed down after the S7 battery, per routing.yaml's
    own comment) doesn't silently skip prompts here. The temp file is
    deleted on exit; the operator's own routing.yaml is never written to.
    """
    config = dict(routing_config_module.load_config(routing_config_path))
    config["judge_sample_rate"] = 1.0
    fd, tmp_name = tempfile.mkstemp(suffix=".yaml", prefix="auto_label_routing_")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, sort_keys=False)
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)


def save_auto_labels(path: Path, progress: dict) -> None:
    """Write-then-rename (same pattern as battery.py's `save_progress`) so
    an interruption never leaves a truncated `auto_labels.json` behind.
    Derived straight from `progress["completed"]` -- there is no separate
    source of truth for the label mapping."""
    labels = {
        prompt_id: outcome["derived_tier"]
        for prompt_id, outcome in progress["completed"].items()
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(labels, f, indent=2, sort_keys=True)
    tmp.replace(path)


def format_auto_label_summary(progress: dict) -> str:
    counts: dict[str, int] = {}
    for outcome in progress["completed"].values():
        tier = outcome["derived_tier"]
        counts[tier] = counts.get(tier, 0) + 1
    lines = [
        "--- auto-label summary ---",
        f"n_labelled = {len(progress['completed'])}",
        f"by_derived_tier = {counts}",
        f"n_failed = {len(progress['failed'])}",
    ]
    if progress["failed"]:
        lines.append(f"failed_ids = {sorted(progress['failed'])}")
    return "\n".join(lines)


def run_auto_label(
    *,
    prompts_path: Path = DEFAULT_PROMPTS_PATH,
    progress_path: Path = DEFAULT_PROGRESS_PATH,
    auto_labels_path: Path = DEFAULT_AUTO_LABELS_PATH,
    db_path: Optional[Path] = None,
    routing_config_path: Optional[Path] = None,
    send_fn: Optional[Callable[[str, str], dict]] = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
    sleep_fn: Callable[[float], None] = time.sleep,
    print_fn: Callable[[str], None] = print,
) -> dict:
    """Run the unlabelled-prompt auto-label pass once, skipping any prompt
    id already recorded under `progress["completed"]` (resumable, exactly
    like battery.py's `run_battery`, across an interruption or a usage
    cap). Returns the final progress dict; also writes
    `data/auto_labels.json` after every prompt.

    `send_fn` defaults to the real `providers.send` (wrapped with retry
    via `battery.with_retry`) -- pass a fake for tests/dry-run.

    Never raises: a prompt that still fails after retries is recorded
    under `progress["failed"]` and the loop continues (same contract as
    battery.py).
    """
    rows = load_unlabelled_rows(prompts_path)
    progress = load_progress(progress_path)

    base_send = send_fn or default_send
    retrying_send = battery.with_retry(
        base_send,
        max_retries=max_retries,
        backoff_base_s=backoff_base_s,
        sleep_fn=sleep_fn,
    )

    with forced_judge_sample_rate_config(routing_config_path) as forced_config_path:
        app = create_app(
            db_path=db_path,
            send_fn=retrying_send,
            routing_config_path=forced_config_path,
        )
        client = TestClient(app)

        total = len(rows)
        already_done = sum(1 for r in rows if r["id"] in progress["completed"])
        print_fn(
            f"auto_label: {total} unlabelled row(s), {already_done} already completed, resuming"
        )

        for i, row in enumerate(rows, start=1):
            prompt_id = row["id"]
            if prompt_id in progress["completed"]:
                continue

            print_fn(f"[{i}/{total}] {prompt_id} ({row['use_case']}) ...")
            resp = client.post(
                "/v1/completions",
                json={
                    "prompt": row["prompt"],
                    "use_case": row["use_case"],
                    "forced_tier": "local",
                },
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
            # Read the FINAL persisted row (post background judge/escalation
            # -- already complete by the time TestClient's .post() returned)
            # back through the existing read API, same reuse-not-duplicate
            # rule battery.py follows.
            run = client.get(f"/runs/{run_id}/spans").json()["run"]

            outcome = {
                "run_id": run_id,
                "derived_tier": run["tier_chosen"],
                "escalated": bool(run["escalated"]),
                "judge_score": run["judge_score"],
            }
            progress["completed"][prompt_id] = outcome
            progress["failed"].pop(prompt_id, None)
            print_fn(
                f"  ok: derived_tier={outcome['derived_tier']} "
                f"escalated={outcome['escalated']} judge_score={outcome['judge_score']}"
            )
            save_progress(progress_path, progress)
            save_auto_labels(auto_labels_path, progress)

    save_auto_labels(auto_labels_path, progress)
    print_fn(format_auto_label_summary(progress))
    return progress


def merge_auto_labels(
    *,
    prompts_path: Path = DEFAULT_PROMPTS_PATH,
    auto_labels_path: Path = DEFAULT_AUTO_LABELS_PATH,
    print_fn: Callable[[str], None] = print,
) -> dict:
    """FREE, no model calls: fill the derived tier from
    `data/auto_labels.json` into every still-null row of
    `data/prompts.json`, and stamp `tier_source` on every row -- "hand"
    for a row that already had a non-null tier (the operator's original
    60), "judge_auto" for a row this merge just filled. Never overwrites
    an already-non-null tier: a row that is somehow both hand-labelled and
    present in auto_labels.json (e.g. hand-labelled after an auto-label
    run) keeps its hand label and gets tier_source="hand", silently.
    """
    rows = train.load_prompts(prompts_path)
    with Path(auto_labels_path).open("r", encoding="utf-8") as f:
        auto_labels = json.load(f)

    n_filled = 0
    n_already_hand = 0
    n_still_unlabelled = 0
    for row in rows:
        if row.get("tier") is not None:
            row["tier_source"] = HAND_SOURCE
            n_already_hand += 1
            continue
        derived = auto_labels.get(row["id"])
        if derived is None:
            n_still_unlabelled += 1
            continue
        row["tier"] = derived
        row["tier_source"] = JUDGE_AUTO_SOURCE
        n_filled += 1

    with Path(prompts_path).open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
        f.write("\n")

    summary = {
        "n_filled": n_filled,
        "n_already_hand": n_already_hand,
        "n_still_unlabelled": n_still_unlabelled,
    }
    print_fn(
        f"merge: filled {n_filled} row(s) with judge_auto tiers, "
        f"{n_already_hand} already hand-labelled, "
        f"{n_still_unlabelled} still unlabelled (no auto_labels.json entry)"
    )
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Derive the cheapest judge-passing tier for every unlabelled "
            "data/prompts.json row (real claude -p / Ollama calls unless "
            "--dry-run). Resumable: re-running continues where it left off. "
            "--merge is free (no model calls): fills the derived labels "
            "into data/prompts.json."
        )
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Free, no model calls: merge data/auto_labels.json into data/prompts.json.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Use an in-process fake provider instead of real Ollama/claude -p calls "
            "-- for smoke-testing the auto-label loop itself. Never used for the "
            "real run."
        ),
    )
    parser.add_argument("--prompts-path", type=Path, default=DEFAULT_PROMPTS_PATH)
    parser.add_argument("--progress-path", type=Path, default=DEFAULT_PROGRESS_PATH)
    parser.add_argument("--auto-labels-path", type=Path, default=DEFAULT_AUTO_LABELS_PATH)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--routing-config-path", type=Path, default=None)
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument("--backoff-base-s", type=float, default=DEFAULT_BACKOFF_BASE_S)
    args = parser.parse_args(argv)

    if args.merge:
        merge_auto_labels(
            prompts_path=args.prompts_path,
            auto_labels_path=args.auto_labels_path,
        )
        return 0

    send_fn = None
    if args.dry_run:
        send_fn = FakeProvider(text="dry-run answer", input_tokens=50, output_tokens=20).send

    run_auto_label(
        prompts_path=args.prompts_path,
        progress_path=args.progress_path,
        auto_labels_path=args.auto_labels_path,
        db_path=args.db_path,
        routing_config_path=args.routing_config_path,
        send_fn=send_fn,
        max_retries=args.max_retries,
        backoff_base_s=args.backoff_base_s,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
