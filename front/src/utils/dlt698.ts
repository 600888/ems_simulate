import type {
  Dlt698Config,
  Dlt698Data,
  Dlt698Point,
  Dlt698Result,
  Dlt698RecordQuery,
} from "@/types/dlt698";
import { DLT698_DATA_TYPES } from "@/types/dlt698";

export function defaultDlt698Config(): Dlt698Config {
  return {
    role: "client",
    server_address: "000000000000",
    logical_address: 0,
    client_address: 16,
    association: "public",
    request_timeout_ms: 5000,
    heartbeat_interval_s: 30,
    protocol_version: 1,
    send_frame_max: 2048,
    receive_frame_max: 2048,
    receive_window: 1,
    apdu_max: 2048,
    association_timeout_s: 120,
    wiring: "three_phase_four_wire",
    tariff_count: 4,
    harmonic_order: 21,
  };
}
export function normalizeOad(input: string): string {
  const value = input.replace(/\s/g, "").replace(/^0x/i, "").toUpperCase();
  if (!/^[0-9A-F]{8}$/.test(value))
    throw new Error("OAD / OMD: 8 hexadecimal digits required");
  return value;
}
export function makeOad(oi: string, attribute: number, index: number): string {
  if (
    !/^[0-9a-f]{4}$/i.test(oi) ||
    !Number.isInteger(attribute) ||
    attribute < 0 ||
    attribute > 255 ||
    !Number.isInteger(index) ||
    index < 0 ||
    index > 255
  )
    throw new Error("Invalid OI / attribute / element index");
  return normalizeOad(
    oi +
      attribute.toString(16).padStart(2, "0") +
      index.toString(16).padStart(2, "0"),
  );
}
const integerBits: Record<string, [number, boolean]> = {
  Int8: [8, true],
  UInt8: [8, false],
  Int16: [16, true],
  UInt16: [16, false],
  Int32: [32, true],
  UInt32: [32, false],
  Int64: [64, true],
  UInt64: [64, false],
  Enum: [8, false],
};
export function validateData(data: Dlt698Data): void {
  if (!data || !DLT698_DATA_TYPES.includes(data.type))
    throw new Error("Unknown Data type");
  const bounds = integerBits[data.type];
  if (bounds) {
    if (typeof data.value !== "string" || !/^-?\d+$/.test(data.value))
      throw new Error(`${data.type}: decimal integer string required`);
    const value = BigInt(data.value),
      [bits, signed] = bounds;
    const min = signed ? -(BigInt(1) << BigInt(bits - 1)) : BigInt(0);
    const max = (BigInt(1) << BigInt(bits - (signed ? 1 : 0))) - BigInt(1);
    if (value < min || value > max)
      throw new Error(`${data.type}: out of range`);
  } else if (data.type === "Array" || data.type === "Structure") {
    if (!Array.isArray(data.value))
      throw new Error(`${data.type}: typed children required`);
    data.value.forEach(validateData);
  } else if (data.type === "Null") {
    if (data.value !== null) throw new Error("Null: null required");
  } else if (data.type === "Boolean") {
    if (typeof data.value !== "boolean")
      throw new Error("Boolean: true / false required");
  } else {
    if (typeof data.value !== "string")
      throw new Error(`${data.type}: string required`);
    if (
      data.type === "OctetString" &&
      !/^(?:[0-9a-fA-F]{2})*$/.test(data.value)
    )
      throw new Error("OctetString: hexadecimal byte pairs required");
    if (data.type === "BitString" && !/^[01]*$/.test(data.value))
      throw new Error("BitString: binary digits required");
    if (/^Float/.test(data.type)) {
      const number = Number(data.value);
      if (
        !data.value.trim() ||
        !Number.isFinite(number) ||
        (data.type === "Float32" && !Number.isFinite(Math.fround(number)))
      )
        throw new Error(`${data.type}: finite number in range required`);
    }
    const date = "\\d{4}-\\d{2}-\\d{2}",
      time = "\\d{2}:\\d{2}:\\d{2}";
    if (["Date", "Time", "DateTime", "DateTimeS"].includes(data.type)) {
      const pattern =
        data.type === "Date"
          ? date
          : data.type === "Time"
            ? time
            : `${date}T${time}`;
      if (!new RegExp(`^${pattern}$`).test(data.value))
        throw new Error(`${data.type}: ISO local date/time required`);
      const parsed = new Date(
        data.type === "Time"
          ? `2000-01-01T${data.value}Z`
          : data.value + (data.type === "Date" ? "T00:00:00Z" : "Z"),
      );
      if (
        !Number.isFinite(parsed.getTime()) ||
        parsed.toISOString().slice(0, data.type === "Date" ? 10 : 19) !==
          (data.type === "Time" ? `2000-01-01T${data.value}` : data.value)
      )
        throw new Error(`${data.type}: invalid date/time`);
    }
  }
}
export function parseData(type: Dlt698Data["type"], text: string): Dlt698Data {
  const value =
    type === "Null"
      ? null
      : type === "Boolean"
        ? JSON.parse(text)
        : ["Array", "Structure"].includes(type)
          ? JSON.parse(text)
          : text;
  const data: Dlt698Data = { type, value };
  validateData(data);
  return data;
}
/** Exact decimal scaling; never pass protocol integers through Number. */
export function engineeringText(
  value: Dlt698Data | undefined,
  scaler: number,
): string {
  if (!value) return "—";
  if (!integerBits[value.type] || typeof value.value !== "string")
    return dataText(value);
  if (!Number.isInteger(scaler) || Math.abs(scaler) > 12) return "—";
  const negative = BigInt(value.value) < BigInt(0);
  let digits = (
    negative ? -BigInt(value.value) : BigInt(value.value)
  ).toString();
  if (scaler >= 0) digits += "0".repeat(scaler);
  else {
    digits = digits.padStart(1 - scaler, "0");
    digits = `${digits.slice(0, scaler)}.${digits.slice(scaler)}`;
  }
  return (negative ? "-" : "") + digits;
}
export function dataText(data: Dlt698Data | undefined): string {
  if (!data) return "—";
  return Array.isArray(data.value)
    ? `${data.type} [${data.value.length}]`
    : data.value === null
      ? "NULL"
      : String(data.value);
}
export function applyReadResults(
  points: Dlt698Point[],
  results: Dlt698Result[],
  requestedCodes: string[],
): Dlt698Point[] {
  // A batch can request the same point more than once. Apply responses by request
  // index so the latest result and last successful Data both remain accurate.
  // The caller keeps the complete batch separately for per-item inspection.
  const byIndex = new Map(results.map((result) => [result.index, result]));
  const byCode = new Map<string, Dlt698Result[]>();
  requestedCodes.forEach((code, index) => {
    const result = byIndex.get(index);
    if (result) byCode.set(code, [...(byCode.get(code) || []), result]);
  });
  return points.map((point) => {
    const responses = byCode.get(point.code);
    if (!responses) return point;
    const next = { ...point };
    responses.forEach((result) => {
      next.result = result;
      if (result.kind === "data" && result.data) {
        next.last_good = result.data;
        next.last_good_at = result.updated_at;
      }
    });
    return next;
  });
}
export function validateRecordQuery(query: Dlt698RecordQuery): void {
  normalizeOad(query.oad);
  query.columns.forEach(normalizeOad);
  if (!query.columns.length)
    throw new Error("Select at least one return column");
  if (query.selector === "sequences") {
    if (
      !/^\d+$/.test(query.start) ||
      !/^\d+$/.test(query.end) ||
      BigInt(query.start) >= BigInt(query.end)
    )
      throw new Error("Sequence range: start < end required");
  }
  if (query.selector === "at" || query.selector === "between") {
    parseData("DateTimeS", query.start);
    if (query.selector === "between") {
      parseData("DateTimeS", query.end);
      if (query.start >= query.end)
        throw new Error("Time range: start < end required");
    }
  }
  if (!["all", "at", "between", "sequences", "latest"].includes(query.selector))
    throw new Error("Unknown record selector");
  if (
    query.selector === "latest" &&
    (!Number.isInteger(query.latest) ||
      query.latest < 1 ||
      query.latest > 65535)
  )
    throw new Error("Latest record index: 1–65535 required");
}
export function configError(config: Dlt698Config): string | null {
  if (!/^(?:[0-9a-fA-F]{2}){1,16}$/.test(config.server_address))
    return "SA: 1–16 hexadecimal bytes required";
  if (
    !["client", "server"].includes(config.role) ||
    !["public", "preestablished"].includes(config.association)
  )
    return "Invalid role / association";
  if (
    ![
      "three_phase_four_wire",
      "three_phase_three_wire",
      "single_phase",
    ].includes(config.wiring)
  )
    return "Invalid wiring";
  for (const [key, min, max] of [
    ["logical_address", 0, 3],
    ["client_address", 0, 255],
    ["request_timeout_ms", 100, 60000],
    ["heartbeat_interval_s", 0, 3600],
    ["protocol_version", 0, 65535],
    ["send_frame_max", 64, 16383],
    ["receive_frame_max", 64, 16383],
    ["receive_window", 1, 255],
    ["apdu_max", 64, 65535],
    ["association_timeout_s", 1, 86400],
    ["tariff_count", 0, 255],
    ["harmonic_order", 1, 255],
  ] as const) {
    if (
      !Number.isInteger(config[key]) ||
      config[key] < min ||
      config[key] > max
    )
      return `${key}: ${min}–${max}`;
  }
  return null;
}
