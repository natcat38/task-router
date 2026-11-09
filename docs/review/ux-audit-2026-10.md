<!-- Moved into the repo on 2026-11-09 from the portfolio-wide UX polish folder (ux-polish-2026-10-23/reports/task-router.md), which has been deleted. -->
# UX audit record, 2026-10-23 to 2026-11-09

This is the point-in-time record of the October 2026 UX polish pass on `ui/`, kept here so the findings, fixes and owner decisions live with the code. The audit and its Fix log are copied unchanged below. Paths such as `shots/...` and `UXP/...` point at the original audit folder, which no longer exists; the key before/after screenshots are next to this file (`ux-audit-2026-*.png`). The binding decisions are in [ADR 0004](../adr/0004-ui-sticky-nav-two-column-run-page-self-hosted-plex.md).

Key screenshots:

- Run page at 1440, before and after the two-column layout: [before](ux-audit-2026-10-run-before-1440.png), [after](ux-audit-2026-10-run-after-1440.png)
- Run page at 1024 with a span open, before the 2026-11-09 fix (page 2,036 px wide): [overflow](ux-audit-2026-11-run-overflow-before-1024.png); plain `lg` with the old 24rem panel (38 px bars, rejected): [plain lg](ux-audit-2026-11-run-plain-lg-rejected-1024.png); after (18rem panel, 134 px bars): [after](ux-audit-2026-11-run-lg-after-1024.png)
- Stats with a negative saving, after: [stats](ux-audit-2026-11-stats-after-1440.png)

---

# UX audit: task-router (`ui/`)

Code read at origin/main `a1df50e` in a detached worktree (`C:/Users/natal/Documents/Coding/.worktrees/task-router-ux-audit`, removed at the end). Date 2026-10-23. No open issues. ROADMAP.md: stage DONE, nothing unchecked, so no roadmap update (read-only audit). The main checkout was not touched.

## How it was run

Real FastAPI backend (`uv run uvicorn api:app`, own venv in the session scratchpad) plus the Vite dev server on :5173. Data: a copy of the committed `data/fixtures/demo.sqlite` (5 runs) for the first screenshots, then a scratch copy extended to 51 runs (46 added through SQL: 3 tiers, 2 error runs, a 3,200-character prompt, a 62-character `use_case`, a run with null `use_case`, a run with zero spans). `POST /replay` needs a live model provider, so it was **mocked with Playwright route interception** (2.5 s delay, then a fixed diff); everything else is the real API. Walked at 1440x900, 390x844 and 320x640: runs list (all filters, empty, error, page 2), run detail (normal, long prompt, error run, no spans), span drawer, replay (loading and result), stats, 404 route, mobile menu, keyboard. Probe scripts: session scratchpad `scratchpad/tr/`. Screenshots: `UXP/shots/tr-*.png`.

## Verdict

The visual system is coherent and the states are better than most small tools (shared loading/empty/error components, a Retry button, URL-driven filters, text contrast that passes). It feels clunky for three reasons: the nav is not pinned (on a phone the run list is 3.8 screens and the Menu button scrolls out of reach), the list never shows what a request was (only a truncated UUID), and the waterfall, the screen the product exists for, has a time axis that does not line up with its bars and a span detail panel that opens below the fold with no sign anything happened.
Biggest single win: fix the waterfall (TR-UX-1 axis, TR-UX-5 drawer) and show the prompt next to every run (TR-UX-3). The layout of the run page is Decision D1.

## Measurements

| Page / state | Desktop screens | Phone screens | Pinned bar after scroll |
| --- | --- | --- | --- |
| Runs list, 20 rows | 1.1 (1033 px) | 3.8 (3170 px, 20 cards of about 150 px) | none: phone header top -2326 px at bottom; desktop rail top -133 px |
| Run detail (6 spans) | 1.0 | 1.0 (the opened span panel adds 0.4 below) | none |
| Replay result open | 1.1 | 1.4 | none |
| Stats | 1.0 | 1.0 | none |

