export type Dlt645PointMode = "standard" | "import";

/** Unknown legacy values use the non-destructive import mode. */
export function normalizeDlt645PointMode(value: unknown): Dlt645PointMode {
  return value === "standard" ? "standard" : "import";
}

/** Standard mode intentionally regenerates the table whenever it is saved. */
export function shouldImportDlt645Standard(mode: Dlt645PointMode): boolean {
  return mode === "standard";
}
