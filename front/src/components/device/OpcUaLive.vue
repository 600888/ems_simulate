<template>
  <div>
    <div v-if="mode === 'events'" class="ua-metrics event-metrics">
      <div class="ua-metric">
        <span>{{ t("opcua.receivedEvents") }}</span
        ><strong>{{ eventCount }}</strong>
      </div>
      <div class="ua-metric">
        <span>{{ t("opcua.highSeverity") }}</span
        ><strong class="ua-danger">{{ severeCount }}</strong>
      </div>
      <div class="ua-metric">
        <span>{{ t("opcua.connectionStatus") }}</span
        ><strong :class="connection === 'connected' ? 'ua-good' : 'ua-muted'">{{
          connectionLabel
        }}</strong>
      </div>
    </div>
    <section class="ua-section">
      <div class="ua-toolbar live-toolbar">
        <el-select
          v-if="mode === 'trend'"
          v-model="selected"
          :placeholder="t('opcua.targetNode')"
          class="curve-select"
          filterable
          ><el-option
            v-for="node in available"
            :key="node"
            :label="node"
            :value="node"
        /></el-select>
        <template v-else>
          <el-input
            v-model="eventFilter"
            :placeholder="t('opcua.eventSearch')"
            clearable
          />
          <el-select
            v-model="severityFilter"
            :placeholder="t('opcua.severity')"
            clearable
            ><el-option
              :label="t('opcua.allSeverities')"
              :value="0" /><el-option
              :label="t('opcua.highSeverity')"
              :value="500"
          /></el-select>
        </template>
        <el-button @click="paused = !paused">{{
          t(paused ? "opcua.resume" : "opcua.pause")
        }}</el-button>
        <el-button @click="clear">{{ t("opcua.clearView") }}</el-button>
        <el-button @click="exportCsv">{{ t("opcua.exportCsv") }}</el-button>
        <el-tag
          :type="connection === 'connected' ? 'success' : 'info'"
          effect="light"
          >{{ connectionLabel }}</el-tag
        >
      </div>
    </section>
    <el-alert
      v-if="gap"
      type="warning"
      :closable="false"
      :title="t('opcua.streamGap')"
    />
    <template v-if="mode === 'trend'">
      <div class="ua-metrics">
        <div class="ua-metric">
          <span>{{ t("opcua.lastValue") }}</span
          ><strong>{{ displayMetric(latest?.value) }}</strong
          ><small class="ua-code">{{ selected || "—" }}</small>
        </div>
        <div class="ua-metric">
          <span>{{ t("opcua.minimum") }}</span
          ><strong>{{ numeric.length ? displayMetric(min) : "—" }}</strong>
        </div>
        <div class="ua-metric">
          <span>{{ t("opcua.maximum") }}</span
          ><strong>{{ numeric.length ? displayMetric(max) : "—" }}</strong>
        </div>
        <div class="ua-metric">
          <span>{{ t("opcua.sampleCount") }}</span
          ><strong>{{ numeric.length }}</strong>
        </div>
      </div>
      <section class="ua-section">
        <div class="ua-section-heading">
          <h3>{{ t("opcua.trend") }}</h3>
          <span class="ua-code">{{ selected }}</span>
        </div>
        <OpcUaTrendPlot
          :title="t('opcua.trend')"
          :points="chartPoints"
          :series-key="`${channelId}:${selected}`"
        />
      </section>
    </template>
    <el-table
      :data="shown"
      max-height="350"
      stripe
      highlight-current-row
      @row-click="selectedEvent = $event"
    >
      <el-table-column :label="t('opcua.sourceTimestamp')" min-width="225"
        ><template #default="{ row }">{{
          formatBeijingDateTime(row.source_timestamp || row.timestamp)
        }}</template></el-table-column
      >
      <template v-if="mode === 'events'">
        <el-table-column
          prop="SourceName"
          :label="t('opcua.eventSource')"
          min-width="150"
          show-overflow-tooltip
        />
        <el-table-column :label="t('opcua.severity')" width="100"
          ><template #default="{ row }"
            ><span
              :class="Number(row.Severity) >= 500 ? 'ua-danger' : 'ua-warning'"
              >{{ row.Severity }}</span
            ></template
          ></el-table-column
        >
        <el-table-column
          prop="Message"
          :label="t('opcua.eventMessage')"
          min-width="260"
          show-overflow-tooltip
        />
      </template>
      <template v-else>
        <el-table-column
          prop="node_id"
          label="NodeId"
          min-width="230"
          show-overflow-tooltip
        />
        <el-table-column
          :label="t('opcua.value')"
          min-width="130"
          show-overflow-tooltip
          ><template #default="{ row }">{{
            displayValue(row.value)
          }}</template></el-table-column
        >
        <el-table-column :label="t('opcua.quality')" width="180"
          ><template #default="{ row }"
            ><span
              :class="
                row.status_code?.startsWith('Good') ? 'ua-good' : 'ua-warning'
              "
              >{{ row.status_code }}</span
            ></template
          ></el-table-column
        >
      </template>
    </el-table>
    <section
      v-if="mode === 'events' && selectedEvent"
      class="ua-section event-detail"
    >
      <div class="ua-section-heading">
        <h3>{{ t("opcua.eventDetails") }}</h3>
        <span>{{
          formatBeijingDateTime(selectedEvent.Time || selectedEvent.timestamp)
        }}</span>
      </div>
      <p class="ua-muted">
        {{ selectedEvent.SourceName }} · {{ t("opcua.severity") }}
        {{ selectedEvent.Severity }} · {{ selectedEvent.EventId }}
      </p>
      <p class="event-message">{{ selectedEvent.Message }}</p>
    </section>
    <p class="ua-note success live-note">
      {{ paused ? t("opcua.viewPaused") : t("opcua.liveHint") }}
    </p>
  </div>