Other numbers: no horizontal scroll at 390 or 320. Computed contrast: `--fog` #8a97a0 on `--ink` 6.19, on `--panel` 5.69; `--signal` on `--ink` 15.71; tier colours on panel 7.79 (local), 7.90 (sonnet), 4.71 (opus text); **`--line` border #2a343b against `--ink` 1.46** (inputs, selects, buttons). Control sizes at 390 px: selects and the text input 34 px tall, 14 px font; Prev/Next 57x34; span rows 28 px; drawer Close 51x27. API: `GET /runs` takes 0.3 s warm, 1.4 s first hit (list shows "Reading runs…", OK); each GET is preceded by an `OPTIONS` preflight (api.log). Motion respects `prefers-reduced-motion` and uses 150 ms.

## Findings

Sev: P0 blocks or confuses the main task; P1 clunky and noticeable; P2 polish.

| ID | Sev | Rule | What the user experiences | Evidence | Fix | Skill | Effort |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TR-UX-1 | P0 | S-LAY-5 (accuracy of the main view) | The waterfall's time axis does not match its bars. Labels run across the full width including the duration column, but the bars end 76 px earlier (desktop: axis right edge 1387, bar right edge 1311; phone 353 vs 277), and start 12 px later. A bar that really ends at 3825 ms lines up with about 3500 ms on the axis. In a tool for reading latency this is misleading. The last label ("5100ms") also hangs over the panel edge. | `RunWaterfallPage.tsx:134` (axis `ml-28 sm:ml-48`, no right inset) vs `:172-197` (row has `px-1`, `gap-2`, a `w-16` duration column); `shots/tr-run-desktop.png`, `tr-run-phone-full.png` | Give the axis the same three-column layout as `SpanRow`: spacer (`w-28 sm:w-48` + `gap-2` + `px-1`), a flex-1 axis, spacer (`w-16` + `gap-2` + `px-1`). Right-align the last tick label (`-translate-x-full`). Add a test that tick 100% and the longest bar end share an x. | impeccable `critique`, tdd | S |
| TR-UX-2 | P1 | S-NAV-1 | The nav is not pinned. On a phone the "router / Menu" header scrolls away: after scrolling the 3.8-screen list, Menu is 2.3 screens up. On desktop the left rail scrolls with the page, so Runs, Stats and the tier legend leave the screen on any long page. | `AppShell.tsx:59` (`<header>` not sticky), `:81` (`<aside>` not sticky); measured header top -2326 px (phone), aside top -133 px (desktop) | Header: `sticky top-0 z-20 bg-ink` (56 px, 6.6% of 844). Rail: `md:sticky md:top-0 md:h-dvh`. Add `scroll-mt-16` to anything linked by anchor. Bottom tab bar instead of a header menu is **D2**. | baseline-ui | S |
| TR-UX-3 | P1 | S-LAY-1 | You cannot tell which request a run is. The list shows a 10-character UUID prefix, a time, a use case and the model; the demo ids share one prefix ("demo000000…" on every row). The run page never shows the prompt or the answer at all (checked on four runs). `GET /runs` already returns `input_text` and `output_text`. A replay debugger that hides the request makes you open every run to find the one you want. | `RunsListPage.tsx:12-14, 226-230, 245-270`; `RunWaterfallPage.tsx:304-334` (no request or response block); `curl /runs` returns `input_text`; `shots/tr-runs-desktop.png`, `tr-list-phone-1.png` | List: add a "Request" column (first 80 characters, `line-clamp-1`, full text in `title`), make the whole row a link. Detail: a collapsible "Request and response" section (two `<pre>` blocks, `max-h-64 overflow-auto`) between the header and the replay panel. Placement is part of **D1**; a collapsed `<details>` under the header is the safe default. | impeccable `clarify`, break-ui | M |
| TR-UX-4 | P1 | S-LAY-1, S-LAY-2 | Phone run list: each run is a 150 px card with four label-value rows, so one screen shows 5 runs and the list is 3.8 screens long. Filters take another 130 px and are not pinned. | `RunsListPage.tsx:245-270` (`RunCard`); measured 3170 px; `shots/tr-list-phone-1.png` | Two-line row: line 1 request snippet, line 2 tier chip, escalated badge, status, relative time (about 64 px; 20 rows is about 1.5 screens). Collapse the three filters into a "Filters (n)" disclosure under `sm`. | impeccable `distill`/`adapt` | M |
| TR-UX-5 | P1 | S-NAV-4, S-A11Y-3 | Click a span and nothing visibly happens: the attribute panel renders under the whole page (desktop top at 676 and bottom at 1014 on a 900 px screen; phone top at 831 on 844), the page does not scroll and focus stays on the row. Escape does not close it. On a phone the user has to find it by scrolling. | `RunWaterfallPage.tsx:335-337` (drawer after the waterfall), `:210-219`; measured `scrollY` 0 after click, drawer still open after Escape; `shots/tr-run-drawer-desktop.png` | Interim (unblocked): render the panel directly under the selected row (inside the list), `scrollIntoView({block:'nearest'})`, move focus to its heading, close on Escape. Side-panel variant (waterfall left, inspector right on `lg`) is **D1**. | emil `break-ui`, impeccable `operate` | S |
| TR-UX-6 | P1 | S-FB-2 | Filtering to zero results shows "No runs yet. Send a request to POST /v1/completions and it'll show up here." That is wrong (runs exist) and gives no way back except clearing three controls by hand. | `RunsListPage.tsx:137-139`; `shots/tr-list-desktop-4-empty.png` | If any filter is active: "No runs match these filters." plus a "Clear filters" button (`setSearchParams({})`); keep the current copy for a truly empty DB. | impeccable `harden` | S |
| TR-UX-7 | P1 | S-NAV-3, S-FB-1 | Typing in "Use case" sends one request per keystroke and writes one browser-history entry per keystroke ("summ" gave 4 requests and 4 history entries), so Back walks through the letters, and a slow earlier response can land after a newer one. | `RunsListPage.tsx:57-67` (`setSearchParams(next)` without `{replace:true}`), `:110`, `:38-51` (no abort); measured history +4, requests 4 | Keep the text in local state, apply it after 300 ms, use `setSearchParams(next, { replace: true })` for typing, and guard `load()` with an `AbortController` or a request counter. | vercel-react-best-practices | S |
| TR-UX-8 | P1 | S-A11Y-2 | Borders of the inputs, selects and the Replay/Prev/Next/Close buttons are `--line` and measure 1.46:1 against the page (1.3:1 on a panel). On a dim screen the controls read as floating text; the Replay button, the one action on the run page, is easy to miss. Text contrast passes. | `index.css:12`; `RunsListPage.tsx:94, 112, 121, 192`; `ReplayPanel.tsx:436, 449`; `shots/tr-run-desktop.png` | Add a `--control-line` token for interactive borders that reaches the UI-part target of 3:1 against its background (the implementer measures the value), keep `--line` for dividers. Give Replay the single filled/primary style. | web-design-guidelines | S |
| TR-UX-9 | P1 | S-LAY-3, S-A11Y-1 | The replay diff, the product's differentiator, is hard to read. Output is cut to 80 characters on both sides with no way to see the rest, so you cannot read the answers you are comparing. On a phone each side of the Output row is about 8 characters wide (4-column grid with `break-all`). | `ReplayPanel.tsx:353-356, 376, 489-490`; `shots/tr-replay-result-phone.png` | Under `md`, stack Before and After as two labelled blocks. Keep the summary row truncated and add "Show full output" (`<details>`) with both texts in `whitespace-pre-wrap max-h-72 overflow-auto`; highlight changed fields with text plus an arrow, not colour alone. | impeccable `layout`, break-ui | M |
| TR-UX-10 | P2 | S-FB-1 | Replay runs the judge on the server, so it can take seconds. The only feedback is one static grey line ("Replaying against sonnet…", no spinner, not announced). On a phone the finished diff is partly below the fold (link top 853 of 844) and focus never moves to it. | `ReplayPanel.tsx:455-457, 401-417`; measured `scrollY` 0 and focus BODY after the result | `role="status"` with the existing pulse dot; on success `scrollIntoView` and focus the result heading. | impeccable `harden` | S |
| TR-UX-11 | P2 | S-NAV-3 | Every route has the title "task-router", so tabs and history all look the same. An unknown URL renders an empty page (main is blank: no 404 route). | `index.html:13`; `App.tsx:11-16` (no `*` route); measured `title` identical on four routes and empty `main` on `/nope` | A `useDocumentTitle` hook ("Runs", "Run d37ee915", "Stats" + " | task-router"); a `<Route path="*">` with `EmptyState` and a link to Runs. | baseline-ui | S |
| TR-UX-12 | P2 | S-A11Y-3, S-NAV-1 | The phone Menu is a two-link hamburger that pushes the page down; it does not close on Escape or outside tap. With two destinations a bottom tab bar would be faster. | `AppShell.tsx:61-78`; measured menu still open after Escape; `shots/tr-menu-phone.png` | Close on Escape and route change. Bottom tab bar variant is **D2**. | emil mobile-native | S |
| TR-UX-13 | P2 | S-A11Y-1, S-A11Y-6 | On a phone, inputs are 14 px (iOS zooms the page on focus) and controls are 34 px (selects, Prev/Next), span rows 28 px, drawer Close 51x27 px. | `index.css:54`; `RunsListPage.tsx:94-121` (`text-sm`); `:192, 203`; `RunWaterfallPage.tsx:172, 215` | `text-base md:text-sm` on inputs and selects; `min-h-11` on buttons and span rows under `md`. | baseline-ui | S |
| TR-UX-14 | P2 | S-LAY-5, S-ID-1 | The same run shows different times in different places: the list prints local time ("19/09/2026, 04:45:00"), the detail page prints raw UTC ISO ("2026-09-18T20:45:00+00:00"), eight hours apart for the same run. | `RunsListPage.tsx:16-19`; `RunWaterfallPage.tsx:123` | One shared `formatTimestamp` (local, with the UTC value in `title`); use it on both pages. | baseline-ui | S |
| TR-UX-15 | P2 | S-A11Y-2, S-FB-2 | An error run is plain text "error" next to "ok", indistinguishable at a glance; with 2 of 51 error runs they hide in the list. | `RunsListPage.tsx:240`; `RunWaterfallPage.tsx:103` | A status chip: `ok` neutral, `error` with an icon plus text in the opus-rose, never colour alone. | impeccable `harden` | S |
| TR-UX-16 | P2 | S-FB-2 | Stats: bar length is relative to the biggest tier while the label shows the share (a bar at half length is labelled 20%); the negative saving "-4.3%" has no sign or note that routing cost more than it saved. | `StatsPage.tsx:361, 343-346` | Bar width = share of requests; add "(more than always using the top tier)" text next to a negative value. Copy needs Natalie's approval (it is a claim about the result). | impeccable `clarify` | S |
| TR-UX-17 | P2 | S-PERF-1 | Every GET carries `Content-Type: application/json`, which forces a CORS preflight before each call; the log shows an OPTIONS before every GET. That doubles round trips on every list, page and filter change. | `api/client.ts:39-40`; `api.log` | Only set the header when `init.body` exists. | vercel-react-best-practices | S |
| TR-UX-18 | P2 | S-ID-1 | Fonts come from Google Fonts (`index.html:7-12`). The tool is local-only and the README advertises a "demo with no model running"; offline, it silently falls back to system fonts with a visible re-flow. | `index.html:7-12` | Self-host IBM Plex (dependency: `@fontsource/ibm-plex-*`) or accept a system stack. **D3**. | hallmark (options only) | S |

