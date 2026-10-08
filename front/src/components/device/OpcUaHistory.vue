<template>
  <div>
    <OpcUaPageHeading
      :title="t('opcua.history')"
      :description="
        t(
          role === 'server'
            ? 'opcua.historyServerDescription'
            : 'opcua.historyDescription',
        )
      "
    />
    <template v-if="role === 'server'">
      <el-alert
        v-if="running"
        :title="t('opcua.liveConfigHint')"
        type="info"
        :closable="false"
      />
      <section class="ua-section">
        <div class="ua-section-heading">
          <h3>{{ t("opcua.historyStorage") }}</h3>
          <el-switch
            v-model="config.enabled"
            :disabled="saving"
            :active-text="t('opcua.enabled')"
          />
        </div>
        <el-form label-position="top" class="ua-form-grid" :disabled="saving">
          <el-form-item :label="t('opcua.historyNodes')" class="ua-span-all"
            ><el-select
              v-model="config.nodes"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              :max-collapse-tags="3"
              ><el-option
                v-for="node in nodes"
                :key="node.node_id"
                :label="node.browse_name + ' · ' + node.node_id"
                :value="node.node_id" /></el-select
          ></el-form-item>
          <el-form-item :label="t('opcua.retentionDays')"
            ><el-input-number
              v-model="config.retention_days"
              :min="1"
              :controls="false"
          /></el-form-item>
          <el-form-item :label="t('opcua.maxValues')"
            ><el-input-number
              v-model="config.max_values"
              :min="1"
              :controls="false"
          /></el-form-item>
        </el-form>
        <div class="ua-form-footer">
          <el-button :loading="saving" type="primary" @click="save">{{
            t("opcua.saveConfig")
          }}</el-button>
        </div>
      </section>
    </template>
    <template v-else>
      <section class="ua-section">
        <div class="ua-section-heading">
          <h3>{{ t("opcua.queryConditions") }}</h3>
        </div>
        <el-form label-position="top" class="history-query">
          <el-form-item label="NodeId"
            ><el-input v-model="nodeId" placeholder="ns=2;s=..."
          /></el-form-item>
          <el-form-item :label="t('opcua.timeRange')"
            ><el-date-picker
              v-model="range"
              type="datetimerange"
              value-format="YYYY-MM-DD HH:mm:ss"
              popper-class="opcua-history-range-popper"
              :start-placeholder="t('opcua.startTime')"
              :end-placeholder="t('opcua.endTime')"
          /></el-form-item>
        </el-form>
        <div class="ua-form-footer">
          <el-button
            :disabled="!running"
            :loading="busy"
            type="primary"
            @click="query(false)"
            >{{ t("opcua.readHistory") }}</el-button
          ><el-button
            :disabled="!continuation || !running"
            :loading="busy"
            @click="query(true)"
            >{{ t("opcua.nextPage") }}</el-button
          ><el-button :disabled="!values.length" @click="exportCsv">{{
            t("opcua.exportCsv")
          }}</el-button>
        </div>
      </section>
      <section class="ua-section">
        <div class="ua-section-heading">
          <h3>{{ t("opcua.historyTrend") }}</h3>
          <span class="ua-code">{{ nodeId }}</span>
        </div>
        <OpcUaTrendPlot
          :title="t('opcua.historyTrend')"
          :points="chartPoints"
          :series-key="`${channelId}:${nodeId}`"
        />
      </section>
      <el-table :data="values" stripe max-height="380">
        <el-table-column
          prop="source_timestamp"
          :label="t('opcua.sourceTimestamp')"
          min-width="240"
        >
          <template #default="{ row }">{{
            formatBeijingDateTime(row.source_timestamp)
          }}</template>
        </el-table-column>
        <el-table-column
          :label="t('opcua.value')"
          min-width="160"
          show-overflow-tooltip
          ><template #default="{ row }">{{
            displayValue(row.value)
          }}</template></el-table-column
        >
        <el-table-column :label="t('opcua.quality')" min-width="180"
          ><template #default="{ row }"
            ><span
              :class="
                row.status_code?.startsWith('Good') ? 'ua-good' : 'ua-warning'
              "
              >{{ row.status_code }}</span
            ></template
          ></el-table-column
        >
        <el-table-column
          prop="variant_type"
          :label="t('opcua.dataType')"
          width="130"
        />
      </el-table>
      <p class="ua-note success history-note">
        {{ t("opcua.historyReturned", { count: values.length }) }}
      </p>
    </template>
  </div>
</template>
<script setup lang="ts">
import {
  formatBeijingDateTime,
  defaultBeijingTimeRange,
  beijingDateTimeToISOString,
} from "@/utils/opcuaTime";
import OpcUaPageHeading from "./OpcUaPageHeading.vue";
import OpcUaTrendPlot from "./OpcUaTrendPlot.vue";
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import {
  getOpcUaFeatures,
  listOpcUaVariables,
  saveOpcUaFeature,
  readOpcUaHistory,
} from "@/api/opcuaApi";
import type { OpcUaValueSnapshot, OpcUaVariable } from "@/api/opcuaApi";
import { showError } from "@/api/http";
const props = defineProps<{
  channelId: number;
  role: "client" | "server";
  running: boolean;
  revision?: number;
}>();
const { t } = useI18n();
const config = ref({
  enabled: false,
  nodes: [] as string[],
  retention_days: 7,
  max_values: 100000,
});
const nodes = ref<OpcUaVariable[]>([]),
  values = ref<OpcUaValueSnapshot[]>([]),
  nodeId = ref("ns=2;s=");
