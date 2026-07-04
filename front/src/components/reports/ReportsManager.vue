<template>
  <div class="reports-manager">
    <header class="reports-header">
      <h3>{{ t("report.title") }}</h3>
      <div class="reports-header-right">
        <div class="auto-refresh-group">
          <el-switch v-model="autoRefresh" />
          <span class="auto-refresh-label">{{ t("report.autoRefresh") }}</span>
          <el-select v-model="pollInterval" :disabled="!autoRefresh" style="width: 90px">
            <el-option
              v-for="opt in REFRESH_INTERVAL_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
        <el-button
          :type="batchMode ? 'primary' : 'default'"
          @click="batchMode = !batchMode"
        >
          {{ batchMode ? t("report.exitBatchMode") : t("report.batchMode") }}
        </el-button>
        <el-button type="primary" :loading="loading" @click="loadRcbs">
          {{ t("common.refresh") }}
        </el-button>
      </div>
    </header>

    <!-- 批量操作进度对话框 -->
    <el-dialog
      v-model="batchProgressVisible"
      :title="t('report.batchProgressTitle')"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
      width="420px"
      destroy-on-close
    >
      <div class="batch-progress-body">
        <el-progress
          :percentage="batchProgressPercent"
          :status="batchProgressStatus"
          :stroke-width="16"
          :text-inside="true"
        />
        <p class="batch-progress-text">{{ batchProgressText }}</p>
      </div>
      <template #footer>
        <el-button
          v-if="!batchProgressFinished"
          type="danger"
          :loading="batchCancelling"
          @click="handleBatchCancel"
        >
          {{ t("report.batchCancel") }}
        </el-button>
      </template>
    </el-dialog>

    <main class="reports-body" v-loading="loading">
      <el-empty v-if="!loading && rcbs.length === 0" :description="t('report.noRcbs')" />
      <template v-else>
        <RcbTreePanel
          :rcbs="rcbs"
          :selected-ref="selectedRcb?.ref"
          :show-checkbox="batchMode"
          :checked-refs="checkedRefs"
          @select="onRcbSelect"
          @update:checked-refs="checkedRefs = $event"
        />

        <section v-if="selectedRcb" class="report-workspace">
          <el-tabs v-model="detailTab" class="report-tabs">
            <el-tab-pane :label="t('report.attributes')" name="attributes">
              <ReportControlPanel
                :rcb="selectedRcb"
                :action-loading="actionLoading"
                :gi-loading="giLoading"
                :batch-loading="batchLoading"
                :batch-mode="batchMode"
                :selected-count="selectedCount"
                @apply="handleApplyConfig"
                @batch-apply="handleBatchApplyConfig"
                @gi="handleGi"
              />
            </el-tab-pane>

            <el-tab-pane :label="t('report.lastReportInfo')" name="latest">
              <div class="latest-pane">
                <div class="entry-summary" v-if="latestEntry">
                  <span>{{ t("report.seqNum") }}: {{ latestEntry.seq_num ?? "-" }}</span>
                  <span
                    >{{ t("report.time") }}:
                    {{ latestEntry.received_at || latestEntry.time_stamp || "-" }}</span
                  >
                  <span
                    >{{ t("report.dataSet") }}: {{ latestEntry.data_set || "-" }}</span
                  >
                  <span>{{ t("report.values") }}: {{ latestEntry.value_count }}</span>
                </div>
                <ReportDataTreeTable
                  :tree-items="latestTreeItems"
                  :loading="latestLoading"
                />
              </div>
            </el-tab-pane>

            <el-tab-pane
              :label="`${t('report.reportData')} (${reportDataTotal})`"
              name="data"
              lazy
            >
              <div class="history-pane">
                <ReportHistoryPanel
                  class="history-list"
                  :entries="reportHistory"
                  :selected-entry-key="selectedEntryKey"
                  :loading="historyLoading"
                  @select="handleHistorySelect"
                />
                <div class="history-tree">
                  <div class="entry-summary" v-if="selectedEntry">
                    <span
                      >{{ t("report.seqNum") }}: {{ selectedEntry.seq_num ?? "-" }}</span
                    >
                    <span
                      >{{ t("report.time") }}:
                      {{
                        selectedEntry.received_at || selectedEntry.time_stamp || "-"
                      }}</span
                    >
                    <span
                      >{{ t("report.dataSet") }}:
                      {{ selectedEntry.data_set || "-" }}</span
                    >
                    <span>{{ t("report.values") }}: {{ selectedEntry.value_count }}</span>
                  </div>
                  <ReportDataTreeTable
                    :tree-items="selectedTreeItems"
                    :loading="selectedTreeLoading"
                  />
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </section>
      </template>
    </main>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  nextTick,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  ref,
  watch,
} from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import {
  applyConfig,
  getLatestReport,
  getReportDataTree,
  getReportHistory,
  getReportState,
  listRcbs,
  triggerGi,
  type OptFields,
  type RcbInfo,
  type ReportEntrySummary,
  type ReportTreeNode,
  type TrgOps,
} from '@/api/reportApi';
import RcbTreePanel from './RcbTreePanel.vue';
import ReportControlPanel from './ReportControlPanel.vue';
import ReportDataTreeTable from './ReportDataTreeTable.vue';
import ReportHistoryPanel from './ReportHistoryPanel.vue';

