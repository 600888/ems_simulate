<template>
  <el-dialog
    v-model="visible"
    class="connection-monitor-dialog"
    width="min(1152px, calc(100vw - 48px))"
    top="7vh"
    append-to-body
    destroy-on-close
    :show-close="false"
    @closed="stopPolling"
  >
    <template #header>
      <div class="monitor-header">
        <div class="monitor-title-group">
          <span class="monitor-icon"
            ><el-icon><Connection /></el-icon
          ></span>
          <div>
            <h2>{{ t("connectionMonitor.title") }}</h2>
            <p>{{ t("connectionMonitor.subtitle") }}</p>
          </div>
        </div>
        <el-button
          circle
          text
          :aria-label="t('common.close')"
          @click="visible = false"
        >
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
    </template>

    <div v-loading="initialLoading" class="monitor-body">
      <section class="server-summary">
        <div class="server-identity">
          <div class="server-name-line">
            <span
              :class="['listening-dot', { stopped: !summary.server_running }]"
            />
            <strong>{{ serverName || deviceName }}</strong>
          </div>
          <span class="server-endpoint">
            {{ t("connectionMonitor.listenAddress") }}&nbsp;
            {{ endpoint || "-" }}
          </span>
        </div>
        <div class="summary-item summary-primary">
          <span>{{ t("connectionMonitor.currentConnections") }}</span>
          <strong>{{ summary.current_count }}</strong>
        </div>
        <div class="summary-item">
          <span>{{ t("connectionMonitor.activeConnections") }}</span>
          <strong>{{ summary.active_count }}</strong>
        </div>
        <div class="summary-item">
          <span>{{ t("connectionMonitor.historyConnections") }}</span>
          <strong>{{ summary.history_count }}</strong>
        </div>
        <div class="summary-item summary-warning">
          <span>{{ t("connectionMonitor.abnormalToday") }}</span>
          <strong>{{ summary.abnormal_disconnects_today }}</strong>
        </div>
      </section>

      <nav class="connection-tabs" :aria-label="t('connectionMonitor.title')">
        <button
          type="button"
          :class="{ active: activeTab === 'current' }"
          @click="switchTab('current')"
        >
          {{ t("connectionMonitor.currentConnections") }}
          <span>{{ summary.current_count }}</span>
        </button>
        <button
          type="button"
          :class="{ active: activeTab === 'history' }"
          @click="switchTab('history')"
        >
          {{ t("connectionMonitor.historyConnections") }}
          <span>{{ summary.history_count }}</span>
        </button>
      </nav>

      <section class="connections-content">
        <div class="connections-toolbar">
          <div class="toolbar-status">
            <el-icon :class="{ rotating: refreshing }"><Refresh /></el-icon>
            <span v-if="activeTab === 'current'">
              {{ t("connectionMonitor.liveRefresh") }}
            </span>
            <span v-else>
              {{
                t("connectionMonitor.historyRetention", {
                  count: history.retention_limit || 100,
                })
              }}
            </span>
          </div>
          <div class="toolbar-actions">
            <template v-if="activeTab === 'history'">
              <el-input
                v-model="filters.remoteIp"
                class="ip-filter"
                clearable
                :placeholder="t('connectionMonitor.filterIp')"
                @keyup.enter="applyHistoryFilters"
                @clear="applyHistoryFilters"
              />
              <el-select
                v-model="filters.reason"
                class="reason-filter"
                clearable
                :placeholder="t('connectionMonitor.filterReason')"
                @change="applyHistoryFilters"
              >
                <el-option
                  v-for="reason in disconnectReasonOptions"
                  :key="reason"
                  :label="disconnectReasonLabel(reason)"
                  :value="reason"
                />
              </el-select>
            </template>
            <el-button :loading="refreshing" @click="refreshActiveTab">
              <el-icon><Refresh /></el-icon>
              {{ t("common.refresh") }}
            </el-button>
          </div>
        </div>

        <template v-if="activeTab === 'current'">
          <div v-if="currentConnections.length" class="table-wrap">
            <el-table
              :data="currentConnections"
              stripe
              height="100%"
              class="connections-table"
              @row-dblclick="openDetail"
            >
              <el-table-column
                :label="t('connectionMonitor.status')"
                width="86"
                fixed
              >
                <template #default="{ row }">
                  <span :class="['state-pill', `state-${row.state}`]">
                    <i />{{ stateLabel(row.state) }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('connectionMonitor.clientAddress')"
                min-width="170"
              >
                <template #default="{ row }"
                  ><code>{{
                    endpointText(row.remote_ip, row.remote_port)
                  }}</code></template
                >
              </el-table-column>
              <el-table-column
                :label="t('connectionMonitor.connectedAt')"
                min-width="158"
              >
                <template #default="{ row }">{{
                  formatDateTime(row.transport_connected_at)
                }}</template>
              </el-table-column>
              <el-table-column
                :label="t('connectionMonitor.duration')"
                min-width="106"
              >
                <template #default="{ row }">{{
                  formatDuration(row.duration_ms)
                }}</template>
              </el-table-column>
              <el-table-column
                :label="t('connectionMonitor.lastActivity')"
                min-width="148"
              >
                <template #default="{ row }">{{
                  formatDateTime(row.last_activity_at)
                }}</template>
              </el-table-column>
              <el-table-column
                :label="t('connectionMonitor.traffic')"
                min-width="126"
              >
                <template #default="{ row }">
                  <div class="traffic-cell">
                    <span>RX {{ formatBytes(row.rx_bytes) }}</span
                    ><span>TX {{ formatBytes(row.tx_bytes) }}</span>
                  </div>
                </template>
              </el-table-column>
              <el-table-column
                :label="t('connectionMonitor.security')"
                min-width="104"
              >
                <template #default="{ row }"
                  ><span :class="['security-pill', { secure: hasTls(row) }]">{{
                    securityText(row)
                  }}</span></template
                >
              </el-table-column>
              <el-table-column
                :label="t('connectionMonitor.actions')"
                width="72"
                fixed="right"
              >
                <template #default="{ row }"
                  ><el-button link type="primary" @click="openDetail(row)">{{
                    t("connectionMonitor.detail")
                  }}</el-button></template
                >
              </el-table-column>
            </el-table>
          </div>
          <div v-else class="empty-state">
            <span class="empty-icon"
              ><el-icon><SwitchButton /></el-icon
            ></span>
            <h3>{{ t("connectionMonitor.noCurrent") }}</h3>
            <p>
              {{
                t("connectionMonitor.listeningAt", {
                  name: serverName,
                  endpoint: endpoint || "-",
                })
              }}
            </p>
            <small>{{ t("connectionMonitor.noCurrentHint") }}</small>
            <el-button @click="switchTab('history')"
              ><el-icon><Timer /></el-icon
              >{{ t("connectionMonitor.viewHistory") }}</el-button
            >
          </div>
          <footer v-if="currentConnections.length" class="content-footer">
            <span>{{
              t("connectionMonitor.currentTotal", {
                count: currentConnections.length,
              })
            }}</span>
            <span>{{
              t("connectionMonitor.updatedAt", { time: lastUpdatedTime })
            }}</span>
          </footer>
        </template>

        <template v-else>
          <div class="table-wrap">
            <el-table
              :data="history.items"
              stripe
              height="100%"
              class="connections-table"
              @row-dblclick="openDetail"
            >
              <el-table-column
                :label="t('connectionMonitor.result')"
                width="86"
                fixed
              >
                <template #default="{ row }"
                  ><span :class="['state-pill', `state-${row.state}`]"
                    ><i />{{ historyStateLabel(row) }}</span
                  ></template
                >
              </el-table-column>
              <el-table-column
                :label="t('connectionMonitor.clientAddress')"
                min-width="170"
              >
                <template #default="{ row }"
                  ><code>{{
                    endpointText(row.remote_ip, row.remote_port)
                  }}</code></template
                >
              </el-table-column>
              <el-table-column
                :label="t('connectionMonitor.connectedAt')"
                min-width="150"
              >
                <template #default="{ row }">{{
                  formatDateTime(row.transport_connected_at, true)
                }}</template>
              </el-table-column>
              <el-table-column
                :label="t('connectionMonitor.duration')"
                min-width="106"
              >
                <template #default="{ row }">{{
                  formatDuration(row.duration_ms)
                }}</template>
              </el-table-column>
              <el-table-column
                :label="t('connectionMonitor.disconnectedAt')"
                min-width="150"
              >
                <template #default="{ row }">{{
                  disconnectedAtText(row)
                }}</template>
              </el-table-column>
              <el-table-column
                :label="t('connectionMonitor.disconnectReason')"
                min-width="138"
              >
                <template #default="{ row }">{{
                  disconnectReasonLabel(row.disconnect_reason)
                }}</template>
              </el-table-column>
              <el-table-column
                :label="t('connectionMonitor.security')"
                min-width="104"
              >
                <template #default="{ row }"
                  ><span :class="['security-pill', { secure: hasTls(row) }]">{{
                    securityText(row)
                  }}</span></template
                >
              </el-table-column>
              <el-table-column
                :label="t('connectionMonitor.actions')"
                width="72"
                fixed="right"
              >
                <template #default="{ row }"
                  ><el-button link type="primary" @click="openDetail(row)">{{
                    t("connectionMonitor.detail")
                  }}</el-button></template
                >
              </el-table-column>
              <template #empty
                ><el-empty :description="t('connectionMonitor.noHistory')"
              /></template>
            </el-table>
          </div>
          <footer class="content-footer history-footer">
            <span>{{
              t("connectionMonitor.retentionNote", {
                count: history.retention_limit || 100,
              })
            }}</span>
            <el-pagination
              v-model:current-page="historyPage"
              v-model:page-size="historyPageSize"
              small
              background
              layout="total, prev, pager, next"
              :total="history.total"
              @current-change="loadHistory"
            />
          </footer>
        </template>
      </section>
    </div>
  </el-dialog>

  <el-dialog
    v-model="detailVisible"
    class="connection-detail-dialog"
    width="min(720px, calc(100vw - 48px))"
    top="10vh"
    append-to-body
    :show-close="false"
  >
    <template #header>
      <div class="detail-header">
        <div>
          <div class="detail-title-line">
            <h2>{{ t("connectionMonitor.detailTitle") }}</h2>
            <span v-if="detail" :class="['state-pill', `state-${detail.state}`]"
              ><i />{{ stateLabel(detail.state) }}</span
            >
          </div>
          <p>{{ t("connectionMonitor.detailSubtitle") }}</p>
        </div>
        <el-button circle text @click="detailVisible = false"
          ><el-icon><Close /></el-icon
        ></el-button>
      </div>
    </template>

    <div v-loading="detailLoading" class="detail-body">
      <template v-if="detail">
        <section class="identity-hero">
          <div class="client-hero">
            <span class="client-icon"
              ><el-icon><UserFilled /></el-icon
            ></span>
            <div>
              <code>{{
                endpointText(detail.remote_ip, detail.remote_port)
              }}</code
              ><span>{{ protocolLabel(detail.protocol_type) }}</span>
            </div>
          </div>
          <div class="security-summary">
            <el-icon><Lock v-if="hasTls(detail)" /><Unlock v-else /></el-icon>
            <div>
              <strong>{{ securityText(detail) }}</strong
              ><span>{{ cipherText(detail) }}</span>
            </div>
          </div>
        </section>

        <section class="detail-grid timeline-grid">
          <article>
            <el-icon><Clock /></el-icon
            ><span>{{ t("connectionMonitor.connectedAt") }}</span
            ><strong>{{
              formatDateTime(detail.transport_connected_at)
            }}</strong>
          </article>
          <article>
            <el-icon><Timer /></el-icon
            ><span>{{ t("connectionMonitor.duration") }}</span
            ><strong>{{ formatDuration(detail.duration_ms) }}</strong>
          </article>
          <article>
            <el-icon><Refresh /></el-icon
            ><span>{{ t("connectionMonitor.lastActivity") }}</span
            ><strong>{{ formatDateTime(detail.last_activity_at) }}</strong>
          </article>
        </section>

        <section class="detail-grid traffic-grid">
          <article>
            <span>{{ t("connectionMonitor.rxTraffic") }}</span
            ><strong>{{ formatBytes(detail.rx_bytes) }}</strong
            ><small
              >RX {{ detail.rx_messages.toLocaleString() }}
              {{ t("connectionMonitor.frames") }}</small
            >
          </article>
          <article>
            <span>{{ t("connectionMonitor.txTraffic") }}</span
            ><strong>{{ formatBytes(detail.tx_bytes) }}</strong
            ><small
              >TX {{ detail.tx_messages.toLocaleString() }}
              {{ t("connectionMonitor.frames") }}</small
            >
          </article>
          <article :class="{ 'has-error': detail.error_count > 0 }">
            <span>{{ t("connectionMonitor.communicationErrors") }}</span
            ><strong>{{ detail.error_count }}</strong
            ><small>{{
              detail.close_detail || t("connectionMonitor.noErrors")
            }}</small>
          </article>
        </section>

        <section class="information-panels">
          <article>
            <h3>{{ t("connectionMonitor.connectionInfo") }}</h3>
            <dl>
              <dt>{{ t("connectionMonitor.remoteAddress") }}</dt>
              <dd>{{ endpointText(detail.remote_ip, detail.remote_port) }}</dd>
              <dt>{{ t("connectionMonitor.localAddress") }}</dt>
              <dd>{{ endpointText(detail.local_ip, detail.local_port) }}</dd>
              <dt>{{ t("connectionMonitor.transportProtocol") }}</dt>
              <dd>TCP / {{ ipVersion(detail.remote_ip) }}</dd>
            </dl>
          </article>
          <article>
            <h3>{{ t("connectionMonitor.securityInfo") }}</h3>
            <dl>
              <dt>{{ t("connectionMonitor.encryptionStatus") }}</dt>
              <dd>
                {{
                  hasTls(detail)
                    ? t("connectionMonitor.encrypted")
                    : t("connectionMonitor.unencrypted")
                }}
              </dd>
              <dt>{{ t("connectionMonitor.tlsVersion") }}</dt>
              <dd>{{ tlsVersion(detail) }}</dd>
              <dt>{{ t("connectionMonitor.cipherSuite") }}</dt>
              <dd>{{ cipherText(detail) }}</dd>
              <dt>{{ t("connectionMonitor.disconnectReason") }}</dt>
              <dd>{{ disconnectReasonLabel(detail.disconnect_reason) }}</dd>
            </dl>
          </article>
        </section>

        <section class="session-id-row">
          <div>
            <span>{{ t("connectionMonitor.sessionId") }}</span
            ><code>{{ detail.session_id }}</code>
          </div>
          <el-button @click="copySessionId"
            ><el-icon><CopyDocument /></el-icon
            >{{ t("common.copy") }}</el-button
          >
        </section>
      </template>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import {
  Close,
  Clock,
  Connection,
  CopyDocument,
  Lock,
  Refresh,
  SwitchButton,
  Timer,
  Unlock,
  UserFilled,
} from "@element-plus/icons-vue";
import {
  getConnectionDetail,
  getConnectionHistory,
  getConnectionSummary,
  getCurrentConnections,
} from "@/api/connectionMonitorApi";
import type {
  ConnectionHistoryResult,
  ConnectionRecord,
  ConnectionState,
  ConnectionSummary,
  DisconnectReason,
} from "@/api/connectionMonitorApi";

