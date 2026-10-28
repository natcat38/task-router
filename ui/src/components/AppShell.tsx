import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { TIER_ORDER } from "../api/tiers";
import { TierChip } from "./TierChip";

const NAV_ITEMS = [
  { to: "/", label: "Runs", end: true },
  { to: "/stats", label: "Stats", end: false },
];

function navLinkClass({ isActive }: { isActive: boolean }): string {
  const base = "block rounded px-3 py-2 text-sm transition-standard";
  return isActive
    ? `${base} bg-panel text-signal`
    : `${base} text-fog hover:text-signal`;
}

/** The tier legend -- a constant reminder of what the three dots mean
 * (Design_Direction.md "The signature element"), shown at the bottom of
 * the nav rail on every page. */
function TierLegend() {
  return (
    <div className="flex flex-col gap-1.5 border-t border-line pt-3">
      <span className="px-3 text-xs text-fog">tiers</span>
      {TIER_ORDER.map((tier) => (
        <div key={tier} className="px-3">
          <TierChip tier={tier} />
        </div>
      ))}
    </div>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Primary" className="flex flex-col gap-1">
      {NAV_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={navLinkClass}
          onClick={onNavigate}
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const mobileBarRef = useRef<HTMLDivElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const location = useLocation();

  // Any route change closes the menu (back/forward included, not only taps on its own links).
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname, location.search]);

  // While the menu is open: Escape closes it (focus returns to the button),
  // and so does a tap anywhere outside the bar.
  useEffect(() => {
    if (!mobileNavOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setMobileNavOpen(false);
      menuButtonRef.current?.focus();
    }
    function onPointerDown(event: PointerEvent) {
      if (event.target instanceof Node && !mobileBarRef.current?.contains(event.target)) {
        setMobileNavOpen(false);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [mobileNavOpen]);

  return (
    <div className="min-h-full bg-ink text-signal md:flex">
      {/* Mobile top bar (below md). Pinned, so the Menu stays in reach on a long list;
          the open menu is inside the same pinned block so it scrolls with it. */}
      <div ref={mobileBarRef} className="sticky top-0 z-20 bg-ink md:hidden">
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <span className="font-mono text-sm font-semibold">router</span>
          <button
            ref={menuButtonRef}
            type="button"
            aria-expanded={mobileNavOpen}
            aria-controls="mobile-nav"
            onClick={() => setMobileNavOpen((open) => !open)}
            className="min-h-11 rounded border border-control-line px-3 py-1.5 text-sm transition-standard hover:border-signal md:min-h-0"
          >
            {mobileNavOpen ? "Close" : "Menu"}
          </button>
        </header>
        {mobileNavOpen && (
          <div
            id="mobile-nav"
            className="max-h-[calc(100dvh-4rem)] overflow-y-auto border-b border-line px-4 py-4"
          >
            <NavLinks onNavigate={() => setMobileNavOpen(false)} />
            <div className="mt-4">
              <TierLegend />
            </div>
          </div>
        )}
      </div>

      {/* Desktop nav rail (md and up). Pinned for the full viewport height so Runs,
          Stats and the tier legend stay on screen however long the page is. */}
      <aside className="hidden w-56 shrink-0 flex-col justify-between self-start border-r border-line px-3 py-4 md:sticky md:top-0 md:flex md:h-dvh">
        <div>
          <div className="mb-4 px-3 font-mono text-sm font-semibold">router</div>
          <NavLinks />
        </div>
        <TierLegend />
      </aside>

      <main className="min-w-0 flex-1 px-4 py-6 md:px-8 md:py-8">{children}</main>
    </div>
  );
}
