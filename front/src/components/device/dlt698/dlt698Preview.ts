import type { Dlt698Point } from "@/types/dlt698";
/** Explicit design examples, never returned by the HTTP adapter. */
export function previewPoints(): Dlt698Point[] {
  const rows: [
    string,
    string,
    Dlt698Point["data_type"],
    string,
    number,
    string,
    Dlt698Point["category"],
  ][] = [
    ["00100201", "正向有功总电能", "UInt32", "123456", -2, "kWh", "energy"],
    ["00200201", "反向有功总电能", "UInt32", "2345", -2, "kWh", "energy"],
    ["20000201", "A 相电压", "UInt16", "2301", -1, "V", "variable"],
    ["20000202", "B 相电压", "UInt16", "2298", -1, "V", "variable"],
    ["20010201", "A 相电流", "Int32", "5000", -3, "A", "variable"],
    ["200F0200", "电网频率", "UInt16", "5000", -2, "Hz", "variable"],
    [
      "00100401",
      "高精度有功电能",
      "UInt64",
      "18446744073709551615",
      -4,
      "kWh",
      "energy",
    ],
  ];
  const points = rows.map(
    ([oad, name, type, value, scaler, unit, category], i): Dlt698Point => ({
      code: `DLT698_${oad}`,
      name,
      oad,
      category,
      data_type: type,
      unit,
      scaler,
      standard: true,
      writable: false,
      initial_value: { type, value },
      last_good: { type, value },
      last_good_at: "2026-10-13T10:24:08+08:00",
      result: { index: i, oad, kind: "data", data: { type, value } },
    }),
  );
  const voltageArray = {
    type: "Array" as const,
    value: ["2301", "2298", "2304"].map((value) => ({
      type: "UInt16" as const,
      value,
    })),
  };
  points.push({
    code: "DLT698_20000200",
    name: "三相电压数组",
    oad: "20000200",
    category: "variable",
    data_type: "Array",
    unit: "V",
    scaler: -1,
    standard: true,
    writable: false,
    initial_value: voltageArray,
    last_good: voltageArray,
    last_good_at: "2026-10-13T10:24:08+08:00",
    result: { index: 7, oad: "20000200", kind: "data", data: voltageArray },
  });
  points.push({
    code: "DLT698_F0010200",
    name: "厂家自定义对象",
    oad: "F0010200",
    category: "parameter",
    data_type: "UInt16",
    unit: "",
    scaler: 0,
    standard: false,
    writable: true,
    initial_value: { type: "UInt16", value: "0" },
    result: { index: 8, oad: "F0010200", kind: "dar", dar: 4 },
  });
  return points;
}
