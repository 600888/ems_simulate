<template>
  <div class="ua-history-workspace">
    <section v-if="role === 'server'" class="ua-section">
      <div class="ua-section-heading">
        <h3>{{ t("opcua.historyStorage") }}</h3>
      </div>
      <el-form label-position="top" class="history-options">
        <el-form-item :label="t('opcua.retentionDays')"
          ><el-input-number
            v-model="storage.retention_days"
            :min="1"
            :max="3650"
        /></el-form-item>
        <el-form-item :label="t('opcua.maxValues')"
          ><el-input-number
            v-model="storage.max_values"
            :min="1"
            :max="10000000"
        /></el-form-item>
      </el-form>
      <p class="ua-muted">{{ t("opcua.historyStorageHint") }}</p>
      <div class="ua-toolbar">
        <el-button :loading="saving" @click="saveStorage(false)">{{
          t("opcua.saveConfig")
        }}</el-button
        ><el-button
          type="primary"
          :loading="saving"
          :disabled="!nodes.length"
          @click="saveStorage(true)"
          >{{ t("opcua.startHistory") }}</el-button
        ><el-button
          :disabled="!storage.enabled"
          :loading="saving"
          @click="stopStorage"
          >{{ t("opcua.stop") }}</el-button
        ><el-tag :type="storage.enabled ? 'success' : 'info'">{{
          t(storage.enabled ? "opcua.enabled" : "opcua.disabled")
        }}</el-tag>
      </div>
    </section>
    <template v-else>
      <section class="ua-section">
        <div class="ua-section-heading">
          <h3>{{ t("opcua.historyQuery") }}</h3>
        </div>
        <el-form label-position="top" class="history-options">
          <el-form-item class="range" :label="t('opcua.timeRange')"
            ><el-date-picker
              v-model="range"
              type="datetimerange"
              :start-placeholder="t('opcua.startTime')"
              :end-placeholder="t('opcua.endTime')"
          /></el-form-item>
          <el-form-item :label="t('opcua.readMode')"
            ><el-select v-model="options.mode"
              ><el-option value="raw" :label="t('opcua.rawValues')" /><el-option
                value="processed"
                :label="t('opcua.aggregateValues')" /></el-select
          ></el-form-item>
          <el-form-item :label="t('opcua.resultLimit')"
            ><el-input-number v-model="options.limit" :min="1" :max="500"
          /></el-form-item>
          <el-form-item
            v-if="options.mode === 'processed'"
            :label="t('opcua.aggregateFunction')"
            ><el-select v-model="options.aggregate"
              ><el-option
                v-for="name in aggregates"
                :key="name"
                :value="name"
                :label="name" /></el-select
          ></el-form-item>
          <el-form-item
            v-if="options.mode === 'processed'"
            :label="t('opcua.processingInterval')"
            ><el-input-number
              v-model="options.processing_interval_ms"
              :min="50"
              :max="3600000"
          /></el-form-item>
          <el-form-item :label="t('opcua.timestamps')"
            ><el-select v-model="options.timestamps"
              ><el-option
                v-for="name in ['Source', 'Server', 'Both', 'Neither']"
                :key="name"
                :value="name"
                :label="t(`opcua.timestamp${name}`)" /></el-select
          ></el-form-item>
          <el-form-item
            v-if="options.mode === 'raw'"
            :label="t('opcua.returnBounds')"
            ><el-switch v-model="options.return_bounds"
          /></el-form-item>
        </el-form>
        <el-alert
          v-if="options.mode === 'processed'"
          type="info"
          :title="t('opcua.aggregateServerHint')"
          :closable="false"
        />
        <div class="ua-toolbar">
          <el-button
            type="primary"
            :loading="busy"
            :disabled="!running || !nodes.length"
            @click="query(false)"
            >{{ t("opcua.query") }}</el-button
          ><el-button
            :loading="busy"
            :disabled="!running || !hasMore || capped"
            @click="query(true)"
            >{{ t("opcua.nextPage") }}</el-button
          ><el-button :disabled="!values.length" @click="exportCsv">{{
            t("opcua.exportCsv")
          }}</el-button
          ><span class="ua-muted">{{
            t("opcua.receivedRecords", { count: values.length })
          }}</span>
        </div>
        <el-alert
          v-if="capped"
          type="warning"
          :title="t('opcua.historyResultCap')"
          :closable="false"
        />
        <el-alert
          v-for="(error, id) in errors"
          :key="id"
          type="error"
          :title="`${id}: ${error}`"
          :closable="false"
        />
      </section>
      <section class="ua-section">
        <div class="ua-section-heading">
          <h3>{{ t("opcua.queryResults") }}</h3>
          <el-radio-group v-model="view" size="small"
            ><el-radio-button value="table">{{
              t("opcua.tableView")
            }}</el-radio-button
            ><el-radio-button value="trend">{{
              t("opcua.trend")
            }}</el-radio-button></el-radio-group
          >
        </div>
        <template v-if="view === 'trend'"
          ><el-select v-model="chartNode"
            ><el-option
              v-for="node in nodes"
              :key="node.node_id"
              :value="node.node_id"
              :label="node.browse_name" /></el-select
          ><OpcUaTrendPlot
            :title="chartNode"
            :points="chartPoints"
            :series-key="`${channelId}:${chartNode}`"
        /></template>
        <el-table
          v-else
          :data="values"
          stripe
          max-height="430"
          :empty-text="t('opcua.noHistory')"
        >
          <el-table-column
            prop="node_id"
            label="NodeId"
            min-width="190"
            show-overflow-tooltip
          />
          <el-table-column
            :label="t('opcua.value')"
            min-width="120"
            show-overflow-tooltip
            ><template #default="{ row }">{{
              displayUaValue(row.value)
            }}</template></el-table-column
          >
          <el-table-column
            prop="status_code"
            :label="t('opcua.quality')"
            width="155"
          />
          <el-table-column
            prop="source_timestamp"
            :label="t('opcua.sourceTimestamp')"
            min-width="210"
          />
          <el-table-column
            prop="server_timestamp"
            :label="t('opcua.serverTimestamp')"
            min-width="210"
          />
        </el-table>
      </section>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { showError } from "@/api/http";