## Decisions for Natalie

**D1. Run-detail layout (blocks the side-panel part of TR-UX-5 and the placement of the request block in TR-UX-3).** Today three stacked panels: header, Replay form, Waterfall, then the span panel at the bottom. Protects: the waterfall is the product, and replay is the differentiator (README). Changes how the screen feels.
- A. Keep stacked; move Waterfall above Replay; replay becomes a collapsed section that opens after a click.
- B. Two columns from `lg`: waterfall on the left; a sticky right panel switches between Span details, Request and response, and Replay.
- C. Tabs under the header (Trace, Replay, Request); one thing on screen at a time, phone-friendly, hides the waterfall while replaying.

**D2. Phone navigation (blocks the bottom-bar variant of TR-UX-2 and TR-UX-12).** Two destinations only (Runs, Stats).
- A. Sticky top header with the existing Menu button (smallest change).
- B. Sticky top header showing both links inline, no menu at all (two links fit at 390 px).
- C. Bottom tab bar with safe-area padding (thumb-reachable; the top bar keeps only the wordmark).

**D3. Fonts (TR-UX-18).** Adds a dependency or drops a design choice.
- A. Keep the Google Fonts link (needs internet; no new dependency).
- B. `@fontsource/ibm-plex-sans` and `-mono` (works offline; two packages).
- C. System sans and mono stacks (no dependency; loses the IBM Plex look from `Design_Direction.md`).