const props = defineProps<{
  modelValue: boolean;
  deviceName: string;
  serverName: string;
  endpoint: string;
}>();
const emit = defineEmits<{
  (event: "update:modelValue", value: boolean): void;
}>();
const { t, locale } = useI18n();

const emptySummary = (): ConnectionSummary => ({
  supported: true,
  server_running: false,
  current_count: 0,
  active_count: 0,
  idle_count: 0,
  history_count: 0,
  abnormal_disconnects_today: 0,
});

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit("update:modelValue", value),
});
const summary = reactive<ConnectionSummary>(emptySummary());
const currentConnections = ref<ConnectionRecord[]>([]);
const history = reactive<ConnectionHistoryResult>({
  supported: true,
  total: 0,
  retention_limit: 100,
  items: [],
});
const activeTab = ref<"current" | "history">("current");
const initialLoading = ref(false);
const refreshing = ref(false);
const detailLoading = ref(false);
const detailVisible = ref(false);
const detail = ref<ConnectionRecord | null>(null);
const historyPage = ref(1);
const historyPageSize = ref(20);
const filters = reactive<{ remoteIp: string; reason: DisconnectReason | "" }>({
  remoteIp: "",
  reason: "",
});
const lastUpdatedAt = ref<Date | null>(null);
let pollTimer: number | null = null;
let requestInFlight = false;