import {
  getOpcUaFeatures,
  saveOpcUaFeature,
  readOpcUaHistory,
  type OpcUaHistoryOptions,
  type OpcUaValueSnapshot,
} from "@/api/opcuaApi";
import {
  displayUaValue,
  downloadCsv,
  type UaSelection,
} from "@/utils/opcuaPubSub";
import OpcUaTrendPlot from "./OpcUaTrendPlot.vue";
const props = defineProps<{
  channelId: number;
  role: "client" | "server";
  running: boolean;
  nodes: UaSelection[];
  revision?: number;
}>();
const emit = defineEmits<{ restoreNodes: [nodeIds: string[]] }>();
const { t } = useI18n();
const storage = ref({
  enabled: false,
  nodes: [] as string[],
  retention_days: 7,
  max_values: 100000,
});
const range = ref<[Date, Date]>([new Date(Date.now() - 3600000), new Date()]);
const options = ref<OpcUaHistoryOptions>({
  limit: 100,
  mode: "raw",
  aggregate: "Average",
  processing_interval_ms: 1000,
  timestamps: "Both",
  return_bounds: false,
  release: false,
});
const aggregates = ["Average", "Minimum", "Maximum", "Count", "Total"];
const values = ref<OpcUaValueSnapshot[]>([]),
  errors = ref<Record<string, string>>({}),
  busy = ref(false),
  saving = ref(false);
const view = ref("table"),
  chartNode = ref("");
type Query = {
  channel: number;
  start: string;
  end: string;
  options: OpcUaHistoryOptions;
  tokens: Record<string, string | null>;
};
let original: Query | null = null,
  epoch = 0,
  loadEpoch = 0;
