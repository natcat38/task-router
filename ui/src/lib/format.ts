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