const { t } = useI18n();

const props = defineProps<{
  channelId: number;
}>();

const loading = ref(false);
const latestLoading = ref(false);
const historyLoading = ref(false);
const selectedTreeLoading = ref(false);
const actionLoading = ref(false);
const batchLoading = ref(false);
const giLoading = ref(false);
const rcbs = ref<RcbInfo[]>([]);
const selectedRcb = ref<RcbInfo | null>(null);
const detailTab = ref('attributes');

const checkedRefs = ref<string[]>([]);
const selectedCount = computed(() => checkedRefs.value.length);
const batchMode = ref(false);

// 退出批量模式时清空勾选
watch(batchMode, (val) => {
  if (!val) checkedRefs.value = [];
});

// 批量操作进度
const batchProgressVisible = ref(false);
const batchProgressPercent = ref(0);
const batchProgressStatus = ref<'success' | 'exception' | ''>('');
const batchProgressText = ref('');
const batchCancelled = ref(false);
const batchCancelling = ref(false);
const batchProgressFinished = ref(false);

const reportHistory = ref<ReportEntrySummary[]>([]);
const reportDataTotal = ref(0);
const latestEntry = ref<ReportEntrySummary | null>(null);
const latestTreeItems = ref<ReportTreeNode[]>([]);
const selectedEntry = ref<ReportEntrySummary | null>(null);
const selectedEntryKey = ref<string | null>(null);
const selectedTreeItems = ref<ReportTreeNode[]>([]);

const autoRefresh = ref(true);
const pollInterval = ref(1000);
const REFRESH_INTERVAL_OPTIONS = [
  { value: 1000, label: '1s' },
  { value: 3000, label: '3s' },
  { value: 5000, label: '5s' },
  { value: 10000, label: '10s' },
];
let reportPollTimer: ReturnType<typeof setTimeout> | null = null;
let stateRequestId = 0;
let latestRequestId = 0;
let historyRequestId = 0;
let selectedTreeRequestId = 0;
let rcbRequestInFlight = false;
let latestKnownUid: number | null = null;
let historyKnownUid: number | null = null;
let reportPollingActive = true;

watch(
  () => props.channelId,
  (newId) => {
    resetReportState();
    detailTab.value = 'attributes';
    if (newId) loadRcbs();
  },
);

watch(detailTab, (tab) => {
  if (tab === 'latest') void loadLatestReportData(true);
  if (tab === 'data') void loadReportHistory(true);
});

watch([selectedRcb, autoRefresh, pollInterval, detailTab], () => {
  startReportPolling();
});

function startReportPolling() {
  stopReportPolling();
  if (!reportPollingActive || !autoRefresh.value || !selectedRcb.value || !props.channelId) return;
  reportPollTimer = setTimeout(async () => {
    try {
      await refreshVisibleReportData(false);
    } finally {
      startReportPolling();
    }
  }, pollInterval.value);
}

function stopReportPolling() {
  if (reportPollTimer !== null) {
    clearTimeout(reportPollTimer);
    reportPollTimer = null;
  }
}

