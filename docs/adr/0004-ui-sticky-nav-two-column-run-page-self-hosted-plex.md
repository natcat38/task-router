# 0004: UI layout — a sticky top bar on phones, a two-column run page from `xl`, and self-hosted IBM Plex

## Status
Accepted (2026-10-24). Owner decisions from the 2026-10 UX polish pass; shipped in #24, #25 and #26.

## Context
A UX audit on 2026-10-23 measured the UI in `ui/` against `docs/Design_Direction.md`:

- **Phone navigation.** The nav scrolled away with the page. On a 20-row runs list the Menu sat 2,326px above the viewport by the end of the list, so changing page meant scrolling back to the top.
- **Run page.** The waterfall and its span detail were one column, so on a 1440x900 screen the detail panel ended at y=1014, below the fold, and the reader scrolled away from the bar they had clicked.
- **Fonts.** IBM Plex Sans and Mono loaded from Google Fonts. The UI is a local tool, usually run beside a local router, and with no network it fell back to system fonts.

## Decision
- **Phone navigation (G1, option A).** Below `md` (768px) a compact top bar with the existing Menu button stays pinned while the page scrolls. From `md` the left nav rail is shown and is sticky. Links stay one tap behind Menu on a phone; no bottom tab bar.
- **Run page (G2, option A; task-router D1, option B).** From `xl` (1280px) the run page is two columns: the waterfall on the left and the inspector (span details, request and response, replay form) sticky on the right. Below `xl` the inspector stacks under the waterfall. The replay diff stacks by its own container width (`@md`), not the viewport, because it now sits in that narrow panel.
- **Fonts (R12, option 2).** IBM Plex Sans and IBM Plex Mono are self-hosted through `@fontsource/ibm-plex-sans` and `@fontsource/ibm-plex-mono`, imported in `ui/src/main.tsx`. No external font host.

## Consequences
- The two-column breakpoint is `xl`, not the `lg` the decision named. With the 224px nav rail beside it, the waterfall's bar track was only 70px wide at 1024px, too narrow to read.
- Run page with a span open: 1.0 screens on desktop (the panel was below the fold), 1.4 -> 1.17 on a phone. Phone runs list (20 rows): 3.8 -> 1.82 screens.
- External font hosts 2 -> 0; all six Plex faces load with the network blocked. The UI gains two font packages.
- Still open with the owner: whether the Stats page explains a negative saving with a note such as "(more than always using the top tier)" (TR-UX-16).