## Branding status

| Item | Status |
| --- | --- |
| Name in header | Present, but inconsistent: wordmark "router" (`AppShell.tsx:60, 83`) vs title "task-router" |
| Logo | Missing (text wordmark only); acceptable for a local tool |
| Favicon | Present (`public/favicon.svg`) |
| `<title>` | Partial: static "task-router" on every route (TR-UX-11) |
| Description, OG image | Missing; not needed for a local-only tool |
| Palette and type | Present: dark tokens in `index.css`, IBM Plex, tier-colour trio, documented in `docs/Design_Direction.md` |

## Fix batches (non-blocked findings)

1. **Waterfall correctness and run page (one PR):** TR-UX-1, 5 (interim version), 10, 14, 15. Goal: the trace view is accurate, and clicking or replaying visibly does something.
2. **List and navigation (one PR):** TR-UX-2 (sticky header and rail), 3 (list column and collapsed request block), 4, 6, 7, 11, 17. Goal: find the right run fast, and keep the nav in reach.
3. **Controls and replay diff (one PR):** TR-UX-8, 9, 13, 16 (once copy is approved). Goal: controls are visible and touch-sized, and the diff is readable on a phone.

Waiting on decisions: layout parts of TR-UX-3 and 5 (D1), bottom bar in TR-UX-2 and 12 (D2), TR-UX-18 (D3).

