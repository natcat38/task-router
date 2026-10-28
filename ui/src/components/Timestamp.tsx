import { formatRelative, formatTimestamp, formatTimestampUtc } from "../lib/format";

/**
 * A run timestamp, shown in the viewer's local time everywhere (list and
 * detail page alike) with the UTC value on hover. One component so the two
 * pages can never disagree about the same run again.
 */
export function Timestamp({ iso, className }: { iso: string; className?: string }) {
  const utc = formatTimestampUtc(iso);
  if (utc === null) return <span className={className}>{iso}</span>;
  return (
    <time dateTime={iso} title={utc} className={className}>
      {formatTimestamp(iso)}
    </time>
  );
}

/** The compact form for dense rows ("5m ago"); the full local time and the UTC value stay in the tooltip. */
export function RelativeTimestamp({ iso, className }: { iso: string; className?: string }) {
  const utc = formatTimestampUtc(iso);
  if (utc === null) return <span className={className}>{iso}</span>;
  return (
    <time dateTime={iso} title={`${formatTimestamp(iso)} - ${utc}`} className={className}>
      {formatRelative(iso)}
    </time>
  );
}