</template>
<script setup lang="ts">
import { formatBeijingDateTime } from "@/utils/opcuaTime";
import OpcUaTrendPlot from "./OpcUaTrendPlot.vue";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { readOpcUaStream } from "@/api/opcuaApi";
import type { OpcUaStreamEvent } from "@/api/opcuaApi";

const props = defineProps<{ channelId: number; mode: "trend" | "events" }>();
const { t, locale } = useI18n();
const records = ref<OpcUaStreamEvent[]>([]);
const paused = ref(false);
const gap = ref(false);
const connection = ref("-");
const selected = ref("");
let after = 0;
let stopped = false;
let epoch = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
const available = computed(() => [
  ...new Set(
    records.value
      .filter((e) => e.kind === "value" && typeof e.value === "number")
      .map((e) => e.node_id as string),
  ),
]);
const visible = computed(() =>
  records.value
    .filter((e) =>
      props.mode === "events"
        ? e.kind === "event"
        : e.kind === "value" &&
          (!selected.value || e.node_id === selected.value),
    )
    .slice(-300)
    .reverse(),
);
const numeric = computed(() =>
  records.value.filter(
    (e) =>
      e.kind === "value" &&
      e.node_id === selected.value &&
      typeof e.value === "number",
  ),
);
const min = computed(() =>
  Math.min(...numeric.value.map((e) => e.value as number)),
);
const max = computed(() =>
  Math.max(...numeric.value.map((e) => e.value as number)),
);
const chartPoints = computed(() => {
  let previous = -1;
  let interrupted = false;
  const points: {
    timestamp: string;
    value: unknown;
    status?: string;
    breakBefore: boolean;
  }[] = [];
  for (const event of records.value) {
    if (event.kind === "connection" && event.state === "disconnected")
      interrupted = true;
    if (event.kind !== "value" || event.node_id !== selected.value) continue;
    const numericValue =
      typeof event.value === "number" && Number.isFinite(event.value);
    points.push({
      timestamp: event.source_timestamp || event.timestamp,
      value: event.value,
      status: event.status_code,
      breakBefore: interrupted || previous < 0,
    });
    interrupted = !numericValue;
    previous = event.sequence;
  }
  return points;
});
const eventFilter = ref("");
const severityFilter = ref<number | null>(null);
const shown = computed(() =>
  visible.value.filter(
    (e) =>
      props.mode !== "events" ||
      ((!severityFilter.value || Number(e.Severity) >= severityFilter.value) &&
        `${e.Message || ""} ${e.SourceName || ""} ${e.EventId || ""}`
          .toLowerCase()
          .includes(eventFilter.value.toLowerCase())),
  ),
);
const eventCount = computed(
  () => records.value.filter((e) => e.kind === "event").length,
);
const severeCount = computed(
  () =>
    records.value.filter((e) => e.kind === "event" && Number(e.Severity) >= 500)
      .length,
);
const latest = computed(() => numeric.value[numeric.value.length - 1]);
const selectedEvent = ref<OpcUaStreamEvent | null>(null);
const connectionLabel = computed(() =>
  connection.value === "connected"
    ? t("opcua.connected")
    : connection.value === "disconnected"
      ? t("opcua.disconnected")
      : connection.value,
);
function displayValue(value: unknown) {
  return typeof value === "object"
    ? JSON.stringify(value)
    : String(value ?? "—");
}
function displayMetric(value: unknown) {
  return typeof value === "number"
    ? new Intl.NumberFormat(locale.value, { maximumFractionDigits: 4 }).format(
        value,
      )
    : displayValue(value);
}

