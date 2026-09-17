# 0003: Cloud tiers run on the subscription via unmodified `claude -p`; API-key provider defined but unused

## Status
Accepted

## Context
The original plan (D4, a stretch goal) was to put the router in front of the operator's own daily Claude Code usage — i.e. have the operator's interactive Claude Code sessions route through this project's gateway. That is infeasible and was dropped: Claude Code's subscription (OAuth) auth does not route through a custom gateway URL without forwarding the operator's session token to that gateway, and `code.claude.com/docs/en/legal-and-compliance` prohibits developers from intermediating or forwarding Claude.ai credentials/session tokens on behalf of users (`REFUTATIONS.md` #16, `claude-p-backend.md` §3). Nothing in this build is sized for that stretch goal.

Separately, `claude -p` itself has two auth modes that matter for this project: run normally (OAuth, draws from the operator's own subscription usage pool) or run with `--bare` (skips OAuth/keychain entirely and requires `ANTHROPIC_API_KEY`, i.e. pay-per-token API billing — `claude-p-backend.md` §1). `claude-p-backend.md` §3 is explicit that a personal, local, single-user, unmodified-binary demo — one person's own machine, their own login, only they hit the endpoint — reads as "ordinary use" the OAuth grant is meant for. A publicly reachable, multi-tenant deployment is the pattern the legal page targets and forbids under subscription credentials; that would need its own `ANTHROPIC_API_KEY`, billed per token, to be permissible.

## Decision
Cloud-tier calls (Sonnet, Opus) run locally through the unmodified `claude -p --output-format json` binary, authenticated via OAuth against the operator's own subscription. `--bare` is never used, because it silently drops OAuth and forces API-key billing. A second provider, using `ANTHROPIC_API_KEY` against the direct Anthropic API, is defined behind the same `send(prompt, model)` interface as the `claude -p` provider — but it is not exercised anywhere in this build. It exists so a future hosted/public deployment (the kind of deployment that would require API-key billing per the legal page) can swap providers without changing the router, classifier, or any call site.

## Consequences
- All savings figures in this project ("saved vs all-Opus", `GET /v1/stats`) are computed against `registry.yaml` **API list prices** even though every call in this build actually runs on the subscription and bills nothing per-call. Per D10, every savings figure is labelled "at API list prices; no money changed hands" — it is a demonstration of what routing *would* save under API billing, not a record of an actual bill.
- Because the demo never runs `--bare` or sets `ANTHROPIC_API_KEY` for real calls, there is no live test coverage of the API-key provider path. It is implemented and unit-testable against the fake provider interface, but anyone standing up a hosted deployment from this code should treat the API-key provider as unverified against a real endpoint until they run it.
- The dropped D4 stretch (routing the operator's own interactive Claude Code through this gateway) is not designed around, not partially built, and not left as a "future work" item requiring architecture changes — the provider interface's only nod to a future hosted use case is the unused API-key slot, which serves a different use case (public deployment) than D4's (personal daily driver) did.

## Alternatives Considered

### Use `--bare` with `ANTHROPIC_API_KEY` for everything, even locally
- Pros: deterministic billing, no ambiguity about which usage pool a call draws from, one code path for local and hosted.
- Cons: costs real money for a portfolio demo that has no budget for it; contradicts D10's "no money changed hands" framing; loses the point of demonstrating subscription-based cost-free local iteration.
- Rejected: the whole premise of the demo is a solo developer on a subscription plan (D8) routing cheap-first without a per-call bill.

### Build and exercise the API-key provider now, running part of the battery against it
- Pros: proves the swap works end to end, not just at the interface level.
- Cons: spends real API-list-price money that isn't budgeted; D10 explicitly rules out mixing real billing into the demo's numbers, since it would need to be disentangled from the "no money changed hands" figures.
- Rejected: out of scope for this build; documented as the reason the interface exists rather than exercised.
