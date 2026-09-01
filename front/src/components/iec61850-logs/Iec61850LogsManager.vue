<template>
  <section class="log-manager">
    <header class="workbench-header">
      <div>
        <h2>IEC 61850 日志</h2>
        <p>日志控制块、事件记录与审计轨迹</p>
      </div>
      <div class="header-actions">
        <div class="auto-refresh">
          <span class="pulse"></span>
          <span>自动刷新 1s</span>
          <el-switch v-model="autoRefresh" size="small" />
        </div>
        <el-button
          :icon="Refresh"
          :loading="queryLoading"
          @click="queryLogs(true)"
        >
          刷新
        </el-button>
        <el-button
          :icon="Download"
          :disabled="!entries.length"
          @click="exportCsv"
        >
          导出 CSV
        </el-button>
      </div>
    </header>

    <div class="workbench-body">
      <aside class="tree-panel">
        <div class="panel-title">
          <span>日志控制块</span>
          <el-tag size="small" effect="plain">{{ controls.length }}</el-tag>
        </div>
        <el-input
          v-model="treeKeyword"
          :prefix-icon="Search"
          clearable
          placeholder="搜索 LogControl"
        />
        <el-scrollbar class="tree-scroll">
          <div v-if="filteredControls.length" class="control-list">
            <button
              v-for="control in filteredControls"
              :key="control.ref"
              class="control-item"
              :class="{ active: selectedControl?.ref === control.ref }"
              @click="selectControl(control)"
            >
              <span class="control-icon"
                ><el-icon><Tickets /></el-icon
              ></span>
              <span class="control-copy">
                <strong>{{ control.name }}</strong>
                <small>{{ control.ld }} / {{ control.ln }}</small>
              </span>
              <el-tag :type="control.enabled ? 'success' : 'info'" size="small">
                {{ control.enabled ? "启用" : "停用" }}
              </el-tag>
            </button>
          </div>
          <el-empty v-else :image-size="68" description="未发现日志控制块" />
        </el-scrollbar>
      </aside>

      <main class="logs-workspace" v-loading="controlsLoading">
        <el-empty
          v-if="!selectedControl && !controlsLoading"
          description="请从左侧选择日志控制块"
        />
        <template v-else-if="selectedControl">
          <div class="control-summary">
            <div class="summary-heading">
              <div>
                <div class="heading-row">
                  <h3>{{ selectedControl.name }}</h3>
                  <el-tag
                    :type="selectedControl.enabled ? 'success' : 'info'"
                    size="small"
                  >
                    {{ selectedControl.enabled ? "已启用" : "已停用" }}
                  </el-tag>
                </div>
                <p>{{ selectedControl.ref }}</p>
              </div>
              <div class="summary-status">
                <span>{{ result.total.toLocaleString() }} 条</span>
                <el-switch
                  :model-value="selectedControl.enabled"
                  :loading="enableLoading"
                  @change="toggleEnabled"
                />
              </div>
            </div>
            <div class="property-strip">
              <div class="property-cell">
                <span>日志引用 (LogRef)</span>
                <strong>{{ selectedControl.log_ref || "—" }}</strong>
              </div>
              <div class="property-cell">
                <span>数据集 (DatSet)</span>
                <strong>{{ selectedControl.data_set_ref || "—" }}</strong>
              </div>
              <div class="property-cell">
                <span>触发条件 (TrgOps)</span>
                <strong>{{ triggerText(selectedControl.trg_ops) }}</strong>
              </div>
              <div class="property-cell">
                <span>完整性周期 (IntgPd)</span>
                <strong>{{ selectedControl.intg_period || 0 }} ms</strong>
              </div>
            </div>
          </div>

          <div class="query-bar">
            <label>
              <span>时间范围</span>
              <el-select v-model="timeRange" @change="applyQuery">
                <el-option label="最近 1 小时" value="1h" />
                <el-option label="最近 24 小时" value="24h" />
                <el-option label="最近 7 天" value="7d" />
              </el-select>
            </label>
            <label>
              <span>级别</span>
              <el-select v-model="levelFilter" @change="applyQuery">
                <el-option label="全部级别" value="" />
                <el-option label="信息" value="info" />
                <el-option label="警告" value="warning" />
                <el-option label="错误" value="error" />
              </el-select>
            </label>
            <label>
              <span>服务</span>
              <el-select v-model="serviceFilter" @change="applyQuery">
                <el-option label="全部服务" value="" />
                <el-option label="Report" value="Report" />
                <el-option label="Control" value="Control" />
                <el-option label="Setting" value="Setting" />
                <el-option label="MMS" value="MMS" />
                <el-option label="Log" value="Log" />
              </el-select>
            </label>
            <el-input
              v-model="keyword"
              :prefix-icon="Search"
              clearable
              placeholder="对象引用、消息或 EntryID"
              @keyup.enter="applyQuery"
              @clear="applyQuery"
            />
            <el-button type="primary" :icon="Search" @click="applyQuery"
              >查询</el-button
            >
          </div>

          <div class="log-content">
            <section class="entries-panel">
              <nav class="log-tabs">
                <button
                  v-for="tab in tabs"
                  :key="tab.key"
                  :class="{ active: activeTab === tab.key }"
                  @click="activeTab = tab.key"
                >
                  {{ tab.label }} <span>{{ tab.count }}</span>
                </button>
              </nav>
              <div class="table-wrap">
                <el-table
                  :data="visibleEntries"
                  height="100%"
                  highlight-current-row
                  row-key="entry_id"
                  empty-text="当前条件下没有日志记录"
                  @current-change="selectEntry"
                >
                  <el-table-column label="时间" width="136">
                    <template #default="{ row }">
                      <code>{{ formatLogTime(row.timestamp) }}</code>
                    </template>
                  </el-table-column>
                  <el-table-column label="级别" width="86">
                    <template #default="{ row }">
                      <span :class="['severity', normalizeLevel(row.level)]">
                        <i></i>{{ levelText(row.level) }}
                      </span>
                    </template>
                  </el-table-column>
                  <el-table-column prop="service" label="服务" width="105" />
                  <el-table-column label="对象引用" min-width="180">
                    <template #default="{ row }"
                      ><code>{{ row.object_ref || "—" }}</code></template
                    >
                  </el-table-column>
                  <el-table-column
                    prop="message"
                    label="消息"
                    min-width="240"
                    show-overflow-tooltip
                  />
                </el-table>
              </div>
              <footer class="pagination-bar">
                <span>
                  {{ pageStart }}–{{ pageEnd }} /
                  {{ result.total.toLocaleString() }} 条
                  <em v-if="result.more_follows">· 设备仍有后续记录</em>
                </span>
                <el-pagination
                  v-model:current-page="page"
                  :page-size="pageSize"
                  :total="result.total"
                  layout="prev, pager, next"
                  small
                  @current-change="queryLogs(true)"
                />
              </footer>
            </section>

            <aside class="entry-detail">
              <template v-if="selectedEntry">
                <div class="entry-title">
                  <div>
                    <h3>日志详情</h3>
                    <code>Entry #{{ selectedEntry.entry_id || "—" }}</code>
                  </div>
                  <el-tag :type="tagType(selectedEntry.level)" size="small">
                    {{ levelText(selectedEntry.level) }}
                  </el-tag>
                </div>
                <dl>
                  <div>
                    <dt>时间戳</dt>
                    <dd>{{ formatFullTime(selectedEntry.timestamp) }}</dd>
                  </div>
                  <div>
                    <dt>来源</dt>
                    <dd>{{ selectedEntry.source || "—" }}</dd>
                  </div>
                  <div>
                    <dt>服务</dt>
                    <dd>{{ selectedEntry.service || "—" }}</dd>
                  </div>
                  <div>
                    <dt>对象引用</dt>
                    <dd>
                      <code>{{ selectedEntry.object_ref || "—" }}</code>
                    </dd>
                  </div>
                </dl>
                <div class="message-block">
                  <span>消息</span>
                  <p>{{ selectedEntry.message }}</p>
                </div>
                <div class="fields-block">
                  <h4>日志字段</h4>
                  <div v-if="fieldEntries.length" class="field-list">
                    <div v-for="field in fieldEntries" :key="field[0]">
                      <code>{{ field[0] }}</code>
                      <span>{{ formatField(field[1]) }}</span>
                    </div>
                  </div>
                  <el-empty v-else :image-size="48" description="无附加字段" />
                </div>
              </template>
              <el-empty
                v-else
                :image-size="70"
                description="选择一条日志查看详情"
              />
            </aside>
          </div>
        </template>
      </main>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  computed,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  ref,
  watch,
} from "vue";
import { ElMessage } from "element-plus";
import { Download, Refresh, Search, Tickets } from "@element-plus/icons-vue";
import {
  listLogControls,
  queryIec61850Logs,
  setLogControlEnabled,
  type Iec61850LogEntry,
  type Iec61850LogResult,
  type LogControl,
  type LogTriggerOptions,
} from "@/api/iec61850LogApi";