async function poll() {
  const generation = epoch;
  try {
    const page = await readOpcUaStream(props.channelId, after);
    if (stopped || generation !== epoch) return;
    if (page.latest_sequence < after) {
      after = 0;
      gap.value = true;
      return;
    }
    gap.value ||= page.gap;
    if (page.events.length)
      after = page.events[page.events.length - 1].sequence;
    for (const event of page.events) {
      if (event.kind === "connection") connection.value = event.state || "-";
      if (!paused.value) records.value.push(event);
    }
    records.value = records.value.slice(-2000);
    if (!selected.value && available.value.length)
      selected.value = available.value[0];
  } catch {
    connection.value = t("opcua.notRunning");
  } finally {
    if (!stopped && generation === epoch) timer = setTimeout(poll, 500);
  }
}
function clear() {
  records.value = [];
  selectedEvent.value = null;
  gap.value = false;
}
function exportCsv() {
  const rows = shown.value
    .slice()
    .reverse()
    .map((e) => [
      e.source_timestamp || e.timestamp,
      e.node_id || e.SourceName,
      e.value ?? e.Message,
      e.status_code || e.Severity,
    ]);
  const csv = [
    "time,node,value_or_message,quality_or_severity",
    ...rows.map((row) =>
      row.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(","),
    ),
  ].join("\r\n");
  const url = URL.createObjectURL(
    new Blob(["\uFEFF", csv], { type: "text/csv" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = `opcua-${props.mode}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}
onMounted(poll);
watch(
  () => props.channelId,
  () => {
    epoch++;
    clearTimeout(timer);
    after = 0;
    clear();
    void poll();
  },
);
onBeforeUnmount(() => {
  stopped = true;
  epoch++;
  clearTimeout(timer);
});
</script>

<style scoped>
.live-toolbar {
  margin-bottom: 0;
}
.live-toolbar .curve-select {
  flex: 1 1 260px;
  width: auto;
  min-width: 0;
  max-width: 420px;
}
.event-metrics {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.event-detail,
.live-note {
  margin-top: 16px;
}
.event-message {
  margin-top: 12px;
  line-height: 22px;
  overflow-wrap: anywhere;
}
.event-detail .ua-muted {
  overflow-wrap: anywhere;
}
</style>
