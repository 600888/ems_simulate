import { OpcUaScalarError, parseOpcUaScalar } from "@/utils/opcuaValue";

describe("OPC UA scalar input", () => {
  it("preserves Boolean values and rejects truthy strings", () => {
    expect(parseOpcUaScalar("false", "Boolean")).toBe(false);
    expect(parseOpcUaScalar(" TRUE ", "Boolean")).toBe(true);
    expect(parseOpcUaScalar("0", "Boolean")).toBe(false);
    expect(() => parseOpcUaScalar("yes", "Boolean")).toThrow(OpcUaScalarError);
  });

  it("checks signed Int32 boundaries before a write", () => {
    expect(parseOpcUaScalar("-2147483648", "Int32")).toBe(-2147483648);
    expect(parseOpcUaScalar("2147483647", "Int32")).toBe(2147483647);
    for (const text of ["2147483648", "-2147483649", "1.5", ""]) {
      expect(() => parseOpcUaScalar(text, "Int32")).toThrow(OpcUaScalarError);
    }
  });

  it("accepts finite Double values and rejects NaN, infinity and empty input", () => {
    expect(parseOpcUaScalar("12.5", "Double")).toBe(12.5);
    expect(parseOpcUaScalar("-1e6", "Double")).toBe(-1000000);
    for (const text of ["NaN", "Infinity", "1e500", "  "]) {
      expect(() => parseOpcUaScalar(text, "Double")).toThrow(OpcUaScalarError);
    }
  });
});