const hasMore = computed(() => Object.values(tokens.value).some(Boolean));
const tokens = ref<Record<string, string | null>>({});
const capped = computed(() => values.value.length >= 10000);
const chartPoints = computed(() =>
  values.value
    .filter((v) => v.node_id === chartNode.value)
    .slice()
    .sort(
      (a, b) =>
        Date.parse(a.source_timestamp || a.server_timestamp || "") -
        Date.parse(b.source_timestamp || b.server_timestamp || ""),
    )
    .map((v) => ({
      timestamp: v.source_timestamp || v.server_timestamp,
      value: v.value,
      status: v.status_code,
    })),
);
async function release(query: Query | null) {
  if (!query) return;
  await Promise.allSettled(
    Object.entries(query.tokens)
      .filter(([, token]) => token)
      .map(([id, token]) =>
        readOpcUaHistory(query.channel, id, query.start, query.end, token, {
          ...query.options,
          release: true,
        }),
      ),
  );
}
function reset() {
  epoch++;
  const previous = original;
  original = null;
  tokens.value = {};
  values.value = [];
  errors.value = {};
  busy.value = false;
  void release(previous);
}
async function load() {
  const current = ++loadEpoch;
  if (props.role !== "server") return;
  try {
    const features = await getOpcUaFeatures(props.channelId);
    if (current !== loadEpoch) return;
    storage.value = {
      enabled: false,
      nodes: [],
      retention_days: 7,
      max_values: 100000,
      ...features.history,
    };
    emit("restoreNodes", storage.value.nodes);
  } catch (e) {
    if (current === loadEpoch) showError(e);
  }
}
async function saveStorage(start: boolean) {
  const current = epoch;
  saving.value = true;
  try {
    const config = {
      ...storage.value,
      nodes: props.nodes.map((n) => n.node_id),
      enabled: start || storage.value.enabled,
    };
    await saveOpcUaFeature(props.channelId, "history", config);
    if (current !== epoch) return;
    storage.value = config;
    ElMessage.success(t("opcua.configSaved"));
  } catch (e) {
    if (current === epoch) showError(e);
  } finally {
    if (current === epoch) saving.value = false;
  }
}
async function stopStorage() {
  const current = epoch;
  saving.value = true;
  try {
    await saveOpcUaFeature(props.channelId, "history", {
      ...storage.value,
      enabled: false,
    });
    if (current === epoch) storage.value.enabled = false;
  } catch (e) {
    if (current === epoch) showError(e);
  } finally {
    if (current === epoch) saving.value = false;
  }
}
async function query(next: boolean) {
  if (busy.value) return;
  if (!next) {
    if (
      !range.value ||
      !range.value[0] ||
      !range.value[1] ||
      range.value[0] >= range.value[1]
    ) {
      ElMessage.warning(t("opcua.chooseRange"));
      return;
    }
    reset();
    original = {
      channel: props.channelId,
      start: range.value[0].toISOString(),
      end: range.value[1].toISOString(),
      options: { ...options.value },
      tokens: Object.fromEntries(props.nodes.map((n) => [n.node_id, null])),
    };
  }
  if (!original) return;
  const current = epoch,
    query = original;
  busy.value = true;
  try {
    // Independent cursors keep multi-node pagination and retries bound to the original query.
    for (const [id, token] of Object.entries(query.tokens)) {
      if (next && !token) continue;
      try {
        const result = await readOpcUaHistory(
          query.channel,
          id,
          query.start,
          query.end,
          token,
          query.options,
        );
        query.tokens[id] = result.continuation;
        if (current !== epoch) {
          await release(query);
          return;
        }
        values.value = [...values.value, ...result.values].slice(0, 10000);
        delete errors.value[id];
      } catch (e) {
        if (current !== epoch) return;
        errors.value[id] = e instanceof Error ? e.message : String(e);
      }
      tokens.value = { ...query.tokens };
      if (capped.value) {
        await release(query);
        query.tokens = {};
        tokens.value = {};
        break;
      }
    }
  } finally {
    if (current === epoch) busy.value = false;
  }
}
function exportCsv() {
  downloadCsv(
    "opcua-history.csv",
    ["NodeId", "Value", "Quality", "SourceTimestamp", "ServerTimestamp"],
    values.value.map((v) => [
      v.node_id,
      v.value,
      v.status_code,
      v.source_timestamp,
      v.server_timestamp,
    ]),
  );
}
watch(
  () => props.nodes.map((n) => n.node_id).join("\n"),
  () => {
    reset();
    if (!props.nodes.some((n) => n.node_id === chartNode.value))
      chartNode.value = props.nodes[0]?.node_id || "";
  },
);
watch(
  () => [props.channelId, props.role],
  () => {
    reset();
    saving.value = false;
    storage.value = {
      enabled: false,
      nodes: [],
      retention_days: 7,
      max_values: 100000,
    };
    range.value = [new Date(Date.now() - 3600000), new Date()];
    options.value = {
      limit: 100,
      mode: "raw",
      aggregate: "Average",
      processing_interval_ms: 1000,
      timestamps: "Both",
      return_bounds: false,
      release: false,
    };
    void load();
  },
  { immediate: true },
);
watch(() => props.revision, load);
watch(
  () => props.running,
  (value) => {
    if (!value) reset();
  },
);
onBeforeUnmount(() => {
  loadEpoch++;
  reset();
});
</script>
<style scoped>
.ua-history-workspace {
  display: grid;
  gap: 14px;
}
.history-options {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 0 16px;
}
.range {
  grid-column: 1/-1;
}
.range :deep(.el-date-editor) {
  width: 100%;
}
.ua-muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.ua-toolbar {
  margin-top: 12px;
}
.el-alert + .el-alert {
  margin-top: 8px;
}
</style>