async function loadRcbs() {
  if (!props.channelId || rcbRequestInFlight) return;
  rcbRequestInFlight = true;
  const previousRef = selectedRcb.value?.ref;
  loading.value = true;
  try {
    rcbs.value = await listRcbs(props.channelId);
    await nextTick();
    if (rcbs.value.length > 0) {
      const nextRcb = rcbs.value.find((rcb) => rcb.ref === previousRef) || rcbs.value[0];
      if (nextRcb.ref !== previousRef) resetReportData();
      selectedRcb.value = nextRcb;
      void loadReportState();
    } else {
      selectedRcb.value = null;
      resetReportData();
    }
  } catch (err) {
    console.error('Load RCBs error:', err);
  } finally {
    loading.value = false;
    rcbRequestInFlight = false;
  }
}

async function loadReportState() {
  if (!selectedRcb.value || !props.channelId) return;
  const requestId = ++stateRequestId;
  const requestedChannelId = props.channelId;
  const requestedRcbRef = selectedRcb.value.ref;
  const state = await getReportState(requestedChannelId, requestedRcbRef);
  if (
    requestId !== stateRequestId
    || props.channelId !== requestedChannelId
    || selectedRcb.value?.ref !== requestedRcbRef
  ) return;
  reportDataTotal.value = state.total;
}

async function loadLatestReportData(showLoading = true) {
  if (!selectedRcb.value || !props.channelId) return;
  const requestId = ++latestRequestId;
  const requestedRcbRef = selectedRcb.value.ref;
  if (showLoading) latestLoading.value = true;
  try {
    const resp = await getLatestReport(
      props.channelId,
      requestedRcbRef,
      showLoading ? null : latestKnownUid,
    );
    if (requestId !== latestRequestId || selectedRcb.value?.ref !== requestedRcbRef || resp.unchanged) return;
    latestKnownUid = resp.latest_uid ?? null;
    latestEntry.value = resp.entry;
    latestTreeItems.value = resp.tree_items || [];
  } finally {
    if (requestId === latestRequestId && showLoading) latestLoading.value = false;
  }
}

async function loadReportHistory(showLoading = true) {
  if (!selectedRcb.value || !props.channelId) return;
  const requestId = ++historyRequestId;
  const requestedRcbRef = selectedRcb.value.ref;
  if (showLoading) historyLoading.value = true;
  try {
    const resp = await getReportHistory(
      props.channelId,
      requestedRcbRef,
      100,
      showLoading ? null : historyKnownUid,
    );
    if (requestId !== historyRequestId || selectedRcb.value?.ref !== requestedRcbRef || resp.unchanged) return;
    historyKnownUid = resp.latest_uid ?? null;
    reportHistory.value = resp.entries || [];
    reportDataTotal.value = resp.total || 0;

    if (selectedEntryKey.value && !reportHistory.value.some((entry) => entry.entry_key === selectedEntryKey.value)) {
      selectedEntryKey.value = null;
      selectedEntry.value = null;
      selectedTreeItems.value = [];
    }
  } finally {
    if (requestId === historyRequestId && showLoading) historyLoading.value = false;
  }
}

async function refreshVisibleReportData(showLoading = true) {
  if (detailTab.value === 'latest') {
    await Promise.all([loadReportState(), loadLatestReportData(showLoading)]);
    return;
  }
  if (detailTab.value === 'data') {
    await loadReportHistory(showLoading);
    return;
  }
  await loadReportState();
}

function onRcbSelect(rcb: RcbInfo) {
  selectedRcb.value = rcb;
  detailTab.value = 'attributes';
  resetReportData();
  void loadReportState();
}

async function handleHistorySelect(row: { entry_key: string }) {
  selectedEntryKey.value = row.entry_key;
  if (!selectedRcb.value || !props.channelId) return;
  const requestedRcbRef = selectedRcb.value.ref;
  const requestedEntryKey = row.entry_key;
  const requestId = ++selectedTreeRequestId;
  selectedTreeLoading.value = true;
  try {
    const result = await getReportDataTree(props.channelId, requestedRcbRef, {
      entryKey: requestedEntryKey,
      latest: false,
    });
    if (
      requestId !== selectedTreeRequestId
      || selectedRcb.value?.ref !== requestedRcbRef
      || selectedEntryKey.value !== requestedEntryKey
    ) return;
    selectedEntry.value = result.entry;
    selectedTreeItems.value = result.tree_items || [];
  } finally {
    if (requestId === selectedTreeRequestId) selectedTreeLoading.value = false;
  }
}