const props = defineProps<{ channelId: number }>();

const controlsLoading = ref(false);
const queryLoading = ref(false);
const enableLoading = ref(false);
const controls = ref<LogControl[]>([]);
const selectedControl = ref<LogControl | null>(null);
const selectedEntry = ref<Iec61850LogEntry | null>(null);
const entries = ref<Iec61850LogEntry[]>([]);
const result = ref<Iec61850LogResult>({
  entries: [],
  total: 0,
  page: 1,
  page_size: 50,
  more_follows: false,
});
const treeKeyword = ref("");
const keyword = ref("");
const levelFilter = ref("");
const serviceFilter = ref("");
const timeRange = ref("24h");
const activeTab = ref<"events" | "system" | "audit">("events");
const page = ref(1);
const pageSize = 50;
const autoRefresh = ref(true);
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let pollingActive = true;

const filteredControls = computed(() => {
  const value = treeKeyword.value.trim().toLowerCase();
  if (!value) return controls.value;
  return controls.value.filter((item) =>
    `${item.name} ${item.ref} ${item.log_ref}`.toLowerCase().includes(value),
  );
});

function isSystem(entry: Iec61850LogEntry) {
  return /^(mms|association|log|quality)$/i.test(entry.service);
}

function isAudit(entry: Iec61850LogEntry) {
  return (
    /^(control|setting|security|audit)$/i.test(entry.service) ||
    Object.keys(entry.fields || {}).some((key) =>
      /origin|operator|user/i.test(key),
    )
  );
}

