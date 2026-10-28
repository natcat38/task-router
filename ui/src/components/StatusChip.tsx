import type { RunStatus } from "../api/types";

/**
 * Run status. `ok` stays quiet plain text; `error` gets a bordered chip with
 * an icon and the word, in the opus-rose, so it never relies on colour alone.
 */
export function StatusChip({ status }: { status: RunStatus }) {
  if (status !== "error") {
    return <span className="font-mono text-[13px] text-fog">{status}</span>;
  }
  return (
    <span className="inline-flex items-center gap-1 rounded border border-tier-opus/60 px-1.5 py-0.5 font-mono text-[13px] text-tier-opus">
      <svg
        aria-hidden="true"
        viewBox="0 0 16 16"
        className="h-3 w-3 shrink-0"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      >
        <circle cx="8" cy="8" r="6.25" />
        <path d="M5.5 5.5l5 5M10.5 5.5l-5 5" />
      </svg>
      error
    </span>
  );
}
