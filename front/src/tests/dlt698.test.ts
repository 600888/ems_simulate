/// <reference types="jest" />

import type {
  Dlt698Config,
  Dlt698Data,
  Dlt698DataType,
  Dlt698Point,
  Dlt698RecordQuery,
  Dlt698Result,
} from "@/types/dlt698";
import {
  applyReadResults,
  configError,
  defaultDlt698Config,
  engineeringText,
  makeOad,
  normalizeOad,
  parseData,
  validateData,
  validateRecordQuery,
} from "@/utils/dlt698";

const point = (code: string, oad = "00100401"): Dlt698Point => ({
  code,
  oad,
  name: code,
  category: "energy",
  data_type: "UInt64",
  unit: "kWh",
  scaler: -4,
  standard: true,
  writable: false,
  initial_value: { type: "UInt64", value: "0" },
});
const query = (
  changes: Partial<Dlt698RecordQuery> = {},
): Dlt698RecordQuery => ({
  template: "daily",
  oad: "50040200",
  selector: "all",
  start: "",
  end: "",
  latest: 1,
  columns: ["20210200", "00100201"],
  ...changes,
});

describe("DL/T 698 OAD and exact Data", () => {
  it("preserves all four OAD bytes, including attribute feature bits and one-based element indices", () => {
    expect(normalizeOad(" 0x2000 82 01 ")).toBe("20008201");
    expect(makeOad("2000", 130, 1)).toBe("20008201");
    expect(makeOad("0010", 2, 0)).toBe("00100200");
    expect(makeOad("0010", 2, 1)).toBe("00100201");
    expect(makeOad("f001", 255, 255)).toBe("F001FFFF");
    for (const input of ["200002", "2000020100", "2000020G", "", "2000-0201"]) {
      expect(() => normalizeOad(input)).toThrow();
    }
    for (const [attribute, index] of [
      [-1, 0],
      [256, 0],
      [2.5, 0],
      [2, -1],
      [2, 256],
      [2, 1.5],
    ]) {
      expect(() => makeOad("2000", attribute, index)).toThrow();
    }
    expect(() => makeOad("200", 2, 1)).toThrow();
  });

  const integers: [Dlt698DataType, string, string, string, string][] = [
    ["Int8", "-128", "127", "-129", "128"],
    ["UInt8", "0", "255", "-1", "256"],
    ["Int16", "-32768", "32767", "-32769", "32768"],
    ["UInt16", "0", "65535", "-1", "65536"],
    ["Int32", "-2147483648", "2147483647", "-2147483649", "2147483648"],
    ["UInt32", "0", "4294967295", "-1", "4294967296"],
    [
      "Int64",
      "-9223372036854775808",
      "9223372036854775807",
      "-9223372036854775809",
      "9223372036854775808",
    ],
    ["UInt64", "0", "18446744073709551615", "-1", "18446744073709551616"],
    ["Enum", "0", "255", "-1", "256"],
  ];
  it.each(integers)(
    "checks %s bounds without converting through floating point",
    (type, min, max, below, above) => {
      expect(parseData(type, min)).toEqual({ type, value: min });
      expect(parseData(type, max)).toEqual({ type, value: max });
      expect(() => parseData(type, below)).toThrow(/out of range/);
      expect(() => parseData(type, above)).toThrow(/out of range/);
      expect(() =>
        validateData({ type, value: 1 } as unknown as Dlt698Data),
      ).toThrow(/string/);
      for (const text of ["1.0", "1e3", " 1 ", "NaN", ""]) {
        expect(() => parseData(type, text)).toThrow();
      }
    },
  );

  it("retains UInt64 and signed Int64 precision when displaying engineering units", () => {
    const maximum = parseData("UInt64", "18446744073709551615");
    expect(JSON.parse(JSON.stringify(maximum))).toEqual(maximum);
    expect(engineeringText(maximum, -4)).toBe("1844674407370955.1615");
    expect(
      engineeringText(parseData("Int64", "-9223372036854775808"), -4),
    ).toBe("-922337203685477.5808");
    expect(engineeringText(parseData("Int32", "-5"), -3)).toBe("-0.005");
    expect(engineeringText(parseData("UInt32", "123456"), -2)).toBe("1234.56");
    expect(engineeringText(parseData("Int32", "5000"), -3)).toBe("5.000");
    expect(engineeringText(parseData("UInt16", "0"), -4)).toBe("0.0000");
    expect(engineeringText(parseData("UInt16", "12"), 2)).toBe("1200");
    expect(engineeringText(maximum, 1.5)).toBe("—");
    expect(engineeringText(undefined, -4)).toBe("—");
  });

  it("recursively validates heterogeneous structures and nested arrays without flattening their types", () => {
    const data: Dlt698Data = {
      type: "Structure",
      value: [
        { type: "DateTimeS", value: "2026-10-13T08:30:00" },
        {
          type: "Array",
          value: [
            { type: "UInt64", value: "18446744073709551615" },
            {
              type: "Structure",
              value: [
                { type: "Boolean", value: false },
                { type: "Null", value: null },
              ],
            },
          ],
        },
      ],
    };
    expect(parseData("Structure", JSON.stringify(data.value))).toEqual(data);
    expect(engineeringText(data, -2)).toBe("Structure [2]");
    expect(() =>
      parseData("Array", '[{"type":"UInt16","value":"65536"}]'),
    ).toThrow(/out of range/);
    expect(() =>
      parseData(
        "Structure",
        '[{"type":"Array","value":[{"type":"Boolean","value":"false"}]}]',
      ),
    ).toThrow(/Boolean/);
    expect(() => parseData("Array", "[1]")).toThrow(/Unknown Data/);
    expect(() => parseData("Array", "{} ")).toThrow(/typed children/);
    expect(() => parseData("Array", "[null]")).toThrow(/Unknown Data/);
  });

  it("keeps Boolean and string values explicit and validates binary bytes", () => {
    expect(parseData("Boolean", "false")).toEqual({
      type: "Boolean",
      value: false,
    });
    expect(parseData("Boolean", "true")).toEqual({
      type: "Boolean",
      value: true,
    });
    expect(() => parseData("Boolean", '"false"')).toThrow(/Boolean/);
    expect(() => parseData("Boolean", "0")).toThrow(/Boolean/);
    expect(parseData("Utf8String", "  电能  ")).toEqual({
      type: "Utf8String",
      value: "  电能  ",
    });
    expect(parseData("OctetString", "00abFF").value).toBe("00abFF");
    expect(() => parseData("OctetString", "FFF")).toThrow(/byte pairs/);
    expect(() => parseData("BitString", "102")).toThrow(/binary/);
    expect(() => validateData({ type: "Null", value: "null" })).toThrow(
      /null required/,
    );
  });

  it("rejects invalid calendar dates, time overflow and ambiguous date-time formats", () => {
    expect(parseData("Date", "2024-02-29").value).toBe("2024-02-29");
    expect(parseData("Time", "23:59:59").value).toBe("23:59:59");
    expect(parseData("DateTime", "2026-10-13T08:30:00").value).toBe(
      "2026-10-13T08:30:00",
    );
    for (const value of ["2026-02-29", "2026-04-31", "2026-13-01"]) {
      expect(() => parseData("Date", value)).toThrow(/invalid date/);
    }
    for (const value of ["24:00:00", "23:60:00", "23:59:60"]) {
      expect(() => parseData("Time", value)).toThrow(/invalid date/);
    }
    for (const value of [
      "2026-10-13 08:30:00",
      "2026-10-13T08:30:00Z",
      "2026-10-13T08:30:00+08:00",
    ]) {
      expect(() => parseData("DateTimeS", value)).toThrow(/ISO local/);
    }
  });

  it("rejects non-finite floats and Float32 overflow before submitting typed Data", () => {
    expect(parseData("Float32", "3.4e38").value).toBe("3.4e38");
    expect(() => parseData("Float32", "3.5e38")).toThrow(/range/);
    expect(parseData("Float64", "3.5e38").value).toBe("3.5e38");
    for (const value of ["NaN", "Infinity", "1e500", " "]) {
      expect(() => parseData("Float64", value)).toThrow(/finite/);
    }
  });
});

