# Design Direction: Task Router UI

Status: BUILD stage, written just before S6 per `ROADMAP.md` §2. Grounds the
dashboard in its own subject matter — a distributed-tracing / observability
tool for a routing decision, not a generic admin panel. Self-check applied:
the generic default for "LLM dashboard" right now is a warm-cream/serif
hero or a near-black page with one violet accent and rounded SaaS cards.
This direction is neither — it's built to look like a trace/log viewer a
backend engineer already trusts (Jaeger, Honeycomb, a terminal), because
that is exactly the audience (Product_Scope §1: a solo developer who wants
to see *why*, not a marketing surface).

## Palette

Base UI palette — five named colors, blue-slate rather than true black or
warm cream, because this is a *reading* tool (long sessions scanning spans
and numbers), not a landing page:

| Name | Hex | Role |
|---|---|---|
| `--ink` | `#0F1417` | App background. Blue-slate near-black, not `#0B0B0B` flat black. |
| `--panel` | `#161D22` | Card / row / nav-rail surface, one step up from ink. |
| `--line` | `#2A343B` | Hairline borders, table rules, the waterfall's time-axis ticks. |
| `--fog` | `#8A97A0` | Secondary text — timestamps, helper copy, empty-state body text. |
| `--signal` | `#E8EDEF` | Primary text, active nav item, focus ring color. |

## The signature element: tier color as a running signal

The one thing that repeats everywhere, always meaning the same thing, is
the **tier-color system** — it is the answer to "why did this go here,"
which is the entire point of the product (Product_Scope §1–§2):

| Tier | Hex | Feel |
|---|---|---|
| `local` | `#46C2B0` (teal) | cool, cheap, fast |
| `sonnet` | `#E8A33D` (amber) | mid — the escalation destination for local |
| `opus` | `#D65D8C` (rose) | top of the chain — deliberately *not* terracotta/orange, so it never reads as "the Anthropic brand color" |

These three colors appear as: a small filled dot + monospace label (the
"tier chip," used in the nav legend, run-list rows, and stats), the fill
color of each span bar in the waterfall, and the accent color of a replay
diff row when a tier changed. Nowhere else in the UI is color used for
meaning — everything else is ink/panel/line/fog/signal. One signature,
applied consistently, beats five decorative accents.

## Typefaces

Two families, one pairing that is itself on-brand for a technical-tracing
tool (IBM Plex was designed for IBM's own developer/enterprise tools —
this is a deliberate pick, not the Inter-everywhere default):

| Family | Role |
|---|---|
| **IBM Plex Sans** | UI chrome — nav, headings, body copy, buttons. |
| **IBM Plex Mono** | All data: run IDs, timestamps, span names, ns durations, JSON attributes, prices. If it came out of the API as a value rather than a label, it's set in Plex Mono. |

Type scale (Plex Sans unless noted): page title 22px/600, section heading
16px/600, body 14px/400, Plex Mono data 13px/500 with slightly increased
letter-spacing (0.01em) for scanability in tables.

## Layout concept

A left nav rail, not a top nav bar — trace viewers are read top-to-bottom
inside a page, so the wayfinding chrome belongs on the side, out of the
reading column. Content is left-aligned throughout; nothing here is centered
marketing copy.

```
┌────────┬──────────────────────────────────────────┐
│ router │  Runs                          [filters]  │
│        │  ──────────────────────────────────────  │
│ ● Runs │  run_id   tier●  use_case  status   time  │
│ ○ Stats│  ──────────────────────────────────────  │
│        │  a3f9e1   ●local extract   ok      12:04  │
│ ● local│  b2c810   ●sonnet summ.    ok      12:03  │
│ ● sonnt│  ...                                      │
│ ● opus │                                            │
└────────┴──────────────────────────────────────────┘
```

The nav rail carries the tier legend permanently at its bottom — a constant
reminder of what the three dots mean, since it's the vocabulary the whole
app is built on. On the waterfall page, span bars stack vertically against
a shared horizontal time axis (ticked in `--line`, labelled in Plex Mono),
each bar filled in its tier color — this *is* the oscilloscope-trace
feeling: parallel signals against one shared clock.

Below 768px the rail collapses to a slim icon-only strip; below 375px it
becomes a top bar with a menu toggle, content goes full width, and tables
switch to stacked key/value rows instead of horizontal scroll.

## Loading / empty / error states

Copy is in the interface's voice — states explain, they don't apologize:

| State | Copy |
|---|---|
| Runs list, loading | `Reading runs…` |
| Runs list, empty | `No runs yet. Send a request to POST /v1/completions and it'll show up here.` |
| Runs list, error | `Couldn't reach the router API at {base URL}. Check it's running, then retry.` + a Retry button |
| Waterfall, loading | `Reading trace…` |
| Waterfall, not found | `No run with this ID. It may have aged out or the ID is wrong.` |
| Replay, before submit | `Pick a past run and a tier to force, then compare.` |
| Replay, in flight | `Replaying against {tier}…` |
| Replay, error | `Replay failed: {message}` |
| Stats, loading | `Adding it up…` |
| Stats, empty | `No completed runs yet — stats need at least one.` |

Every error state includes a Retry action; no state is a bare spinner or a
blank white page with no explanation.

## Quality floor

- **Focus:** every interactive element gets a visible `2px solid var(--signal)` outline with `2px` offset on `:focus-visible` — never `outline: none` without a replacement.
- **Contrast:** body text (`--signal` / `--fog` on `--ink` / `--panel`) checked to meet WCAG AA (4.5:1) for normal text, 3:1 for large text and the tier dots against their backgrounds.
- **Reduced motion:** all transitions and the waterfall's bar-draw animation are wrapped in `@media (prefers-reduced-motion: no-preference)` — with the media query's inverse, motion is off by default for anyone who has asked for that.
- **Responsive:** usable down to 375px width — verified layout collapse described above, no horizontal scroll on the page itself (tables may scroll within their own container only where unavoidable).

## What was deliberately not done

- No card-grid-with-shadows treatment — this is a table/list-and-detail tool, not a marketing dashboard.
- No numbered-step markers — nothing here is a sequence.
- No tracked-out ALL-CAPS eyebrows or middle-dot-joined meta strings.
- No gradient washes or decorative color outside the tier system.
