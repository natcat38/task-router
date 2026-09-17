# task-router

Status: in development.

A solo developer who pays for one LLM subscription and writes small scripts
against it — a changelog formatter, a data cleaner, a quick classifier — has
no reason to send every one of those requests to the same expensive model.
task-router routes each request to a cheap tier by default, catches the cheap
tier when it is wrong with an async judge one tier above, and escalates only
when needed. Its differentiator over existing LLM-observability tools is
whole-pipeline replay: any past request can be re-run with a different tier
forced, replaying classify → route → answer → judge → escalate, not just
swapping the model on a stored prompt.

## Run

Setup and run instructions land in slice S0. Nothing here is runnable yet.

## Docs

- [`docs/Product_Scope.md`](docs/Product_Scope.md) — what this is and why
- [`docs/Tech_Scope.md`](docs/Tech_Scope.md) — stack, data model, vertical slices
- [`docs/adr/`](docs/adr) — architecture decisions
- [`knowledge/`](knowledge) — OKF knowledge bundle
