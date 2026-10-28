import { useRef } from "react";
import type { KeyboardEvent, ReactNode, Ref } from "react";
import type { Run } from "../api/types";

export type InspectorTab = "span" | "request" | "replay";

const TABS: { id: InspectorTab; label: string }[] = [
  { id: "span", label: "Span" },
  { id: "request", label: "Request" },
  { id: "replay", label: "Replay" },
];

export const inspectorTabId = (tab: InspectorTab) => `inspector-tab-${tab}`;
export const inspectorPanelId = (tab: InspectorTab) => `inspector-panel-${tab}`;

/**
 * The run page's side panel (one column below `xl`, sticky beside the
 * waterfall from `lg`): a tab strip that switches between span details, the
 * request and response, and the replay form. Every panel stays mounted and is
 * only hidden, so a replay that is running or finished is not lost when the
 * viewer looks at a span.
 */
export function RunInspector({
  active,
  onChange,
  panelRef,
  span,
  request,
  replay,
}: {
  active: InspectorTab;
  onChange: (tab: InspectorTab) => void;
  panelRef?: Ref<HTMLElement>;
  span: ReactNode;
  request: ReactNode;
  replay: ReactNode;
}) {
  const tabRefs = useRef<Record<InspectorTab, HTMLButtonElement | null>>({
    span: null,
    request: null,
    replay: null,
  });

  // Arrow keys move between tabs (roving tabindex), as the tabs pattern expects.
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const index = TABS.findIndex((t) => t.id === active);
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % TABS.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + TABS.length) % TABS.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = TABS.length - 1;
    else return;
    event.preventDefault();
    onChange(TABS[next].id);
    tabRefs.current[TABS[next].id]?.focus();
  }

  const panels: Record<InspectorTab, ReactNode> = { span, request, replay };

  return (
    <section
      ref={panelRef}
      aria-label="Run inspector"
      className="scroll-mt-16 rounded border border-line bg-panel xl:sticky xl:top-8 xl:max-h-[calc(100dvh-4rem)] xl:overflow-y-auto"
    >
      <div
        role="tablist"
        aria-label="Inspector views"
        onKeyDown={onKeyDown}
        className="flex border-b border-line px-2"
      >
        {TABS.map((tab) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                tabRefs.current[tab.id] = el;
              }}
              type="button"
              role="tab"
              id={inspectorTabId(tab.id)}
              aria-selected={selected}
              aria-controls={inspectorPanelId(tab.id)}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(tab.id)}
              className={`-mb-px border-b-2 px-3 py-2.5 text-sm transition-standard ${
                selected
                  ? "border-signal text-signal"
                  : "border-transparent text-fog hover:text-signal"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {TABS.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={inspectorPanelId(tab.id)}
          aria-labelledby={inspectorTabId(tab.id)}
          hidden={tab.id !== active}
          className="px-5 py-4"
        >
          {panels[tab.id]}
        </div>
      ))}
    </section>
  );
}

function TextBlock({ title, text, empty }: { title: string; text: string | null; empty: string }) {
  return (
    <div>
      <h3 className="mb-1 text-xs text-fog">{title}</h3>
      {text === null || text === "" ? (
        <p className="text-fog">{empty}</p>
      ) : (
        <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-ink px-3 py-2 font-mono text-[13px] text-signal">
          {text}
        </pre>
      )}
    </div>
  );
}

/** What was asked and what came back, for the run being viewed. */
export function RequestResponse({ run }: { run: Run }) {
  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-base font-semibold text-signal">Request and response</h2>
      <TextBlock title="Request" text={run.input_text} empty="No request text recorded." />
      <TextBlock
        title="Response"
        text={run.output_text}
        empty={run.status === "error" ? "This run failed before an answer came back." : "No response recorded."}
      />
    </div>
  );
}
