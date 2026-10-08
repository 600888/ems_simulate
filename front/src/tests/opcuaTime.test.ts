import {
  beijingDateTimeToISOString,
  defaultBeijingTimeRange,
  formatBeijingDateTime,
  formatBeijingTime,
  opcUaTimestampMillis,
} from "@/utils/opcuaTime";
import { normalizeTrendSamples } from "@/utils/opcuaTrendPlot";

test("UTC, explicit offsets and UTC timestamps without offsets show the same Beijing time", () => {
  for (const time of [
    "2026-10-07T16:30:45.123456Z",
    "2026-10-08T00:30:45.123+08:00",
    "2026-10-07T09:30:45.123-07:00",
    "2026-10-07T16:30:45.123",
  ]) {
    expect(formatBeijingDateTime(time)).toBe("2026-10-08 00:30:45.123");
    expect(formatBeijingTime(time)).toBe("00:30:45");
  }
});

test("midnight rolls over the year and uses hour 00", () => {
  expect(formatBeijingDateTime("2026-12-31T16:00:00Z")).toBe(
    "2027-01-01 00:00:00.000",
  );
});

test.each([null, undefined, "", "not-a-date", NaN])(
  "missing or invalid timestamp %p has a placeholder",
  (value) => expect(formatBeijingDateTime(value)).toBe("—"),
);

test("Beijing history input converts to the correct UTC instant", () => {
  expect(beijingDateTimeToISOString("2026-10-08 00:30:45")).toBe(
    "2026-10-07T16:30:45.000Z",
  );
  const now = Date.parse("2026-10-07T16:30:45Z");
  expect(defaultBeijingTimeRange(now)).toEqual([
    "2026-10-07 23:30:45",
    "2026-10-08 00:30:45",
  ]);
  expect(beijingDateTimeToISOString(defaultBeijingTimeRange(now)[1])).toBe(
    new Date(now).toISOString(),
  );
});

test("trend parsing treats timestamps without offsets as UTC too", () => {
  const timestamp = "2026-10-07T16:30:45";
  expect(opcUaTimestampMillis(timestamp)).toBe(Date.parse(`${timestamp}Z`));
  expect(normalizeTrendSamples([{ timestamp, value: 12 }])[0].time).toBe(
    Date.parse(`${timestamp}Z`),
  );
});