const disconnectReasonOptions: DisconnectReason[] = [
  "remote_closed",
  "network_reset",
  "idle_timeout",
  "protocol_error",
  "tls_handshake_failed",
  "authentication_failed",
  "server_stopped",
  "connection_replaced",
  "max_connections_rejected",
  "process_terminated",
  "unknown",
];

const lastUpdatedTime = computed(() =>
  lastUpdatedAt.value
    ? new Intl.DateTimeFormat(locale.value, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      }).format(lastUpdatedAt.value)
    : "-",
);

const assignSummary = (value: ConnectionSummary) =>
  Object.assign(summary, emptySummary(), value);

const loadSummary = async () =>
  assignSummary(await getConnectionSummary(props.deviceName));
const loadCurrent = async () => {
  const result = await getCurrentConnections(props.deviceName);
  currentConnections.value = result.items || [];
};
const loadHistory = async () => {
  const result = await getConnectionHistory(props.deviceName, {
    page: historyPage.value,
    page_size: historyPageSize.value,
    disconnect_reason: filters.reason || null,
    remote_ip: filters.remoteIp || null,
  });
  Object.assign(history, result);
};

const refreshActiveTab = async () => {
  if (requestInFlight || !visible.value) return;
  requestInFlight = true;
  refreshing.value = true;
  try {
    await Promise.all([
      loadSummary(),
      activeTab.value === "current" ? loadCurrent() : loadHistory(),
    ]);
    lastUpdatedAt.value = new Date();
  } finally {
    refreshing.value = false;
    requestInFlight = false;
  }
};

