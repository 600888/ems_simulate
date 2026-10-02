<template>
  <div v-if="samples.length && extent" class="trend-plot">
    <div class="plot-toolbar">
      <span class="plot-mode">{{
        t(manualViewport ? "opcua.plotInspecting" : "opcua.plotFollowing")
      }}</span>
      <div class="plot-actions">
        <button
          type="button"
          :aria-pressed="!selectionMode"
          @click="selectionMode = false"
        >
          {{ t("opcua.plotPan") }}
        </button>
        <button
          type="button"
          :aria-pressed="selectionMode"
          @click="selectionMode = true"
        >
          {{ t("opcua.plotSelect") }}
        </button>
        <button
          type="button"
          :aria-label="t('opcua.plotZoomIn')"
          :title="t('opcua.plotZoomIn')"
          @click="zoom(0.75)"
        >
          +
        </button>
        <button
          type="button"
          :aria-label="t('opcua.plotZoomOut')"
          :title="t('opcua.plotZoomOut')"
          @click="zoom(1.35)"
        >
          −
        </button>
        <button type="button" @click="resetView">
          {{ t("opcua.plotReset") }}
        </button>
      </div>
    </div>
    <div class="plot-surface">
      <svg
        ref="svg"
        viewBox="0 0 1000 340"
        class="ua-chart interactive-chart"
        :class="{
          dragging: gesture?.kind === 'pan',
          selecting: gesture?.kind === 'select',
        }"
        role="img"
        :aria-label="title"
        :aria-describedby="hintId"
        tabindex="0"
        @wheel="handleWheel"
        @pointermove="handlePointerMove"
        @pointerdown="handlePointerDown"
        @pointerup="handlePointerUp"
        @pointercancel="cancelGesture"
        @lostpointercapture="cancelGesture"
        @pointerleave="pointer = null"
        @dblclick.prevent="resetView"
        @keydown="handleKeyDown"
        @blur="pointer = null"
      >
        <defs>
          <clipPath :id="clipId">
            <rect
              :x="area.left"
              :y="area.top"
              :width="plotWidth"
              :height="plotHeight"
            />
          </clipPath>
        </defs>
        <g v-for="tick in valueTicks" :key="tick.position">
          <line
            :x1="area.left"
            :x2="area.right"
            :y1="tick.position"
            :y2="tick.position"
            class="grid-line"
          />
          <text :x="area.left - 12" :y="tick.position + 4" text-anchor="end">
            {{ numberLabel(tick.value) }}
          </text>
        </g>
        <g v-for="(tick, index) in timeTicks" :key="index">
          <line
            :x1="tick.position"
            :x2="tick.position"
            :y1="area.top"
            :y2="area.bottom"
            class="grid-line"
          />
          <text
            :x="tick.position"
            :y="area.bottom + 23"
            :text-anchor="
              index === 0 ? 'start' : index === 4 ? 'end' : 'middle'
            "
          >
            {{ timeLabel(tick.value) }}
          </text>
        </g>
        <line
          :x1="area.left"
          :x2="area.right"
          :y1="area.bottom"
          :y2="area.bottom"
          class="axis-line"
        />
        <line
          :x1="area.left"
          :x2="area.left"
          :y1="area.top"
          :y2="area.bottom"
          class="axis-line"
        />
        <g :clip-path="`url(#${clipId})`">
          <path :d="path" class="curve" vector-effect="non-scaling-stroke" />
          <circle
            v-for="(sample, index) in isolatedSamples"
            :key="index"
            :cx="x(sample.time)"
            :cy="y(sample.value)"
            r="4"
            fill="var(--ua-primary)"
          />
          <circle
            v-for="(sample, index) in badSamples"
            :key="index"
            :cx="x(sample.time)"
            :cy="y(sample.value)"
            r="3.5"
            class="bad-sample"
          />
          <template v-if="cursor">
            <line
              :x1="cursor.x"
              :x2="cursor.x"
              :y1="area.top"
              :y2="area.bottom"
              class="cursor-line"
            />
            <line
              :x1="area.left"
              :x2="area.right"
              :y1="cursor.y"
              :y2="cursor.y"
              class="cursor-line"
            />
            <circle
              :cx="x(cursor.sample.time)"
              :cy="y(cursor.sample.value)"
              r="5"
              class="cursor-point"
              :class="{ bad: cursor.bad }"
            />
          </template>
          <rect
            v-if="selection"
            :x="selection.x"
            :y="selection.y"
            :width="selection.width"
            :height="selection.height"
            class="selection-box"
          />
        </g>
        <g v-if="cursor" class="cursor-axis-label">
          <rect
            x="3"
            :y="cursor.y - 11"
            :width="area.left - 10"
            height="22"
            rx="3"
          />
          <text :x="area.left - 12" :y="cursor.y + 4" text-anchor="end">
            {{ numberLabel(cursor.value) }}
          </text>
          <rect
            :x="cursor.timeLabelX - 57"
            :y="area.bottom + 9"
            width="114"
            height="23"
            rx="3"
          />
          <text
            :x="cursor.timeLabelX"
            :y="area.bottom + 25"
            text-anchor="middle"
          >
            {{ timeLabel(cursor.time, true) }}
          </text>
        </g>
      </svg>
      <div
        v-if="cursor && !gesture"
        class="plot-tooltip"
        :class="{ 'tooltip-left': cursor.x > 650 }"
        :style="{
          left: `${cursor.x / 10}%`,
          top: `${Math.min(cursor.y, 175) / 3.4}%`,
        }"
        role="status"
      >
        <time
          >{{ t("opcua.plotNearestSample") }} ·
          {{ timestampLabel(cursor.sample.time) }}</time
        >
        <div>
          <span>{{ t("opcua.value") }}</span
          ><strong>{{ numberLabel(cursor.sample.value, 12) }}</strong>
        </div>
        <div v-if="cursor.sample.status">
          <span>{{ t("opcua.plotQuality") }}</span
          ><strong :class="{ 'bad-status': cursor.bad }">{{
            cursor.sample.status
          }}</strong>
        </div>
      </div>
    </div>
    <p :id="hintId" class="plot-hint">{{ t("opcua.plotInteractionHint") }}</p>
  </div>
  <div v-else class="ua-empty">
    <el-empty :image-size="70" :description="t('opcua.noNumericData')" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, useId, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  normalizeTrendSamples,
  trendExtent,
  fitPlotRange,
  zoomPlotRange,
  panPlotRange,
  plotFraction,
  plotValue,
  nearestTrendSample,
  visibleTrendSamples,
  isolatedTrendSamples,
  trendPath,
  type TrendPoint,
  type PlotViewport,
} from "@/utils/opcuaTrendPlot";
const props = defineProps<{
  title: string;
  points: TrendPoint[];
  seriesKey?: string | number;
}>();
const { t, locale } = useI18n();
const id = useId().replace(/[^a-zA-Z0-9_-]/g, "");
const clipId = `ua-plot-clip-${id}`,
  hintId = `ua-plot-hint-${id}`;