const visibleEntries = computed(() => {
  if (activeTab.value === "system") return entries.value.filter(isSystem);
  if (activeTab.value === "audit") return entries.value.filter(isAudit);
  return entries.value;
});

const tabs = computed(() => [
  { key: "events" as const, label: "事件日志", count: result.value.total },
  {
    key: "system" as const,
    label: "系统日志",
    count: entries.value.filter(isSystem).length,
  },
  {
    key: "audit" as const,
    label: "审计轨迹",
    count: entries.value.filter(isAudit).length,
  },
]);

const fieldEntries = computed(() =>
  Object.entries(selectedEntry.value?.fields || {}),
);
const pageStart = computed(() =>
  result.value.total ? (page.value - 1) * pageSize + 1 : 0,
);
const pageEnd = computed(() =>
  Math.min(page.value * pageSize, result.value.total),
);

function queryRange() {
  const now = Date.now();
  const duration =
    timeRange.value === "1h"
      ? 3_600_000
      : timeRange.value === "7d"
        ? 604_800_000
        : 86_400_000;
  return { start: now - duration, end: now };
}

function triggerText(options: LogTriggerOptions) {
  const names: Record<keyof LogTriggerOptions, string> = {
    dchg: "dchg",
    qchg: "qchg",
    dupd: "dupd",
    period: "period",
    gi: "gi",
  };
  return (
    (Object.keys(names) as (keyof LogTriggerOptions)[])
      .filter((key) => options?.[key])
      .map((key) => names[key])
      .join(" · ") || "—"
  );
}

function normalizeLevel(level: string) {
  const value = String(level || "info").toLowerCase();
  if (["error", "fatal", "critical"].includes(value)) return "error";
  if (["warn", "warning"].includes(value)) return "warning";
  return "info";
}

function levelText(level: string) {
  return (
    { info: "信息", warning: "警告", error: "错误" }[normalizeLevel(level)] ||
    level
  );
}

function tagType(level: string) {
  const value = normalizeLevel(level);
  return value === "error"
    ? "danger"
    : value === "warning"
      ? "warning"
      : "info";
}

function formatLogTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "—";
  return `${date.toLocaleTimeString([], { hour12: false })}.${String(date.getMilliseconds()).padStart(3, "0")}`;
}

function formatFullTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || "—";
  return `${date.toLocaleString([], { hour12: false })}.${String(date.getMilliseconds()).padStart(3, "0")}`;
}

function formatField(value: unknown) {
  if (typeof value === "object" && value !== null) return JSON.stringify(value);
  return String(value ?? "—");
}

async function loadControls() {
  if (!props.channelId) return;
  const previousRef = selectedControl.value?.ref;
  controlsLoading.value = true;
  try {
    controls.value = await listLogControls(props.channelId);
    selectedControl.value =
      controls.value.find((item) => item.ref === previousRef) ||
      controls.value[0] ||
      null;
    page.value = 1;
    await queryLogs(false);
  } finally {
    controlsLoading.value = false;
  }
}

async function selectControl(control: LogControl) {
  if (selectedControl.value?.ref === control.ref) return;
  selectedControl.value = control;
  selectedEntry.value = null;
  page.value = 1;
  await queryLogs(true);
}

