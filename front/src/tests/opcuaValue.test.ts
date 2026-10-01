import { OpcUaScalarError, parseOpcUaScalar } from "@/utils/opcuaValue";

describe("OPC UA scalar input", () => {
  it("preserves Int64 precision and unsigned bounds", () => {
    expect(parseOpcUaScalar("9223372036854775807", "Int64")).toEqual({
      integer: "9223372036854775807",
    });
    expect(parseOpcUaScalar("18446744073709551615", "UInt64")).toEqual({
      integer: "18446744073709551615",
    });
    expect(() => parseOpcUaScalar("18446744073709551616", "UInt64")).toThrow(
      OpcUaScalarError,
    );
    expect(() => parseOpcUaScalar("-1", "UInt64")).toThrow(OpcUaScalarError);
  });

  it("preserves strings and validates UTC conversion and ByteString", () => {
    expect(parseOpcUaScalar(" hello ", "String")).toBe(" hello ");
    expect(parseOpcUaScalar("2026-10-01T08:00:00+08:00", "DateTime")).toBe(
      "2026-10-01T00:00:00.000Z",
    );
    expect(() => parseOpcUaScalar("2026-10-01", "DateTime")).toThrow(
      OpcUaScalarError,
    );
    expect(parseOpcUaScalar("AAE=", "ByteString")).toEqual({ base64: "AAE=" });
  });
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
