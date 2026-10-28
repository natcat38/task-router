/** Local, human-readable form of an ISO timestamp. Falls back to the raw
 * string when it doesn't parse, so a bad value is shown rather than hidden. */
export function formatTimestamp(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleString();
}

/** The same instant in UTC, for a tooltip. Null when the value doesn't parse. */
export function formatTimestampUtc(iso: string): string | null {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? null : `${parsed.toISOString()} (UTC)`;
}

/** First `max` characters of a request, whitespace collapsed to single spaces. */
export function requestSnippet(text: string, max = 80): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat === "") return "(no request text)";
  return flat.length > max ? `${flat.slice(0, max)}…` : flat;
}

/** "just now", "5m ago", "3h ago", "2d ago"; older than 30 days falls back to the local date. */
export function formatRelative(iso: string, now: number = Date.now()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const seconds = Math.round((now - then) / 1000);
  if (seconds < 45) return "just now";
  if (seconds < 0) return new Date(iso).toLocaleDateString();
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days <= 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}
