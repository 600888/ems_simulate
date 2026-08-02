/// <reference types="jest" />

import {
  normalizeDlt645PointMode,
  shouldImportDlt645Standard,
} from "@/utils/dlt645PointMode";

describe("DLT645 point-table mode", () => {
  it("uses import for legacy devices whose source was not recorded", () => {
    expect(normalizeDlt645PointMode(undefined)).toBe("import");
    expect(normalizeDlt645PointMode("unknown")).toBe("import");
  });

  it("regenerates a recorded standard table when the device is saved", () => {
    expect(shouldImportDlt645Standard("standard")).toBe(true);
  });

  it("never generates standard points for an imported table", () => {
    expect(shouldImportDlt645Standard("import")).toBe(false);
  });
});