## Cleanup note

Servers on :8000 and :5173 and the worktree were removed at the end of the audit; the scratch databases and venv are in the session scratchpad only. `POST /replay` was mocked, not run against a model.

## Fix log

Decisions applied: G2 A / D1 B (two columns, sticky inspector), G1 A / D2 A (sticky top bar with the existing Menu), R12 option 2 (`@fontsource` IBM Plex). All three PRs squash-merged to `main`, CI green (`verify`, `ui`, `validate`), `mergedAt` verified with `gh pr view`.

| PR | Branch | IDs fixed | mergedAt |
| --- | --- | --- | --- |
| https://github.com/natcat38/task-router/pull/24 | fix/ux-run-page | TR-UX-1, 5, 10, 14, 15 (plus the Request tab of TR-UX-3, which the three-view inspector needs) | 2026-10-28T04:26:22Z |
| https://github.com/natcat38/task-router/pull/25 | fix/ux-list-nav | TR-UX-2, 3 (list column and whole-row link), 4, 6, 7, 11, 12, 17 | 2026-10-28T04:35:19Z |
| https://github.com/natcat38/task-router/pull/26 | fix/ux-controls-fonts | TR-UX-8, 9, 13, 18; TR-UX-16 bar-width half only | 2026-10-28T04:43:26Z |