async function queryLogs(showLoading = true) {
  const control = selectedControl.value;
  if (!control?.log_ref || !props.channelId || queryLoading.value) return;
  if (showLoading) queryLoading.value = true;
  const requestedRef = control.ref;
  try {
    const range = queryRange();
    const response = await queryIec61850Logs(props.channelId, {
      logRef: control.log_ref,
      startTimeMs: range.start,
      endTimeMs: range.end,
      page: page.value,
      pageSize,
      keyword: keyword.value,
      level: levelFilter.value,
      service: serviceFilter.value,
    });
    if (selectedControl.value?.ref !== requestedRef) return;
    result.value = response;
    entries.value = response.entries || [];
    if (
      !selectedEntry.value ||
      !entries.value.some(
        (item) => item.entry_id === selectedEntry.value?.entry_id,
      )
    ) {
      selectedEntry.value = entries.value[0] || null;
    }
  } finally {
    if (showLoading) queryLoading.value = false;
    schedulePoll();
  }
}

function applyQuery() {
  page.value = 1;
  void queryLogs(true);
}

function selectEntry(entry: Iec61850LogEntry | null) {
  if (entry) selectedEntry.value = entry;
}

async function toggleEnabled(value: string | number | boolean) {
  if (!selectedControl.value) return;
  enableLoading.value = true;
  try {
    const enabled = Boolean(value);
    if (
      await setLogControlEnabled(
        props.channelId,
        selectedControl.value.ref,
        enabled,
      )
    ) {
      selectedControl.value.enabled = enabled;
      ElMessage.success(enabled ? "日志控制块已启用" : "日志控制块已停用");
    }
  } finally {
    enableLoading.value = false;
  }
}

