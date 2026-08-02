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

  it("imports the standard table for a new device", () => {
    expect(shouldImportDlt645Standard("standard", false, "import")).toBe(true);
  });

  it("does not reimport an existing standard table during a normal edit", () => {
    expect(shouldImportDlt645Standard("standard", true, "standard")).toBe(
      false,
    );
  });

  it("imports once when an edited device switches to the standard table", () => {
    expect(shouldImportDlt645Standard("standard", true, "import")).toBe(true);
  });

  it("never generates standard points while import mode is selected", () => {
    expect(shouldImportDlt645Standard("import", true, "standard")).toBe(false);
  });
});