const startPolling = () => {
  stopPolling();
  pollTimer = window.setInterval(() => {
    if (activeTab.value === "current") refreshActiveTab();
  }, 5000);
};
const stopPolling = () => {
  if (pollTimer !== null) window.clearInterval(pollTimer);
  pollTimer = null;
};

const switchTab = async (tab: "current" | "history") => {
  activeTab.value = tab;
  if (tab === "history") await loadHistory();
};
const applyHistoryFilters = async () => {
  historyPage.value = 1;
  await refreshActiveTab();
};

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) {
      stopPolling();
      return;
    }
    initialLoading.value = true;
    activeTab.value = "current";
    try {
      await refreshActiveTab();
      startPolling();
    } finally {
      initialLoading.value = false;
    }
  },
);

const openDetail = async (row: ConnectionRecord) => {
  detailVisible.value = true;
  detailLoading.value = true;
  detail.value = row;
  try {
    detail.value = await getConnectionDetail(props.deviceName, row.session_id);
  } finally {
    detailLoading.value = false;
  }
};

const endpointText = (ip: string | null, port: number | null) => {
  if (!ip) return "-";
  const host = ip.includes(":") ? `[${ip}]` : ip;
  return port === null || port === undefined ? host : `${host}:${port}`;
};
const formatDateTime = (value: string | null, compact = false) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat(locale.value, {
    year: compact ? undefined : "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
};
const formatDuration = (milliseconds: number) => {
  const totalSeconds = Math.max(0, Math.floor((milliseconds || 0) / 1000));
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (days) return t("connectionMonitor.durationDays", { days, hours });
  if (hours) return t("connectionMonitor.durationHours", { hours, minutes });
  if (minutes)
    return t("connectionMonitor.durationMinutes", { minutes, seconds });
  return t("connectionMonitor.durationSeconds", { seconds });
};
const formatBytes = (value: number) => {
  const bytes = Math.max(0, Number(value) || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(2)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
};
const stateLabel = (state: ConnectionState) =>
  t(`connectionMonitor.states.${state}`);
const disconnectReasonLabel = (reason: DisconnectReason | null) =>
  reason ? t(`connectionMonitor.reasons.${reason}`) : "-";
const historyStateLabel = (row: ConnectionRecord) => {
  if (row.state === "abnormal") return t("connectionMonitor.states.abnormal");
  if (row.disconnect_reason === "idle_timeout")
    return t("connectionMonitor.timeout");
  return t("connectionMonitor.states.closed");
};
const hasTls = (row: ConnectionRecord) =>
  Boolean(row.security?.tls || row.security?.version);
const tlsVersion = (row: ConnectionRecord) =>
  String(row.security?.version || (hasTls(row) ? "TLS" : "-"));
const cipherText = (row: ConnectionRecord) =>
  String(row.security?.cipher || "-");
const securityText = (row: ConnectionRecord) =>
  hasTls(row) ? tlsVersion(row) : t("connectionMonitor.unencrypted");
const protocolLabel = (protocol: string) =>
  protocol.replace(/Server$/i, "").replace(/([a-z])([A-Z])/g, "$1 $2");
const ipVersion = (ip: string | null) => (ip?.includes(":") ? "IPv6" : "IPv4");
const disconnectedAtText = (row: ConnectionRecord) =>
  row.disconnected_at
    ? formatDateTime(row.disconnected_at, true)
    : row.end_time_accuracy === "estimated"
      ? t("connectionMonitor.endTimeUnknown")
      : "-";

const copySessionId = async () => {
  if (!detail.value) return;
  await navigator.clipboard.writeText(detail.value.session_id);
  ElMessage.success(t("connectionMonitor.copied"));
};

onBeforeUnmount(stopPolling);
</script>

<style lang="scss">
.connection-monitor-dialog,
.connection-detail-dialog {
  border-radius: 10px;
  overflow: hidden;
  background: var(--panel-bg);
  color: var(--text-primary);

  .el-dialog__header {
    padding: 0;
    margin: 0;
  }
  .el-dialog__body {
    padding: 0;
  }
}

/* Element Plus 的 .el-dialog 自带 padding:16px，会令内容四周内缩、
   表头不贴顶、左右留出可见边距。这里清掉，让内容通栏满宽并与设计稿一致。 */
.el-overlay-dialog .connection-monitor-dialog {
  padding: 0;
}

.connection-monitor-dialog {
  height: 92vh;

  .monitor-header,
  .detail-header {
    height: 72px;
    padding: 0 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid var(--border-color);
  }
  .monitor-title-group {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .monitor-icon,
  .client-icon {
    display: grid;
    place-items: center;
    width: 38px;
    height: 38px;
    border-radius: 8px;
    color: var(--color-primary);
    background: var(--status-info-bg);
    font-size: 19px;
  }
  h2 {
    font-size: 16px;
    line-height: 24px;
    font-weight: 600;
  }
  p {
    color: var(--text-secondary);
    font-size: 11px;
    line-height: 18px;
  }
}

.monitor-body {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.server-summary {
  flex-shrink: 0;
  height: 82px;
  display: grid;
  grid-template-columns: minmax(240px, 1.8fr) repeat(4, minmax(105px, 1fr));
  gap: 20px;
  align-items: center;
  padding: 0 24px;
  background: var(--bg-subtle);
  border-bottom: 1px solid var(--border-color);
}
.server-identity {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.server-name-line {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 14px;
}
.listening-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-success);
  box-shadow: 0 0 0 3px
    color-mix(in srgb, var(--color-success) 14%, transparent);
}
.listening-dot.stopped {
  background: var(--color-danger);
  box-shadow: none;
}
.server-endpoint {
  color: var(--text-secondary);
  font:
    11px Consolas,
    monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.summary-item span {
  color: var(--text-secondary);
  font-size: 10px;
}
.summary-item strong {
  font-size: 18px;
  font-weight: 600;
}
.summary-primary strong {
  color: var(--color-primary);
}
.summary-warning strong {
  color: var(--color-warning);
}

.connection-tabs {
  flex-shrink: 0;
  height: 49px;
  display: flex;
  align-items: flex-end;
  gap: 24px;
  padding: 0 24px;
  border-bottom: 1px solid var(--border-color);
}
.connection-tabs button {
  height: 48px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 13px;
}
.connection-tabs button.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
  font-weight: 600;
}
.connection-tabs button span {
  min-width: 20px;
  height: 20px;
  padding: 0 7px;
  display: inline-grid;
  place-items: center;
  border-radius: 10px;
  background: var(--bg-muted);
  font-size: 10px;
}
.connection-tabs button.active span {
  color: var(--color-primary);
  background: var(--status-info-bg);
}

.connections-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 16px 24px 18px;
}
.connections-toolbar {
  flex-shrink: 0;
  height: 34px;
  margin-bottom: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.toolbar-status {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--text-secondary);
  font-size: 11px;
}
.toolbar-status .el-icon {
  color: var(--color-success);
}
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ip-filter {
  width: 154px;
}
.reason-filter {
  width: 152px;
}
.rotating {
  animation: monitor-rotate 0.8s linear infinite;
}
@keyframes monitor-rotate {
  to {
    transform: rotate(360deg);
  }
}

.table-wrap {
  flex: 1;
  min-height: 0;
}
.connections-table {
  height: 100%;
  border: 1px solid var(--border-color);
  border-radius: 7px;
  overflow: hidden;
}
.connections-table code {
  color: var(--text-primary);
  font:
    12px Consolas,
    monospace;
}
.traffic-cell {
  display: flex;
  flex-direction: column;
  font:
    11px Consolas,
    monospace;
  line-height: 17px;
}
.state-pill,
.security-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
  font-size: 11px;
}
.state-pill i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}
.state-active,
.state-established {
  color: var(--color-success);
}
.state-idle,
.state-connecting {
  color: var(--color-warning);
}
.state-closed {
  color: var(--text-secondary);
}
.state-abnormal {
  color: var(--color-danger);
}
.security-pill {
  padding: 3px 7px;
  border-radius: 4px;
  color: var(--text-secondary);
  background: var(--bg-muted);
}
.security-pill.secure {
  color: var(--color-success);
  background: var(--status-normal-bg);
}