const range = ref<[string, string]>(defaultBeijingTimeRange()),
  busy = ref(false),
  continuation = ref<string | null>(null);
const chartPoints = computed(() =>
  values.value
    .slice()
    .sort(
      (a, b) =>
        Date.parse(a.source_timestamp || "") -
        Date.parse(b.source_timestamp || ""),
    )
    .map((row) => ({
      timestamp: row.source_timestamp,
      value: row.value,
      status: row.status_code,
    })),
);
function displayValue(value: unknown) {
  return typeof value === "object"
    ? JSON.stringify(value)
    : String(value ?? "—");
}
let original: { node: string; start: string; end: string } | null = null;
async function load() {
  if (props.role !== "server") return;
  try {
    config.value = {
      ...config.value,
      ...(await getOpcUaFeatures(props.channelId)).history,
    };
    nodes.value = (await listOpcUaVariables(props.channelId)).nodes;
  } catch (e) {
    showError(e);
  }
}
const saving = ref(false);
async function save() {
  saving.value = true;
  try {
    await saveOpcUaFeature(props.channelId, "history", config.value);
    ElMessage.success(t("opcua.configSaved"));
  } catch (e) {
    showError(e);
  } finally {
    saving.value = false;
  }
}
async function query(next: boolean) {
  busy.value = true;
  try {
    if (!next) {
      if (!range.value) throw new Error(t("opcua.chooseRange"));
      original = {
        node: nodeId.value,
        start: beijingDateTimeToISOString(range.value[0]),
        end: beijingDateTimeToISOString(range.value[1]),
      };
      continuation.value = null;
      values.value = [];
    }
    if (!original) return;
    const result = await readOpcUaHistory(
      props.channelId,
      original.node,
      original.start,
      original.end,
      continuation.value,
    );
    values.value = [...values.value, ...result.values].slice(-10000);
    continuation.value = result.continuation;
  } catch (e) {
    showError(e);
  } finally {
    busy.value = false;
  }
}
function exportCsv() {
  const csv = [
    "time,value,quality",
    ...values.value.map((row) =>
      [row.source_timestamp, JSON.stringify(row.value), row.status_code]
        .map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`)
        .join(","),
    ),
  ].join("\r\n");
  const url = URL.createObjectURL(
    new Blob(["\uFEFF", csv], { type: "text/csv" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "opcua-history.csv";
  link.click();
  URL.revokeObjectURL(url);
}
onMounted(load);
watch(
  () => props.revision,
  async () => {
    if (props.role !== "server") return;
    try {
      nodes.value = (await listOpcUaVariables(props.channelId)).nodes;
      const existing = new Set(nodes.value.map((node) => node.node_id));
      config.value.nodes = config.value.nodes.filter((id) => existing.has(id));
    } catch (e) {
      showError(e);
    }
  },
);
watch(
  () => props.channelId,
  () => {
    original = null;
    continuation.value = null;
    values.value = [];
    void load();
  },
);
</script>
<style scoped>
.history-query {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) minmax(0, 2fr);
  gap: 18px;
}
.history-query :deep(.el-form-item),
.history-query :deep(.el-form-item__content) {
  min-width: 0;
}
.history-query :deep(.el-date-editor) {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
}
.history-query :deep(.el-form-item__label) {
  color: var(--ua-muted);
  font-size: 12px;
}
.history-note {
  margin-top: 16px;
}
@container (max-width: 800px) {
  .history-query {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }
}
</style>

<style>
.opcua-history-range-popper .el-date-range-picker {
  width: min(646px, calc(100vw - 24px));
  max-height: calc(100vh - 24px);
  max-height: calc(100dvh - 24px);
  overflow: auto;
}
.opcua-history-range-popper .el-picker-panel__body {
  min-width: 0;
}
.opcua-history-range-popper .el-picker-panel__footer {
  position: sticky;
  bottom: 0;
  z-index: 2;
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}
.opcua-history-range-popper .el-picker-panel__footer .el-button + .el-button {
  margin-left: 0;
}
@media (max-width: 680px) {
  .opcua-history-range-popper .el-date-range-picker__content {
    display: block;
    width: 100%;
    padding: 12px;
  }
  .opcua-history-range-popper .el-date-range-picker__content.is-left {
    border-right: 0;
    border-bottom: 1px solid var(--el-datepicker-inner-border-color);
  }
  .opcua-history-range-popper .el-date-range-picker__time-header {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 12px;
  }
  .opcua-history-range-popper .el-date-range-picker__editors-wrap {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    width: 100%;
    text-align: left;
  }
  .opcua-history-range-popper
    .el-date-range-picker__time-header
    > span:not(.el-date-range-picker__editors-wrap) {
    align-self: center;
    line-height: 16px;
    transform: rotate(90deg);
  }
  .opcua-history-range-popper .el-date-range-picker__time-picker-wrap {
    display: block;
    min-width: 0;
    padding: 0;
  }
  .opcua-history-range-popper
    .el-date-range-picker__time-picker-wrap
    .el-time-panel {
    left: auto;
    right: 0;
    max-width: calc(100vw - 48px);
  }
}
</style>
