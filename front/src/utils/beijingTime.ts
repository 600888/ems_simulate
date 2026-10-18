export const BEIJING_TIME_ZONE = "Asia/Shanghai";

const formatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: BEIJING_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

/** Legacy wall-clock strings without an offset are already Beijing time. */
export function beijingTimestampMillis(value: unknown): number {
  if (value instanceof Date) return value.getTime();
  if (typeof value === "number") return value;
  if (typeof value !== "string" || !value.trim()) return NaN;
  let timestamp = value.trim();
  if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(timestamp))
    timestamp = `${timestamp.replace(" ", "T")}+08:00`;
  return Date.parse(timestamp);
}

export function formatBeijingDateTime(
  value: unknown,
  milliseconds = true,
): string {
  const time = beijingTimestampMillis(value);
  if (!Number.isFinite(time) || Number.isNaN(new Date(time).getTime()))
    return "—";
  const parts = Object.fromEntries(
    formatter.formatToParts(time).map((part) => [part.type, part.value]),
  );
  const label = `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`;
  return milliseconds
    ? `${label}.${String(new Date(time).getUTCMilliseconds()).padStart(3, "0")}`
    : label;
}

export function formatBeijingTime(
  value: unknown,
  milliseconds = false,
): string {
  const label = formatBeijingDateTime(value, milliseconds);
  return label === "—" ? label : label.slice(11);
}
