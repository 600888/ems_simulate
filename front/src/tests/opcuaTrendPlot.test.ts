import {
  normalizeTrendSamples,
  trendExtent,
  zoomPlotRange,
  panPlotRange,
  fitPlotRange,
  plotFraction,
  plotValue,
  nearestTrendSample,
  visibleTrendSamples,
  trendPath,
  isolatedTrendSamples,
} from "@/utils/opcuaTrendPlot";

const start = Date.parse("2026-10-02T08:00:00Z");
const points = (values: unknown[]) =>
  values.map((value, index) => ({
    timestamp: new Date(start + index * 1000).toISOString(),
    value,
    status: "Good",
  }));

test("zoom preserves the sample under the cursor and clamps its maximum extent", () => {
  const range = { min: start, max: start + 10000 };
  const anchor = start + 2500;
  const zoomed = zoomPlotRange(range, anchor, 0.5, range, 1);
  expect(zoomed.max - zoomed.min).toBe(5000);
  expect(plotFraction(anchor, zoomed)).toBeCloseTo(0.25);
  expect(zoomPlotRange(zoomed, anchor, 100, range)).toEqual(range);
});

test("repeated zoom never collapses the time or value axis", () => {
  const bounds = { min: start, max: start + 10000 };
  let range = bounds;
  for (let i = 0; i < 100; i++)
    range = zoomPlotRange(range, (range.min + range.max) / 2, 0.1, bounds, 1);
  expect(range.max - range.min).toBeGreaterThanOrEqual(1);
  expect(Number.isFinite(plotFraction(range.min, range))).toBe(true);
});

test("pan and data-window changes preserve view width within available data", () => {
  const bounds = { min: 0, max: 100 };
  expect(panPlotRange({ min: 20, max: 40 }, -1000, bounds)).toEqual({
    min: 0,
    max: 20,
  });
  expect(panPlotRange({ min: 20, max: 40 }, 1000, bounds)).toEqual({
    min: 80,
    max: 100,
  });
  expect(fitPlotRange({ min: 20, max: 40 }, { min: 35, max: 200 })).toEqual({
    min: 35,
    max: 55,
  });
});

test("hover selects the nearest visible timestamp, including right and left boundaries", () => {
  const samples = normalizeTrendSamples(points([1, 2, 3, 4]));
  const range = { min: start + 1000, max: start + 2000 };
  expect(nearestTrendSample(samples, start + 1600, range)?.value).toBe(3);
  expect(nearestTrendSample(samples, start + 1000, range)?.value).toBe(2);
  expect(nearestTrendSample(samples, start + 2000, range)?.value).toBe(3);
  expect(
    nearestTrendSample(samples, start + 1400, {
      min: start + 1300,
      max: start + 1700,
    }),
  ).toBeNull();
});

test("invalid readings and bad quality preserve line breaks", () => {
  const samples = normalizeTrendSamples(points([1, 2, null, 4, 5, 6, 7]));
  samples[3].status = "BadNoCommunication";
  const path = trendPath(
    samples,
    (time) => (time - start) / 1000,
    (value) => value,
  );
  expect(path).toBe("M0,1 L1,2 M3,4 M4,5 M5,6 L6,7");
});

test("single points and constant zero values have finite padded axes", () => {
  const samples = normalizeTrendSamples(points([0]));
  const extent = trendExtent(samples)!;
  expect(extent.time.max).toBeGreaterThan(extent.time.min);
  expect(extent.value).toEqual({ min: -1, max: 1 });
  expect(plotFraction(0, extent.value)).toBe(0.5);
  expect(trendExtent([])).toBeNull();
});

test("small variations on a large baseline remain visible", () => {
  const extent = trendExtent(normalizeTrendSamples(points([1000, 1001])))!;
  expect(extent.value.min).toBeCloseTo(999.9);
  expect(extent.value.max).toBeCloseTo(1001.1);
});

test("cropped paths include edge neighbors and duplicate boundary timestamps", () => {
  const samples = normalizeTrendSamples(points([0, 1, 2, 3, 4]));
  samples.splice(3, 0, { ...samples[2], value: 20 });
  const view = visibleTrendSamples(samples, {
    min: start + 1500,
    max: start + 2000,
  });
  expect(view.map((sample) => sample.value)).toEqual([1, 2, 20, 3]);
});

test("out-of-order timestamps are sorted without mutating input", () => {
  const input = points([1, 2, 3]).reverse();
  expect(normalizeTrendSamples(input).map((sample) => sample.value)).toEqual([
    1, 2, 3,
  ]);
  expect(input[0].value).toBe(3);
});