async function handleApplyConfig(payload: { rptEna: boolean; trgOps: TrgOps; optFields: OptFields }) {
  if (!selectedRcb.value) return;
  actionLoading.value = true;
  try {
    const result = await applyConfig(
      props.channelId,
      selectedRcb.value.ref,
      payload.rptEna,
      payload.trgOps,
      payload.optFields,
    );
    if (result.success) {
      ElMessage.success(t('report.applyConfigSuccess'));
      if (result.rcb) updateRcbInList(result.rcb);
      if (payload.rptEna) await refreshVisibleReportData(false);
    } else {
      ElMessage.error(t('report.applyConfigFailed'));
    }
  } finally {
    actionLoading.value = false;
  }
}

const BATCH_DELAY_MS = 50; // 每个 RCB 操作间的延迟

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function handleBatchCancel() {
  batchCancelling.value = true;
  batchCancelled.value = true;
  batchCancelling.value = false;
}

async function handleBatchApplyConfig(payload: { rptEna: boolean; trgOps: TrgOps; optFields: OptFields }) {
  if (checkedRefs.value.length === 0) {
    ElMessage.warning(t('report.noRcbSelected'));
    return;
  }
  batchLoading.value = true;
  batchCancelled.value = false;
  batchProgressFinished.value = false;
  const refs = [...checkedRefs.value];
  const total = refs.length;
  let successCount = 0;
  let failCount = 0;

  // 打开进度对话框
  batchProgressPercent.value = 0;
  batchProgressStatus.value = '';
  batchProgressText.value = t('report.batchApplyInProgress', { current: 0, total });
  batchProgressVisible.value = true;

  for (let i = 0; i < total; i++) {
    // 检查是否已取消
    if (batchCancelled.value) {
      batchProgressFinished.value = true;
      batchProgressStatus.value = 'exception';
      batchProgressText.value = t('report.batchCancelled', {
        current: successCount + failCount,
        total,
      });
      break;
    }

    const rcbRef = refs[i];
    try {
      const result = await applyConfig(
        props.channelId,
        rcbRef,
        payload.rptEna,
        payload.trgOps,
        payload.optFields,
      );
      if (result.success) {
        successCount++;
        if (result.rcb) updateRcbInList(result.rcb);
      } else {
        failCount++;
      }
    } catch {
      failCount++;
    }

    // 更新进度
    const done = i + 1;
    batchProgressPercent.value = Math.round((done / total) * 100);
    batchProgressText.value = t('report.batchApplyProgress', {
      current: done,
      total,
      success: successCount,
      fail: failCount,
    });

    // 每个操作间加延迟
    if (i < total - 1) {
      await sleep(BATCH_DELAY_MS);
    }
  }

  if (batchCancelled.value) {
    // 用户取消：延迟后关闭弹窗
    await sleep(500);
    batchProgressVisible.value = false;
    ElMessage.info(t('report.batchCancelled', {
      current: successCount + failCount,
      total,
    }));
  } else {
    // 正常完成：延迟后关闭弹窗
    await sleep(300);
    batchProgressVisible.value = false;

    if (failCount === 0) {
      ElMessage.success(t('report.batchApplySuccess', { count: successCount }));
    } else {
      ElMessage.warning(t('report.batchApplyPartial', { failed: failCount, total }));
    }
  }

  if (payload.rptEna && selectedRcb.value) {
    await refreshVisibleReportData(false);
  }

  batchLoading.value = false;
  batchMode.value = false;
}

