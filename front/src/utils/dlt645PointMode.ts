export type Dlt645PointMode = "standard" | "import";

/** Unknown legacy values use the non-destructive import mode. */
export function normalizeDlt645PointMode(value: unknown): Dlt645PointMode {
  return value === "standard" ? "standard" : "import";
}

/** Import the built-in table only when it is first selected, not on every edit. */
export function shouldImportDlt645Standard(
  mode: Dlt645PointMode,
  isEdit: boolean,
  originalMode: Dlt645PointMode,
): boolean {
  return mode === "standard" && (!isEdit || originalMode !== "standard");
}