test("out-of-order null readings interrupt the correct chronological segment", () => {
  const samples = normalizeTrendSamples(points([0, 1, null, 3]).reverse());
  expect(samples.map((sample) => sample.value)).toEqual([0, 1, 3]);
  expect(
    trendPath(
      samples,
      (time) => (time - start) / 1000,
      (value) => value,
    ),
  ).toBe("M0,0 L1,1 M3,3");
});

test("unknown timestamps preserve arrival gaps and explicit sample boundaries", () => {
  const input = points([0, 1, 2, 3]);
  const samples = normalizeTrendSamples([
    input[3],
    { timestamp: "invalid", value: 99 },
    { ...input[2], value: null },
    input[1],
    input[0],
    { ...input[2], breakBefore: true },
  ]);
  expect(samples.map((sample) => sample.value)).toEqual([0, 1, 2, 3]);
  expect(samples.map((sample) => sample.breakBefore)).toEqual([
    false,
    true,
    true,
    false,
  ]);
});

test("extreme finite readings do not generate NaN coordinates", () => {
  const extent = trendExtent(normalizeTrendSamples(points([-1e308, 1e308])))!;
  expect(plotFraction(0, extent.value)).toBeCloseTo(0.5);
  expect(plotValue(0.5, extent.value)).toBe(0);
});

test("finite readings outside a zoomed value range retain renderable coordinates", () => {
  const maximum = Number.MAX_VALUE;
  const range = { min: -maximum, max: -maximum / 2 };
  expect(plotFraction(maximum, range)).toBeCloseTo(4);
  expect(plotFraction(-maximum, range)).toBe(0);
  const path = trendPath(
    normalizeTrendSamples(points([-maximum, maximum])),
    (time) => (time - start) / 1000,
    (value) => 280 - plotFraction(value, range) * 255,
  );
  expect(path).not.toMatch(/NaN|Infinity/);
  expect(
    Number.isFinite(plotFraction(maximum, { min: 0, max: 1e-300 }) * 255),
  ).toBe(true);
});

test("zoom works when the difference between finite bounds overflows", () => {
  const maximum = Number.MAX_VALUE;
  const bounds = { min: -maximum, max: maximum };
  const anchor = -maximum / 2;
  const zoomed = zoomPlotRange(bounds, anchor, 0.5, bounds);
  expect(Number.isFinite(zoomed.min)).toBe(true);
  expect(Number.isFinite(zoomed.max)).toBe(true);
  expect(zoomed.min / maximum).toBeCloseTo(-0.75);
  expect(zoomed.max / maximum).toBeCloseTo(0.25);
  expect(plotFraction(anchor, zoomed)).toBeCloseTo(0.25);
  expect(zoomed.max - zoomed.min).toBeLessThanOrEqual(maximum);
});

test("extreme panning clamps to bounds without overflowing or widening the view", () => {
  const maximum = Number.MAX_VALUE;
  const bounds = { min: -maximum, max: maximum };
  const panned = panPlotRange(
    { min: maximum / 2, max: maximum },
    maximum,
    bounds,
  );
  expect(panned.min / maximum).toBeCloseTo(0.5);
  expect(panned.max / maximum).toBeCloseTo(1);
  const fitted = fitPlotRange(
    { min: -maximum * 0.75, max: maximum * 0.75 },
    bounds,
  );
  expect(fitted.min / maximum).toBeCloseTo(-0.75);
  expect(fitted.max / maximum).toBeCloseTo(0.75);
});

test("good samples isolated by invalid readings or bad quality remain available as markers", () => {
  const samples = normalizeTrendSamples(points([1, null, 2, 3, 4, 5]));
  samples[2].status = "BadNoCommunication";
  samples[4].breakBefore = true;
  expect(isolatedTrendSamples(samples).map((sample) => sample.value)).toEqual([
    1, 2, 4, 5,
  ]);
  expect(
    isolatedTrendSamples(normalizeTrendSamples(points([1, 2, 3]))),
  ).toEqual([]);
  expect(
    isolatedTrendSamples(normalizeTrendSamples(points([1])))[0].value,
  ).toBe(1);
});

test("identical timestamps and values still have a visible good marker", () => {
  const sample = normalizeTrendSamples(points([1]))[0];
  const duplicates = [{ ...sample }, { ...sample }];
  expect(isolatedTrendSamples(duplicates)).toHaveLength(2);
  expect(
    isolatedTrendSamples([{ ...sample }, { ...sample, value: 2 }]),
  ).toEqual([]);
});
