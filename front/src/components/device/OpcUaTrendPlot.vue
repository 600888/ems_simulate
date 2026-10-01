<template>
  <svg
    v-if="samples.length"
    viewBox="0 0 1000 290"
    class="ua-chart"
    role="img"
    :aria-label="title"
  >
    <g v-for="tick in ticks" :key="tick.y">
      <line x1="65" x2="975" :y1="tick.y" :y2="tick.y" class="grid-line" />
      <text x="52" :y="tick.y + 4" text-anchor="end">{{ tick.label }}</text>
    </g>
    <path :d="path" class="curve" />
    <circle
      v-if="samples.length === 1"
      :cx="65"
      :cy="y(samples[0].value)"
      r="3"
      fill="var(--ua-primary)"
    />
    <text x="65" y="280">{{ timeLabel(samples[0].time) }}</text>
    <text x="975" y="280" text-anchor="end">
      {{ timeLabel(samples[samples.length - 1].time) }}
    </text>
  </svg>
  <div v-else class="ua-empty">
    <el-empty :image-size="70" :description="t('opcua.noNumericData')" />
  </div>
</template>
<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
const props = defineProps<{
  title: string;
  points: {
    timestamp: string | null | undefined;
    value: unknown;
    status?: string;
    breakBefore?: boolean;
  }[];
}>();
const { t } = useI18n();
const samples = computed(() =>
  props.points
    .map((point) => ({
      ...point,
      time: Date.parse(point.timestamp || ""),
    }))
    .filter(
      (point): point is typeof point & { value: number } =>
        typeof point.value === "number" &&
        Number.isFinite(point.value) &&
        Number.isFinite(point.time),
    ),
);
const limits = computed(() => {
  const values = samples.value.map((p) => p.value);
  const min = Math.min(...values),
    max = Math.max(...values);
  const padding = (max - min) * 0.1 || Math.max(Math.abs(max) * 0.1, 1);
  return { min: min - padding, max: max + padding };
});
const y = (value: number) =>
  245 -
  ((value - limits.value.min) / (limits.value.max - limits.value.min)) * 220;
const ticks = computed(() =>
  Array.from({ length: 5 }, (_, i) => {
    const value =
      limits.value.min + ((limits.value.max - limits.value.min) * i) / 4;
    return { y: y(value), label: Number(value.toPrecision(4)).toString() };
  }),
);
const path = computed(() => {
  const points = samples.value;
  if (!points.length) return "";
  const first = points[0].time,
    span = Math.max(1, points[points.length - 1].time - first);
  let previousGood = false;
  return points
    .map((p, i) => {
      const good = !p.status || p.status.startsWith("Good");
      const move = !i || p.breakBefore || !good || !previousGood;
      previousGood = good;
      return `${move ? "M" : "L"}${65 + ((p.time - first) / span) * 910},${y(p.value)}`;
    })
    .join(" ");
});
function timeLabel(time: number) {
  return new Date(time).toLocaleTimeString();
}
</script>
