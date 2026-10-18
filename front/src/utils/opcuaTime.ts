import {
  BEIJING_TIME_ZONE,
  formatBeijingDateTime as formatDateTime,
} from "./beijingTime";

export const OPCUA_TIME_ZONE = BEIJING_TIME_ZONE;

/** OPC UA timestamps without an explicit offset are UTC. */
export function opcUaTimestampMillis(value: unknown): number {
  if (value instanceof Date) return value.getTime();
  if (typeof value === "number") return value;
  if (typeof value !== "string" || !value.trim()) return NaN;
  let timestamp = value.trim();
  if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?$/.test(timestamp))
    timestamp = `${timestamp.replace(" ", "T")}Z`;
  return Date.parse(timestamp);
}

export function formatBeijingDateTime(
  value: unknown,
  milliseconds = true,
): string {
  return formatDateTime(opcUaTimestampMillis(value), milliseconds);
}

export function formatBeijingTime(value: unknown): string {
  const label = formatBeijingDateTime(value, false);
  return label === "—" ? label : label.slice(11);
}

/** Date pickers hold Beijing wall-clock strings, independently of the host zone. */
export function beijingDateTimeToISOString(value: string): string {
  return new Date(`${value.replace(" ", "T")}+08:00`).toISOString();
}

export function defaultBeijingTimeRange(now = Date.now()): [string, string] {
  return [
    formatBeijingDateTime(now - 3600000, false),
    formatBeijingDateTime(now, false),
  ];
}
