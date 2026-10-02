export interface TrendPoint {
  timestamp: string | null | undefined;
  value: unknown;
  status?: string;
  breakBefore?: boolean;
}

export interface TrendSample extends TrendPoint {
  time: number;
  value: number;
}

export interface PlotRange {
  min: number;
  max: number;
}
export interface PlotViewport {
  time: PlotRange;
  value: PlotRange;
}

/** Invalid readings are gaps, even when they cannot be drawn themselves. */
export function normalizeTrendSamples(points: TrendPoint[]): TrendSample[] {
  const dated: (TrendPoint & { time: number })[] = [];
  let unknownTimeGap = false;
  for (const point of points) {
    const time = Date.parse(point.timestamp || "");
    if (!Number.isFinite(time)) {
      unknownTimeGap = true;
      continue;
    }
    const numeric =
      typeof point.value === "number" && Number.isFinite(point.value);
    dated.push({
      ...point,
      time,
      // A gap with no timestamp can only be attached to the next arrival.
      breakBefore: !!point.breakBefore || (numeric && unknownTimeGap),
    });
    if (numeric) unknownTimeGap = false;
  }
  dated.sort((a, b) => a.time - b.time);
  const samples: TrendSample[] = [];
  let interrupted = false;
  for (const point of dated) {
    if (typeof point.value !== "number" || !Number.isFinite(point.value)) {
      interrupted = true;
      continue;
    }
    samples.push({
      ...point,
      value: point.value,
      breakBefore: !!point.breakBefore || interrupted,
    });
    interrupted = false;
  }
  return samples;
}

export function trendExtent(samples: TrendSample[]): PlotViewport | null {
  if (!samples.length) return null;
  let min = Infinity,
    max = -Infinity;
  for (const sample of samples) {
    min = Math.min(min, sample.value);
    max = Math.max(max, sample.value);
  }
  const span = max - min;
  const padding =
    Number.isFinite(span) && span > 0
      ? span * 0.1
      : Math.max(Math.abs(max) * 0.1, 1);
  const value = {
    min: Math.max(-Number.MAX_VALUE, min - padding),
    max: Math.min(Number.MAX_VALUE, max + padding),
  };
  const first = samples[0].time,
    last = samples[samples.length - 1].time;
  return {
    time:
      first === last
        ? { min: first - 500, max: last + 500 }
        : { min: first, max: last },
    value,
  };
}

export function plotFraction(value: number, range: PlotRange): number {
  const span = range.max - range.min;
  if (span === 0)
    return value === range.min ? 0.5 : value < range.min ? -1e12 : 1e12;
  let fraction = (value - range.min) / span;
  if (!Number.isFinite(span) || !Number.isFinite(fraction)) {
    const scale = Math.max(
      Math.abs(value),
      Math.abs(range.min),
      Math.abs(range.max),
      1,
    );
    fraction =
      (value / scale - range.min / scale) /
      (range.max / scale - range.min / scale);
  }
  // Distant, clipped samples still need finite SVG coordinates after projection.
  return Math.max(-1e12, Math.min(1e12, fraction));
}

export function plotValue(fraction: number, range: PlotRange): number {
  const span = range.max - range.min;
  if (Number.isFinite(span)) return range.min + span * fraction;
  return range.min * (1 - fraction) + range.max * fraction;
}

export function fitPlotRange(range: PlotRange, bounds: PlotRange): PlotRange {
  const span = range.max - range.min,
    extent = bounds.max - bounds.min;
  if (!(span > 0)) return { ...bounds };
  if (!Number.isFinite(span) && !Number.isFinite(extent)) {
    const scale = rangeScale(range, bounds);
    return scaleRange(
      fitPlotRange(scaleRange(range, 1 / scale), scaleRange(bounds, 1 / scale)),
      scale,
    );
  }
  if (span >= extent) return { ...bounds };
  const min = Math.min(Math.max(range.min, bounds.min), bounds.max - span);
  return { min, max: min + span };
}

function rangeScale(...ranges: PlotRange[]): number {
  return Math.max(
    ...ranges.flatMap((range) => [Math.abs(range.min), Math.abs(range.max)]),
    1,
  );
}

function scaleRange(range: PlotRange, factor: number): PlotRange {
  return { min: range.min * factor, max: range.max * factor };
}

