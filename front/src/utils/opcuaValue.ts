export const OPCUA_SCALAR_TYPES = [
  "Boolean",
  "SByte",
  "Byte",
  "Int16",
  "UInt16",
  "Int32",
  "UInt32",
  "Int64",
  "UInt64",
  "Float",
  "Double",
  "String",
  "DateTime",
  "ByteString",
] as const;
export type OpcUaScalarType = (typeof OPCUA_SCALAR_TYPES)[number];

export class OpcUaScalarError extends Error {
  constructor(readonly type: OpcUaScalarType) {
    super(
      type === "Boolean"
        ? "Boolean 值只能是 true、false、1 或 0"
        : `请输入有效的 ${type} 值`,
    );
  }
}

export function parseOpcUaScalar(
  text: string,
  type: OpcUaScalarType,
): boolean | number | string | { base64: string } | { integer: string } {
  const normalized = text.trim();
  if (type === "String") return text;
  if (type === "DateTime") {
    if (
      !/(Z|[+-]\d\d:\d\d)$/.test(normalized) ||
      !Number.isFinite(Date.parse(normalized))
    )
      throw new OpcUaScalarError(type);
    return new Date(normalized).toISOString();
  }
  if (type === "ByteString") {
    try {
      atob(normalized);
    } catch {
      throw new OpcUaScalarError(type);
    }
    return { base64: normalized };
  }
  if (type === "Int64" || type === "UInt64") {
    if (!/^-?\d+$/.test(normalized)) throw new OpcUaScalarError(type);
    const integer = BigInt(normalized);
    const lower = BigInt(type === "UInt64" ? "0" : "-9223372036854775808");
    const upper = BigInt(
      type === "UInt64" ? "18446744073709551615" : "9223372036854775807",
    );
    if (integer < lower || integer > upper) throw new OpcUaScalarError(type);
    return { integer: normalized };
  }
  if (type === "Boolean") {
    if (!["true", "false", "1", "0"].includes(normalized.toLowerCase())) {
      throw new OpcUaScalarError(type);
    }
    return ["true", "1"].includes(normalized.toLowerCase());
  }
  const value = Number(normalized);
  const ranges: Record<string, [number, number]> = {
    SByte: [-128, 127],
    Byte: [0, 255],
    Int16: [-32768, 32767],
    UInt16: [0, 65535],
    Int32: [-2147483648, 2147483647],
    UInt32: [0, 4294967295],
  };
  const range = ranges[type];
  if (
    !normalized ||
    !Number.isFinite(value) ||
    (range &&
      (!Number.isInteger(value) || value < range[0] || value > range[1])) ||
    (type === "Float" && Math.abs(value) > 3.4028234663852886e38)
  ) {
    throw new OpcUaScalarError(type);
  }
  return value;
}