function csvCell(value: unknown) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function exportCsv() {
  const header = ["时间", "级别", "服务", "对象引用", "消息", "EntryID"];
  const rows = entries.value.map((item) => [
    item.timestamp,
    levelText(item.level),
    item.service,
    item.object_ref,
    item.message,
    item.entry_id,
  ]);
  const csv = `\ufeff${[header, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n")}`;
  const url = URL.createObjectURL(
    new Blob([csv], { type: "text/csv;charset=utf-8" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `iec61850-${selectedControl.value?.name || "logs"}-${Date.now()}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function stopPoll() {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = null;
}

function schedulePoll() {
  stopPoll();
  if (!pollingActive || !autoRefresh.value || !selectedControl.value) return;
  pollTimer = setTimeout(() => void queryLogs(false), 1000);
}

watch(() => props.channelId, loadControls);
watch(autoRefresh, schedulePoll);
onMounted(loadControls);
onActivated(() => {
  pollingActive = true;
  if (props.channelId) void loadControls();
  schedulePoll();
});
onDeactivated(() => {
  pollingActive = false;
  stopPoll();
});
onBeforeUnmount(stopPoll);
</script>

<style scoped lang="scss">
.log-manager {
  --log-border: var(--border-color, #dfe5ec);
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--log-border);
  border-radius: 6px;
  background: var(--panel-bg);
}
.workbench-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 74px;
  padding: 0 18px;
  border-bottom: 1px solid var(--log-border);
  background: var(--bg-subtle);
}
.workbench-header h2 {
  margin: 0 0 4px;
  color: var(--text-primary);
  font-size: 18px;
}
.workbench-header p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
}
.header-actions,
.auto-refresh {
  display: flex;
  align-items: center;
  gap: 9px;
}
.auto-refresh {
  margin-right: 4px;
  color: var(--text-secondary);
  font-size: 12px;
}
.pulse {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 0 3px #d1fae5;
}
.workbench-body {
  display: flex;
  flex: 1;
  min-height: 0;
}
.tree-panel {
  display: flex;
  flex: 0 0 260px;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  padding: 16px;
  border-right: 1px solid var(--log-border);
  background: var(--bg-subtle);
}
.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--text-primary);
  font-weight: 700;
}
.tree-scroll {
  flex: 1;
  min-height: 0;
}
.control-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.control-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  min-width: 0;
  padding: 10px;
  border: 1px solid transparent;
  border-radius: 4px;
  color: var(--text-primary);
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.control-item:hover {
  background: var(--bg-muted);
}
.control-item.active {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #2563eb;
}
.control-icon {
  display: grid;
  flex: 0 0 28px;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 4px;
  background: #e8edf3;
}
.control-copy {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
  gap: 3px;
}
.control-copy strong,
.control-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.control-copy small {
  color: var(--text-secondary);
  font-size: 11px;
}

.logs-workspace {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 14px;
  overflow: hidden;
}
.summary-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.heading-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.heading-row h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 17px;
}
.summary-heading p {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
}
.summary-status {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #2563eb;
  font-size: 13px;
  font-weight: 700;
}
.property-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-top: 11px;
  border: 1px solid var(--log-border);
  border-radius: 5px;
  overflow: hidden;
}
.property-cell {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 10px 12px;
  border-right: 1px solid var(--log-border);
  background: var(--bg-subtle);
}
.property-cell:last-child {
  border-right: 0;
}
.property-cell span {
  color: var(--text-secondary);
  font-size: 11px;
}
.property-cell strong {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.query-bar {
  display: grid;
  grid-template-columns: 150px 130px 145px minmax(220px, 1fr) auto;
  gap: 9px;
  align-items: end;
  margin: 12px 0;
  padding: 10px 12px;
  border: 1px solid var(--log-border);
  border-radius: 5px;
  background: var(--bg-subtle);
}
.query-bar label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}
.query-bar label > span {
  color: var(--text-secondary);
  font-size: 10px;
}
.log-content {
  display: grid;
  flex: 1;
  grid-template-columns: minmax(0, 1fr) 300px;
  min-height: 0;
  border: 1px solid var(--log-border);
  border-radius: 5px;
  overflow: hidden;
}
.entries-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.log-tabs {
  display: flex;
  align-items: end;
  gap: 20px;
  min-height: 43px;
  padding: 0 14px;
  border-bottom: 1px solid var(--log-border);
  background: var(--bg-subtle);
}
.log-tabs button {
  position: relative;
  height: 43px;
  padding: 0;
  border: 0;
  color: var(--text-secondary);
  background: transparent;
  cursor: pointer;
}
.log-tabs button.active {
  color: #2563eb;
  font-weight: 700;
}
.log-tabs button.active::after {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 2px;
  background: #3b82f6;
  content: "";
}
.log-tabs span {
  display: inline-block;
  margin-left: 4px;
  padding: 1px 5px;
  border-radius: 8px;
  background: #e8edf3;
  font-size: 9px;
}
.table-wrap {
  flex: 1;
  min-height: 0;
}
code {
  font-family: "Roboto Mono", Consolas, monospace;
  font-size: 11px;
}
.severity {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.severity i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #3b82f6;
}
.severity.warning {
  color: #b45309;
}
.severity.warning i {
  background: #f59e0b;
}
.severity.error {
  color: #dc2626;
}
.severity.error i {
  background: #ef4444;
}
.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 38px;
  padding: 0 12px;
  border-top: 1px solid var(--log-border);
  color: var(--text-secondary);
  font-size: 11px;
}
.pagination-bar em {
  color: #b45309;
  font-style: normal;
}

.entry-detail {
  min-width: 0;
  padding: 14px;
  border-left: 1px solid var(--log-border);
  background: var(--bg-subtle);
  overflow: auto;
}
.entry-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--log-border);
}
.entry-title h3 {
  margin: 0 0 4px;
  color: var(--text-primary);
  font-size: 14px;
}
.entry-title code {
  color: var(--text-secondary);
}
dl {
  margin: 12px 0;
}
dl > div {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr);
  gap: 8px;
  padding: 7px 0;
  border-bottom: 1px solid var(--log-border);
  font-size: 11px;
}
dt {
  color: var(--text-secondary);
}
dd {
  min-width: 0;
  margin: 0;
  color: var(--text-primary);
  overflow-wrap: anywhere;
}
.message-block {
  padding: 10px;
  border: 1px solid var(--log-border);
  border-radius: 4px;
  background: var(--panel-bg);
}
.message-block span {
  color: var(--text-secondary);
  font-size: 10px;
}
.message-block p {
  margin: 6px 0 0;
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.6;
}
.fields-block h4 {
  margin: 14px 0 8px;
  color: var(--text-primary);
  font-size: 12px;
}
.field-list {
  border: 1px solid var(--log-border);
  border-radius: 4px;
  background: var(--panel-bg);
}
.field-list > div {
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr);
  gap: 8px;
  padding: 7px 9px;
  border-bottom: 1px solid var(--log-border);
  font-size: 11px;
}
.field-list > div:last-child {
  border-bottom: 0;
}
.field-list span {
  min-width: 0;
  overflow-wrap: anywhere;
}

@container (max-width: 1080px) {
  .workbench-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
    padding: 12px 16px;
  }
  .tree-panel {
    flex-basis: 225px;
  }
  .query-bar {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .query-bar > .el-input {
    grid-column: span 2;
  }
  .log-content {
    grid-template-columns: minmax(0, 1fr) 260px;
  }
}
</style>