async function handleGi() {
  if (!selectedRcb.value) return;
  const requestedRcbRef = selectedRcb.value.ref;
  const requestedChannelId = props.channelId;
  giLoading.value = true;
  try {
    const before = await getReportState(requestedChannelId, requestedRcbRef);
    reportDataTotal.value = before.total;
    const ok = await triggerGi(requestedChannelId, requestedRcbRef);
    if (ok) {
      ElMessage.success(t('report.giSuccess'));
      void refreshReportCountAfterGi(requestedChannelId, requestedRcbRef, before);
    } else {
      ElMessage.error(t('report.giFailed'));
    }
  } finally {
    giLoading.value = false;
  }
}

async function refreshReportCountAfterGi(
  channelId: number,
  rcbRef: string,
  before: { total: number; latest_uid: number | null },
) {
  const maxAttempts = 6;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    await sleep(attempt === 0 ? 200 : 400);
    if (!reportPollingActive || props.channelId !== channelId || selectedRcb.value?.ref !== rcbRef) return;

    const state = await getReportState(channelId, rcbRef);
    reportDataTotal.value = state.total;
    if (state.total !== before.total || state.latest_uid !== before.latest_uid) {
      // 新报告已进入缓存；使下次打开页签时强制获取最新内容。
      latestKnownUid = null;
      historyKnownUid = null;
      return;
    }
  }
}

function updateRcbInList(rcb: RcbInfo) {
  const idx = rcbs.value.findIndex((item) => item.ref === rcb.ref);
  if (idx >= 0) rcbs.value[idx] = rcb;
  selectedRcb.value = rcb;
}

function resetReportState() {
  selectedRcb.value = null;
  rcbs.value = [];
  resetReportData();
}

function resetReportData() {
  stateRequestId++;
  latestRequestId++;
  historyRequestId++;
  selectedTreeRequestId++;
  latestLoading.value = false;
  historyLoading.value = false;
  selectedTreeLoading.value = false;
  reportHistory.value = [];
  reportDataTotal.value = 0;
  latestEntry.value = null;
  latestTreeItems.value = [];
  selectedEntry.value = null;
  selectedEntryKey.value = null;
  selectedTreeItems.value = [];
  latestKnownUid = null;
  historyKnownUid = null;
}

onMounted(() => {
  reportPollingActive = true;
  loadRcbs();
});

onActivated(() => {
  reportPollingActive = true;
  if (props.channelId) loadRcbs();
  startReportPolling();
});

onDeactivated(() => {
  reportPollingActive = false;
  stopReportPolling();
});

onBeforeUnmount(() => {
  reportPollingActive = false;
  stopReportPolling();
});
</script>

<style scoped lang="scss">
.reports-manager {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border-radius: 4px;
  overflow: hidden;
}

.reports-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #d8dde5;
  background: #fbfcfe;

  h3 {
    margin: 0;
    color: #263241;
    font-size: 16px;
    font-weight: 700;
  }
}

.reports-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.auto-refresh-group {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-right: 12px;
  border-right: 1px solid #d8dde5;
}

.auto-refresh-label {
  color: #5d6876;
  font-size: 13px;
  white-space: nowrap;
}

.reports-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.reports-body > .el-empty {
  width: 100%;
}

.report-workspace {
  flex: 1;
  min-width: 0;
  min-height: 0;
  padding: 12px;
  overflow: hidden;
}

.report-tabs {
  display: flex;
  flex-direction: column;
  height: 100%;
}

:deep(.el-tabs__content) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

:deep(.el-tab-pane) {
  height: 100%;
  overflow: auto;
}

.latest-pane,
.history-tree {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 0;
}

.history-pane {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  height: 100%;
  min-height: 0;
  border: 1px solid #d8dde5;
}

.history-list {
  min-width: 0;
}

.history-tree {
  min-width: 0;
  padding: 10px;
  overflow: hidden;
}

.entry-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  min-height: 34px;
  padding: 8px 10px;
  border: 1px solid #d8dde5;
  background: #f6f8fb;
  color: #263241;
  font-size: 13px;
}

.batch-progress-body {
  padding: 8px 0;
  text-align: center;
}

.batch-progress-text {
  margin: 12px 0 0;
  color: #5d6876;
  font-size: 14px;
}

@media (max-width: 900px) {
  .reports-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .reports-body {
    flex-direction: column;
  }

  .history-pane {
    grid-template-columns: 1fr;
    grid-template-rows: 220px minmax(0, 1fr);
  }
}
</style>