const area = { left: 90, right: 980, top: 25, bottom: 280 };
const plotWidth = area.right - area.left,
  plotHeight = area.bottom - area.top;
const svg = ref<SVGSVGElement>();
const samples = computed(() => normalizeTrendSamples(props.points));
const extent = computed(() => trendExtent(samples.value));
const manualViewport = ref<PlotViewport | null>(null);
const viewport = computed(() => {
  const full = extent.value;
  if (!full) return { time: { min: 0, max: 1 }, value: { min: 0, max: 1 } };
  const current = manualViewport.value;
  return current
    ? {
        time: fitPlotRange(current.time, full.time),
        value: fitPlotRange(current.value, full.value),
      }
    : full;
});
const x = (time: number) =>
  area.left + plotFraction(time, viewport.value.time) * plotWidth;
const y = (value: number) =>
  area.bottom - plotFraction(value, viewport.value.value) * plotHeight;
const timeAt = (position: number, view = viewport.value) =>
  plotValue((position - area.left) / plotWidth, view.time);
const valueAt = (position: number, view = viewport.value) =>
  plotValue((area.bottom - position) / plotHeight, view.value);
const visibleSamples = computed(() =>
  visibleTrendSamples(samples.value, viewport.value.time),
);
const badSamples = computed(() =>
  visibleSamples.value.filter(
    (sample) => sample.status && !sample.status.startsWith("Good"),
  ),
);
const path = computed(() => trendPath(visibleSamples.value, x, y));
const isolatedSamples = computed(() =>
  isolatedTrendSamples(visibleSamples.value),
);
const valueTicks = computed(() =>
  Array.from({ length: 5 }, (_, index) => ({
    value: plotValue(index / 4, viewport.value.value),
    position: area.bottom - (index / 4) * plotHeight,
  })),
);
const timeTicks = computed(() =>
  Array.from({ length: 5 }, (_, index) => ({
    value: plotValue(index / 4, viewport.value.time),
    position: area.left + (index / 4) * plotWidth,
  })),
);