.empty-state {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: 1px solid var(--border-color);
  border-radius: 7px;
  background: var(--bg-subtle);
}
.empty-icon {
  width: 56px;
  height: 56px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--bg-muted);
  color: var(--text-secondary);
  font-size: 25px;
}
.empty-state h3 {
  font-size: 15px;
  font-weight: 600;
}
.empty-state p {
  font-size: 11px;
}
.empty-state small {
  color: var(--text-secondary);
}
.content-footer {
  flex-shrink: 0;
  min-height: 34px;
  padding-top: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--text-secondary);
  font-size: 11px;
}

.connection-detail-dialog {
  .detail-header {
    min-height: 68px;
    padding: 14px 22px;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    border-bottom: 1px solid var(--border-color);
  }
  .detail-title-line {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .detail-title-line h2 {
    font-size: 16px;
  }
  .detail-header p {
    margin-top: 4px;
    color: var(--text-secondary);
    font-size: 11px;
  }
}
.detail-body {
  max-height: calc(80vh - 68px);
  overflow-y: auto;
  padding: 18px 22px 22px;
}
.identity-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px;
  border-radius: 8px;
  background: var(--bg-subtle);
  border: 1px solid var(--border-color);
}
.client-hero {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.client-hero > div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.client-hero code {
  font:
    14px Consolas,
    monospace;
  font-weight: 600;
}
.client-hero span {
  color: var(--text-secondary);
  font-size: 11px;
}
.security-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-success);
}
.security-summary div {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.security-summary span {
  color: var(--text-secondary);
  font-size: 10px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.detail-grid {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}
.detail-grid article {
  min-width: 0;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  border: 1px solid var(--border-color);
  border-radius: 7px;
}
.detail-grid article > .el-icon {
  color: var(--color-primary);
}
.detail-grid span {
  color: var(--text-secondary);
  font-size: 10px;
}
.detail-grid strong {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.detail-grid small {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.timeline-grid,
.traffic-grid {
  grid-template-columns: repeat(3, 1fr);
}
.traffic-grid strong {
  font-size: 18px;
}
.traffic-grid article.has-error strong {
  color: var(--color-danger);
}
.information-panels {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-top: 12px;
}
.information-panels article {
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: 7px;
}
.information-panels h3 {
  margin-bottom: 12px;
  font-size: 12px;
}
.information-panels dl {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  row-gap: 9px;
  font-size: 11px;
}
.information-panels dt {
  color: var(--text-secondary);
}
.information-panels dd {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-id-row {
  margin-top: 12px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-radius: 7px;
  background: var(--bg-subtle);
}
.session-id-row > div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.session-id-row span {
  color: var(--text-secondary);
  font-size: 10px;
}
.session-id-row code {
  overflow: hidden;
  text-overflow: ellipsis;
  font:
    11px Consolas,
    monospace;
}

@media (max-width: 900px) {
  .server-summary {
    grid-template-columns: 1.6fr repeat(2, 1fr);
    height: auto;
    padding-top: 12px;
    padding-bottom: 12px;
  }
  .connections-toolbar {
    height: auto;
    align-items: flex-start;
  }
  .toolbar-actions {
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  .information-panels {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 620px) {
  .server-summary {
    grid-template-columns: 1fr 1fr;
  }
  .server-identity {
    grid-column: 1 / -1;
  }
  .connections-toolbar {
    flex-direction: column;
  }
  .toolbar-actions,
  .ip-filter,
  .reason-filter {
    width: 100%;
  }
  .timeline-grid,
  .traffic-grid {
    grid-template-columns: 1fr;
  }
  .identity-hero {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