export function zoomPlotRange(
  range: PlotRange,
  anchor: number,
  factor: number,
  bounds: PlotRange,
  minimumSpan = 0,
): PlotRange {
  const span = range.max - range.min,
    extent = bounds.max - bounds.min;
  if (!Number.isFinite(span) || !Number.isFinite(extent)) {
    const scale = rangeScale(range, bounds);
    return scaleRange(
      zoomPlotRange(
        scaleRange(range, 1 / scale),
        anchor / scale,
        factor,
        scaleRange(bounds, 1 / scale),
        minimumSpan / scale,
      ),
      scale,
    );
  }
  const minimum = Math.max(
    minimumSpan,
    extent * 1e-6,
    Number.EPSILON * Math.max(Math.abs(range.min), Math.abs(range.max), 1) * 8,
  );
  const nextSpan = Math.min(extent, Math.max(minimum, span * factor));
  const position = Math.max(0, Math.min(1, plotFraction(anchor, range)));
  const min = anchor - nextSpan * position;
  return fitPlotRange({ min, max: min + nextSpan }, bounds);
}

export function panPlotRange(
  range: PlotRange,
  delta: number,
  bounds: PlotRange,
): PlotRange {
  if (Number.isNaN(delta)) return fitPlotRange(range, bounds);
  if (
    !Number.isFinite(delta) ||
    !Number.isFinite(range.min + delta) ||
    !Number.isFinite(range.max + delta)
  ) {
    const scale = Math.max(
      rangeScale(range, bounds),
      Number.isFinite(delta) ? Math.abs(delta) : 1,
    );
    const scaledBounds = scaleRange(bounds, 1 / scale);
    const scaledDelta = Number.isFinite(delta)
      ? delta / scale
      : Math.sign(delta) * (scaledBounds.max - scaledBounds.min);
    return scaleRange(
      panPlotRange(scaleRange(range, 1 / scale), scaledDelta, scaledBounds),
      scale,
    );
  }
  return fitPlotRange(
    { min: range.min + delta, max: range.max + delta },
    bounds,
  );
}

function goodSample(sample: TrendSample): boolean {
  return !sample.status || sample.status.startsWith("Good");
}

/** A move-only or zero-length segment needs a marker to remain visible. */
export function isolatedTrendSamples(samples: TrendSample[]): TrendSample[] {
  const connected = (
    left: TrendSample | undefined,
    right: TrendSample | undefined,
  ) =>
    !!left &&
    !!right &&
    goodSample(left) &&
    goodSample(right) &&
    !right.breakBefore &&
    (left.time !== right.time || left.value !== right.value);
  return samples.filter(
    (sample, index) =>
      goodSample(sample) &&
      !connected(samples[index - 1], sample) &&
      !connected(sample, samples[index + 1]),
  );
}

function lowerBound(samples: TrendSample[], time: number): number {
  let left = 0,
    right = samples.length;
  while (left < right) {
    const middle = (left + right) >>> 1;
    if (samples[middle].time < time) left = middle + 1;
    else right = middle;
  }
  return left;
}

/** Include the adjacent points so clipped segments still reach both viewport edges. */
export function visibleTrendSamples(
  samples: TrendSample[],
  range: PlotRange,
): TrendSample[] {
  const start = Math.max(0, lowerBound(samples, range.min) - 1);
  let end = lowerBound(samples, range.max);
  while (end < samples.length && samples[end].time === range.max) end++;
  end = Math.min(samples.length, end + 1);
  return samples.slice(start, end);
}

export function nearestTrendSample(
  samples: TrendSample[],
  time: number,
  range: PlotRange,
): TrendSample | null {
  const index = lowerBound(samples, time);
  const candidates = [samples[index - 1], samples[index]].filter(
    (sample): sample is TrendSample =>
      !!sample && sample.time >= range.min && sample.time <= range.max,
  );
  return candidates.reduce<TrendSample | null>(
    (closest, sample) =>
      !closest || Math.abs(sample.time - time) < Math.abs(closest.time - time)
        ? sample
        : closest,
    null,
  );
}

export function trendPath(
  samples: TrendSample[],
  x: (time: number) => number,
  y: (value: number) => number,
): string {
  let previousGood = false;
  return samples
    .map((sample, index) => {
      const good = goodSample(sample);
      const move = !index || sample.breakBefore || !good || !previousGood;
      previousGood = good;
      return `${move ? "M" : "L"}${x(sample.time)},${y(sample.value)}`;
    })
    .join(" ");
}