Numbers (browser-measured, demo fixture plus extra scratch rows):
- Waterfall axis right edge vs bar track right edge: 76 px off before, 0 px after (desktop and phone).
- Run page, span open: desktop panel was below the fold (bottom 1014 px on 900), now beside the waterfall at 1.0 screens; phone 1.4 to 1.17 screens.
- Phone runs list, 20 rows: 3.8 screens (3170 px) to 1.82 (1532 px). Pinned bar after scroll: phone 0 px (was -2326), desktop rail 0 px (was -133).
- Typing "summ" in Use case: 4 requests and 4 history entries to 1 and 0. OPTIONS preflights per GET: 1 to 0.
- Control border contrast: 1.46:1 to 3.46:1 against ink. Phone control heights 34 px to 44 px; inputs 14 px to 16 px.
- External font hosts: 2 to 0; all six Plex faces load with the network blocked.

Deviations to know:
- The two-column run page starts at `xl` (1280 px), not `lg` (1024 px). With the 224 px nav rail the bar track was 70 px wide at 1024 px. Below `xl` the inspector stacks under the waterfall.
- The replay diff stacks by container width (`@md`), not viewport width, because the diff now sits in a narrow side panel on desktop too.

Skipped, needs Natalie: TR-UX-16 second half. Copy question: should the Stats page put a note beside a negative saving such as -4.3%? The audit proposed "(more than always using the top tier)". It is a claim about the result, so it was not written.

Not touched: ROADMAP.md (stage DONE, nothing unchecked; this was a UX pass, not a roadmap item). The main checkout at `C:/Users/natal/Documents/Coding/task-router` is still on `a1df50e`; `git pull` there to get the changes.

---

## Owner decisions, 2026-11-09 (walkthrough of the open items)

Measured locally against `data/fixtures/demo.sqlite` (run `demo…0005`, one span opened).

| Item | Evidence | Decision |
|---|---|---|
| Two-column breakpoint | Bar track width with the 24rem inspector: plain `lg` 38 px at 1024, 166 px at 1152; `xl` 294 px at 1280 | Option 2: two columns from `lg` with the inspector narrowed to 18rem. Measured after: 134 px at 1024, 262 at 1152, 390 at 1280, 550 at 1440. Between `lg` and `xl` the time axis shows only 0 / half / end, since five labels overlap at 134 px. |
| TR-UX-16 negative saving | Stats read "Saved, including judge cost: -4.3%", a double negative | Option 2: when the figure is below zero the tile reads "Cost more, including judge cost: +4.3%" with "Routing plus judging cost 4.3% more than always using the top tier." |
| Bug found while measuring (not a decision) | Below `xl`, opening a span made the page 1,796 px (390 wide) to 2,036 px (1024 to 1279 wide): the raw-attributes JSON line sized the implicit grid column | Fixed: `grid-cols-[minmax(0,1fr)]` on the run page grid. Page width now equals the window at 320, 390, 1023, 1024, 1152, 1280 and 1440. |
| `RunInspector.tsx` comment | Said sticky "from `lg`" while the class was `xl:sticky` | Now true: the class is `lg:sticky` and the comment says so. |

## From the 2026-11-02 open-items sweep

The portfolio sweep (`open-items-sweep-2026-11-02/TRIAGE.md`, deleted after this move) found no open issues or PRs in task-router. Its only task-router note was the `RunInspector.tsx` comment mismatch above, now fixed.