describe("DL/T 698 per-item read outcomes", () => {
  it("updates by request index even when the response list is returned out of order", () => {
    const points = [
      point("energy"),
      point("voltage", "20000201"),
      point("untouched"),
    ];
    const results: Dlt698Result[] = [
      {
        index: 1,
        oad: "00100401",
        kind: "data",
        data: { type: "UInt64", value: "18446744073709551615" },
        updated_at: "2026-10-13T08:31:00",
      },
      { index: 0, oad: "20000201", kind: "dar", dar: 3 },
    ];
    const next = applyReadResults(points, results, ["voltage", "energy"]);
    expect(next[0].last_good).toEqual(results[0].data);
    expect(next[0].last_good_at).toBe(results[0].updated_at);
    expect(next[1].result).toBe(results[1]);
    expect(next[1].last_good).toBeUndefined();
    expect(next[2]).toBe(points[2]);
    expect(points[0].result).toBeUndefined();
  });

  it.each([
    "dar",
    "transport_error",
    "validation_error",
    "unknown",
    "pending",
  ] as const)(
    "preserves the last successful Data and timestamp after %s",
    (kind) => {
      const existing = {
        ...point("energy"),
        last_good: { type: "UInt64", value: "123456" } as Dlt698Data,
        last_good_at: "2026-10-13T08:30:00",
      };
      const raw: Dlt698Data = {
        type: "Utf8String",
        value: "unexpected type from device",
      };
      const result: Dlt698Result = {
        index: 0,
        oad: existing.oad,
        kind,
        data: kind === "validation_error" ? raw : undefined,
        message: "Device result",
      };
      const [next] = applyReadResults([existing], [result], [existing.code]);
      expect(next.last_good).toBe(existing.last_good);
      expect(next.last_good_at).toBe(existing.last_good_at);
      expect(next.result).toBe(result);
      if (kind === "validation_error") expect(next.result?.data).toBe(raw);
    },
  );

  it("keeps repeated requests in request order and retains an earlier successful value after a later failure", () => {
    const results: Dlt698Result[] = [
      {
        index: 2,
        oad: "00100401",
        kind: "transport_error",
        message: "Timeout",
      },
      {
        index: 1,
        oad: "00100401",
        kind: "data",
        data: { type: "UInt64", value: "9007199254740993" },
        updated_at: "2026-10-13T08:32:00",
      },
      {
        index: 0,
        oad: "00100401",
        kind: "data",
        data: { type: "UInt64", value: "10" },
        updated_at: "2026-10-13T08:31:00",
      },
    ];
    const originalOrder = results.slice();
    const [next] = applyReadResults([point("energy")], results, [
      "energy",
      "energy",
      "energy",
    ]);
    expect(next.result).toBe(results[0]);
    expect(next.last_good).toEqual({
      type: "UInt64",
      value: "9007199254740993",
    });
    expect(next.last_good_at).toBe("2026-10-13T08:32:00");
    expect(results).toEqual(originalOrder);
  });

  it("ignores missing and unrequested response positions", () => {
    const original = point("energy");
    const unrelated: Dlt698Result = {
      index: 5,
      oad: original.oad,
      kind: "dar",
      dar: 3,
    };
    expect(applyReadResults([original], [unrelated], [original.code])[0]).toBe(
      original,
    );
  });
});

