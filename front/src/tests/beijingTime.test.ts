import {
  beijingTimestampMillis,
  formatBeijingDateTime,
  formatBeijingTime,
} from "@/utils/beijingTime";
import { formatGooseTime } from "@/components/goose/gooseWorkbench";

test.each([
  "2026-10-17T14:25:09.536970+00:00",
  "2026-10-17T14:25:09.536970Z",
  "2026-10-17T22:25:09.536+08:00",
  "2026-10-17T07:25:09.536-07:00",
  "2026-10-17 22:25:09.536",
  "2026-10-17T22:25:09.536",
  Date.parse("2026-10-17T14:25:09.536Z"),
  new Date("2026-10-17T14:25:09.536Z"),
])(
  "timestamp %p displays in Beijing independently of the host zone",
  (value) => {
    expect(formatBeijingDateTime(value)).toBe("2026-10-17 22:25:09.536");
    expect(formatBeijingDateTime(value, false)).toBe("2026-10-17 22:25:09");
    expect(formatBeijingTime(value)).toBe("22:25:09");
  },
);

test("Beijing midnight rolls over the day and year", () => {
  expect(formatBeijingDateTime("2026-12-31T16:00:00Z")).toBe(
    "2027-01-01 00:00:00.000",
  );
});

test.each([null, undefined, "", "invalid", NaN, Infinity, 1e20])(
  "invalid timestamp %p uses a placeholder",
  (value) => expect(formatBeijingDateTime(value)).toBe("—"),
);

test("legacy Beijing timestamps and GOOSE epoch seconds keep their instant", () => {
  const ms = Date.parse("2026-10-17T14:25:09.536Z");
  expect(beijingTimestampMillis("2026-10-17 22:25:09.536")).toBe(ms);
  expect(formatGooseTime(ms)).toBe("2026-10-17 22:25:09.536");
  expect(formatGooseTime(ms / 1000)).toBe("2026-10-17 22:25:09.536");
  expect(formatGooseTime("2026-10-17T14:25:09.536Z")).toBe(
    "2026-10-17 22:25:09.536",
  );
  expect(formatGooseTime(0)).toBe("-");
});