type Position = { x: number; y: number };
type Gesture = {
  kind: "pan" | "select";
  pointerId: number;
  origin: Position;
  current: Position;
  view: PlotViewport;
};
const pointer = ref<Position | null>(null);
const gesture = ref<Gesture | null>(null);
const selectionMode = ref(false);
const cursor = computed(() => {
  if (!pointer.value || gesture.value?.kind === "select") return null;
  const time = timeAt(pointer.value.x);
  const sample = nearestTrendSample(samples.value, time, extent.value!.time);
  if (!sample) return null;
  const position = pointer.value.x;
  return {
    sample,
    time,
    value: valueAt(pointer.value.y),
    x: position,
    y: pointer.value.y,
    timeLabelX: Math.max(147, Math.min(923, position)),
    bad: !!sample.status && !sample.status.startsWith("Good"),
  };
});
const selection = computed(() => {
  const drag = gesture.value;
  if (!drag || drag.kind !== "select") return null;
  return {
    x: Math.min(drag.origin.x, drag.current.x),
    y: Math.min(drag.origin.y, drag.current.y),
    width: Math.abs(drag.origin.x - drag.current.x),
    height: Math.abs(drag.origin.y - drag.current.y),
  };
});
function numberLabel(value: number, precision = 5) {
  return Number(value.toPrecision(precision)).toString();
}
function timeLabel(time: number, precise = false) {
  const label = new Intl.DateTimeFormat(locale.value, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    ...(!precise &&
    viewport.value.time.max - viewport.value.time.min >= 86400000
      ? { month: "2-digit", day: "2-digit" }
      : {}),
  }).format(time);
  return precise || viewport.value.time.max - viewport.value.time.min < 10000
    ? `${label}.${String(new Date(time).getMilliseconds()).padStart(3, "0")}`
    : label;
}
function timestampLabel(time: number) {
  const label = new Intl.DateTimeFormat(locale.value, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(time);
  return `${label}.${String(new Date(time).getMilliseconds()).padStart(3, "0")}`;
}
function position(event: {
  clientX: number;
  clientY: number;
}): Position | null {
  const rect = svg.value?.getBoundingClientRect();
  if (!rect?.width || !rect.height) return null;
  return {
    x: ((event.clientX - rect.left) / rect.width) * 1000,
    y: ((event.clientY - rect.top) / rect.height) * 340,
  };
}
function inside(point: Position) {
  return (
    point.x >= area.left &&
    point.x <= area.right &&
    point.y >= area.top &&
    point.y <= area.bottom
  );
}
function clampPosition(point: Position): Position {
  return {
    x: Math.max(area.left, Math.min(area.right, point.x)),
    y: Math.max(area.top, Math.min(area.bottom, point.y)),
  };
}
function resetView() {
  manualViewport.value = null;
  pointer.value = null;
  cancelGesture();
}
function zoom(
  factor: number,
  point?: Position,
  axis: "time" | "value" | "both" = "both",
) {
  const bounds = extent.value;
  if (!bounds) return;
  const current = viewport.value;
  const anchor = point || {
    x: (area.left + area.right) / 2,
    y: (area.top + area.bottom) / 2,
  };
  manualViewport.value = {
    time:
      axis === "value"
        ? current.time
        : zoomPlotRange(current.time, timeAt(anchor.x), factor, bounds.time, 1),
    value:
      axis === "time"
        ? current.value
        : zoomPlotRange(current.value, valueAt(anchor.y), factor, bounds.value),
  };
}
function handleWheel(event: WheelEvent) {
  const point = position(event);
  if (!point || !inside(point) || gesture.value) return;
  event.preventDefault();
  const delta =
    event.deltaY *
    (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 340 : 1);
  zoom(
    Math.exp(Math.max(-200, Math.min(200, delta)) * 0.003),
    point,
    event.shiftKey ? "value" : "time",
  );
  pointer.value = point;
}
function handlePointerDown(event: PointerEvent) {
  if (event.button !== 0 || !event.isPrimary || gesture.value) return;
  const point = position(event);
  if (!point || !inside(point)) return;
  event.preventDefault();
  svg.value?.focus({ preventScroll: true });
  svg.value?.setPointerCapture(event.pointerId);
  gesture.value = {
    kind: event.shiftKey || selectionMode.value ? "select" : "pan",
    pointerId: event.pointerId,
    origin: point,
    current: point,
    view: viewport.value,
  };
  pointer.value = point;
}
function handlePointerMove(event: PointerEvent) {
  const point = position(event);
  if (!point) return;
  pointer.value = inside(point) ? point : null;
  const drag = gesture.value,
    bounds = extent.value;
  if (!drag || drag.pointerId !== event.pointerId || !bounds) return;
  drag.current = clampPosition(point);
  if (
    drag.kind === "pan" &&
    (Math.abs(point.x - drag.origin.x) > 2 ||
      Math.abs(point.y - drag.origin.y) > 2)
  ) {
    manualViewport.value = {
      time: panPlotRange(
        drag.view.time,
        timeAt(drag.origin.x, drag.view) - timeAt(point.x, drag.view),
        bounds.time,
      ),
      value: panPlotRange(
        drag.view.value,
        valueAt(drag.origin.y, drag.view) - valueAt(point.y, drag.view),
        bounds.value,
      ),
    };
  }
}
function handlePointerUp(event: PointerEvent) {
  const drag = gesture.value,
    box = selection.value,
    bounds = extent.value;
  if (!drag || drag.pointerId !== event.pointerId) return;
  if (box && box.width > 6 && box.height > 6 && bounds) {
    manualViewport.value = {
      time: fitPlotRange(
        {
          min: timeAt(box.x, drag.view),
          max: timeAt(box.x + box.width, drag.view),
        },
        bounds.time,
      ),
      value: fitPlotRange(
        {
          min: valueAt(box.y + box.height, drag.view),
          max: valueAt(box.y, drag.view),
        },
        bounds.value,
      ),
    };
  }
  cancelGesture();
}
function cancelGesture() {
  const pointerId = gesture.value?.pointerId;
  gesture.value = null;
  if (pointerId !== undefined && svg.value?.hasPointerCapture(pointerId))
    svg.value.releasePointerCapture(pointerId);
}
function handleKeyDown(event: KeyboardEvent) {
  if (
    [
      "+",
      "=",
      "-",
      "_",
      "0",
      "Home",
      "Escape",
      "ArrowLeft",
      "ArrowRight",
      "ArrowUp",
      "ArrowDown",
    ].includes(event.key)
  )
    event.preventDefault();
  if (event.key === "+" || event.key === "=") zoom(0.75);
  else if (event.key === "-" || event.key === "_") zoom(1.35);
  else if (event.key === "0" || event.key === "Home") resetView();
  else if (event.key === "Escape") {
    cancelGesture();
    pointer.value = null;
  } else if (event.key.startsWith("Arrow") && extent.value) {
    const current = viewport.value;
    manualViewport.value = {
      time: panPlotRange(
        current.time,
        (event.key === "ArrowLeft"
          ? -0.1
          : event.key === "ArrowRight"
            ? 0.1
            : 0) *
          (current.time.max - current.time.min),
        extent.value.time,
      ),
      value: panPlotRange(
        current.value,
        (event.key === "ArrowDown" ? -0.1 : event.key === "ArrowUp" ? 0.1 : 0) *
          (current.value.max - current.value.min),
        extent.value.value,
      ),
    };
    pointer.value = null;
  }
}
watch(() => props.seriesKey ?? props.title, resetView);
watch(
  () => samples.value.length === 0,
  (empty) => {
    if (empty) resetView();
  },
);
</script>

<style scoped>
.trend-plot {
  min-width: 0;
}
.plot-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.plot-mode,
.plot-hint {
  color: var(--ua-muted);
  font-size: 12px;
}
.plot-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.plot-actions button {
  color: var(--ua-text);
  background: var(--ua-surface);
  border: 1px solid var(--ua-line);
  border-radius: 5px;
  min-width: 32px;
  height: 30px;
  padding: 0 10px;
  cursor: pointer;
}
.plot-actions button:hover,
.plot-actions button[aria-pressed="true"] {
  color: var(--ua-primary);
  border-color: var(--ua-primary);
}
.plot-surface {
  position: relative;
  border: 1px solid var(--ua-line);
  border-radius: 7px;
  overflow: hidden;
}
.interactive-chart {
  display: block;
  width: 100%;
  height: auto;
  aspect-ratio: 1000 / 340;
  touch-action: none;
  user-select: none;
  cursor: crosshair;
}
.interactive-chart:focus-visible {
  outline: 2px solid var(--ua-primary);
  outline-offset: -2px;
}
.interactive-chart.dragging {
  cursor: grabbing;
}
.interactive-chart.selecting {
  cursor: crosshair;
}
.axis-line {
  stroke: var(--ua-muted);
  stroke-width: 1;
}
.cursor-line {
  stroke: var(--ua-primary);
  stroke-width: 1;
  stroke-dasharray: 5 4;
  vector-effect: non-scaling-stroke;
  pointer-events: none;
}
.cursor-point {
  fill: var(--ua-surface);
  stroke: var(--ua-primary);
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}
.cursor-point.bad,
.bad-sample {
  stroke: var(--el-color-danger, #f56c6c);
  fill: var(--el-color-danger, #f56c6c);
}
.selection-box {
  fill: color-mix(in srgb, var(--ua-primary) 16%, transparent);
  stroke: var(--ua-primary);
  stroke-width: 1;
  stroke-dasharray: 4 3;
}
.cursor-axis-label rect {
  fill: var(--ua-primary);
}
.interactive-chart .cursor-axis-label text {
  fill: #fff;
  font-size: 11px;
}
.plot-tooltip {
  position: absolute;
  z-index: 1;
  pointer-events: none;
  transform: translate(12px, -10%);
  background: var(--ua-surface);
  border: 1px solid var(--ua-line);
  color: var(--ua-text);
  box-shadow: 0 4px 14px #0002;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 12px;
  max-width: min(260px, 60%);
}
.plot-tooltip.tooltip-left {
  transform: translate(calc(-100% - 12px), -10%);
}
.plot-tooltip time {
  color: var(--ua-muted);
  font-variant-numeric: tabular-nums;
  display: block;
  line-height: 1.5;
}
.plot-tooltip > div {
  display: flex;
  gap: 16px;
  justify-content: space-between;
  margin-top: 5px;
}
.plot-tooltip strong {
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.plot-tooltip .bad-status {
  color: var(--el-color-danger, #f56c6c);
}
.plot-hint {
  margin: 8px 0 0;
  line-height: 1.6;
}
</style>
