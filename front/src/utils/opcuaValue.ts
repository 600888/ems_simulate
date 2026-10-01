export type OpcUaScalarType = "Boolean" | "Int32" | "Double";

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
): boolean | number {
  const normalized = text.trim();
  if (type === "Boolean") {
    if (!["true", "false", "1", "0"].includes(normalized.toLowerCase())) {
      throw new OpcUaScalarError(type);
    }
    return ["true", "1"].includes(normalized.toLowerCase());
  }
  const value = Number(normalized);
  if (
    !normalized ||
    !Number.isFinite(value) ||
    (type === "Int32" &&
      (!Number.isInteger(value) || value < -2147483648 || value > 2147483647))
  ) {
    throw new OpcUaScalarError(type);
  }
  return value;
}