describe("DL/T 698 record ranges and configuration", () => {
  it("validates strictly increasing half-open time and sequence intervals with exact integer comparisons", () => {
    expect(() =>
      validateRecordQuery(
        query({
          selector: "between",
          start: "2026-10-13T00:00:00",
          end: "2026-10-14T00:00:00",
        }),
      ),
    ).not.toThrow();
    expect(() =>
      validateRecordQuery(
        query({
          selector: "sequences",
          start: "9007199254740992",
          end: "9007199254740993",
        }),
      ),
    ).not.toThrow();
    for (const [start, end] of [
      ["7", "7"],
      ["8", "7"],
      ["-1", "7"],
      ["1.5", "7"],
    ]) {
      expect(() =>
        validateRecordQuery(query({ selector: "sequences", start, end })),
      ).toThrow();
    }
    for (const end of ["2026-10-13T00:00:00", "2026-10-12T00:00:00"]) {
      expect(() =>
        validateRecordQuery(
          query({ selector: "between", start: "2026-10-13T00:00:00", end }),
        ),
      ).toThrow(/start < end/);
    }
    expect(() =>
      validateRecordQuery(
        query({ selector: "at", start: "2026-02-29T00:00:00" }),
      ),
    ).toThrow(/invalid date/);
  });

  it("validates required return columns, latest record bounds and unknown selectors", () => {
    expect(() => validateRecordQuery(query({ columns: [] }))).toThrow(/column/);
    expect(() => validateRecordQuery(query({ columns: ["2021020G"] }))).toThrow(
      /hexadecimal/,
    );
    expect(() =>
      validateRecordQuery(query({ selector: "latest", latest: 65535 })),
    ).not.toThrow();
    for (const latest of [0, -1, 1.5, 65536]) {
      expect(() =>
        validateRecordQuery(query({ selector: "latest", latest })),
      ).toThrow();
    }
    expect(() =>
      validateRecordQuery(
        query({
          selector: "unsupported",
        } as unknown as Partial<Dlt698RecordQuery>),
      ),
    ).toThrow(/selector/);
  });

  it("accepts 1–16 server-address bytes and reports invalid protocol field values", () => {
    expect(configError(defaultDlt698Config())).toBeNull();
    expect(
      configError({ ...defaultDlt698Config(), server_address: "01" }),
    ).toBeNull();
    expect(
      configError({
        ...defaultDlt698Config(),
        server_address: "ab".repeat(16),
        wiring: "single_phase",
      }),
    ).toBeNull();
    for (const server_address of [
      "",
      "1",
      "ab".repeat(17),
      "0000GG",
      "01 02",
    ]) {
      expect(configError({ ...defaultDlt698Config(), server_address })).toMatch(
        /SA/,
      );
    }
    const invalid: Partial<Dlt698Config>[] = [
      { logical_address: 4 },
      { client_address: 256 },
      { request_timeout_ms: 99 },
      { heartbeat_interval_s: -1 },
      { protocol_version: 65536 },
      { send_frame_max: 63 },
      { receive_frame_max: 16384 },
      { receive_window: 0 },
      { apdu_max: 65536 },
      { association_timeout_s: 0 },
      { tariff_count: 256 },
      { harmonic_order: 0 },
      { logical_address: 1.5 },
      { role: "unsupported" } as unknown as Partial<Dlt698Config>,
      { association: "unsupported" } as unknown as Partial<Dlt698Config>,
      { wiring: "unsupported" } as unknown as Partial<Dlt698Config>,
    ];
    for (const values of invalid)
      expect(
        configError({ ...defaultDlt698Config(), ...values }),
      ).not.toBeNull();
  });
});
