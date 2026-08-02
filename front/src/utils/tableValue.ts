/**
 * 格式化表格的“真实值”。
 *
 * 普通数值保持原来的三位小数显示；DL/T 645 的复合数据（例如
 * “最大需量, 发生时间”）必须完整保留，不能用 parseFloat 截断。
 */
export function formatTableRealValue(value: unknown): string {
  if (value === null || value === undefined || value === "None") return "";

  if (typeof value === "number") {
    return Number.isFinite(value) ? value.toFixed(3) : String(value);
  }

  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed === "") return "0.000";

    const numericValue = Number(trimmed);
    return Number.isFinite(numericValue) ? numericValue.toFixed(3) : value;
  }

  return String(value);
}
