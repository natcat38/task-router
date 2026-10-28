import type { ReactNode } from "react";

/**
 * Shared loading / empty / error presentational states. Copy is supplied
 * by the caller (each page owns its own domain-specific message per
 * docs/Design_Direction.md "Loading / empty / error states") -- these
 * components only own the layout, so every page looks consistent without
 * repeating markup.
 */

export function LoadingState({ message }: { message: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-10 text-fog">
      <span
        aria-hidden="true"
        className="h-3 w-3 animate-pulse rounded-full bg-fog motion-reduce:animate-none"
      />
      <span>{message}</span>
    </div>
  );
}

export function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="rounded border border-dashed border-line px-4 py-10 text-center text-fog">
      <p>{message}</p>
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-start gap-3 rounded border border-tier-opus/40 bg-tier-opus/10 px-4 py-4 text-signal">
      <span>{message}</span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="min-h-11 rounded border border-control-line px-3 py-1.5 font-mono text-[13px] transition-standard hover:border-signal md:min-h-0"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function Placeholder({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded border border-line bg-panel px-5 py-6">
      <h2 className="mb-1 text-base font-semibold text-signal">{title}</h2>
      <p className="text-fog">Coming in the next chunk.</p>
      {children}
    </div>
  );
}
