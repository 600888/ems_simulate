/// <reference types="jest" />

import { formatTableRealValue } from "@/utils/tableValue";

describe("formatTableRealValue", () => {
  it("keeps the existing three-decimal formatting for numeric values", () => {
    expect(formatTableRealValue(12.5)).toBe("12.500");
    expect(formatTableRealValue("12.5")).toBe("12.500");
    expect(formatTableRealValue(0)).toBe("0.000");
  });

  it("preserves a DLT645 compound value instead of truncating it", () => {
    const demand = "12.5, 2026-08-02 11:30:00";
    expect(formatTableRealValue(demand)).toBe(demand);
  });

  it("keeps other non-numeric protocol values intact", () => {
    expect(formatTableRealValue("00000000, 00000000")).toBe(
      "00000000, 00000000",
    );
    expect(formatTableRealValue(null)).toBe("");
  });
});
