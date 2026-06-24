<template>
  <div class="reports-manager">
    <header class="reports-header">
      <h3>{{ t('report.title') }}</h3>
      <div class="reports-header-right">
        <div class="auto-refresh-group">
          <el-switch v-model="autoRefresh" />
          <span class="auto-refresh-label">{{ t('report.autoRefresh') }}</span>
          <el-select v-model="pollInterval" :disabled="!autoRefresh" style="width: 90px">
            <el-option
              v-for="opt in REFRESH_INTERVAL_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
        <el-button type="primary" :loading="loading" @click="loadRcbs">
          {{ t('common.refresh') }}
        </el-button>
      </div>
    </header>

    <main class="reports-body" v-loading="loading">
      <el-empty v-if="!loading && rcbs.length === 0" :description="t('report.noRcbs')" />
      <template v-else>
        <RcbTreePanel :rcbs="rcbs" :selected-ref="selectedRcb?.ref" @select="onRcbSelect" />

        <section v-if="selectedRcb" class="report-workspace">
          <el-tabs v-model="detailTab" class="report-tabs">
            <el-tab-pane :label="t('report.attributes')" name="attributes">
              <ReportControlPanel
                :rcb="selectedRcb"
                :action-loading="actionLoading"
                :gi-loading="giLoading"
                @apply="handleApplyConfig"
                @gi="handleGi"
              />
            </el-tab-pane>

            <el-tab-pane :label="t('report.lastReportInfo')" name="latest">
              <div class="latest-pane">
                <div class="entry-summary" v-if="latestEntry">
                  <span>{{ t('report.seqNum') }}: {{ latestEntry.seq_num ?? '-' }}</span>
                  <span>{{ t('report.time') }}: {{ latestEntry.received_at || latestEntry.time_stamp || '-' }}</span>
                  <span>{{ t('report.dataSet') }}: {{ latestEntry.data_set || '-' }}</span>
                  <span>{{ t('report.values') }}: {{ latestEntry.value_count }}</span>
                </div>
                <ReportDataTreeTable :tree-items="latestTreeItems" :loading="dataLoading" />
              </div>
            </el-tab-pane>

            <el-tab-pane :label="`${t('report.reportData')} (${reportDataTotal})`" name="data" lazy>
              <div class="history-pane">
                <ReportHistoryPanel
                  class="history-list"
                  :entries="reportData"
                  :selected-entry-key="selectedEntryKey"
                  @select="handleHistorySelect"
                />
                <div class="history-tree">
                  <div class="entry-summary" v-if="selectedEntry">
                    <span>{{ t('report.seqNum') }}: {{ selectedEntry.seq_num ?? '-' }}</span>
                    <span>{{ t('report.time') }}: {{ selectedEntry.received_at || selectedEntry.time_stamp || '-' }}</span>
                    <span>{{ t('report.dataSet') }}: {{ selectedEntry.data_set || '-' }}</span>
                    <span>{{ t('report.values') }}: {{ selectedEntry.value_count }}</span>
                  </div>
                  <ReportDataTreeTable :tree-items="selectedTreeItems" :loading="dataLoading" />
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
import { computed, nextTick, onActivated, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage } from 'element-plus';
import {
  applyConfig,
  getReportData,
  getReportDataTree,
  listRcbs,
  triggerGi,
  type OptFields,
  type RcbInfo,
  type ReportDataEntry,
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
const dataLoading = ref(false);
const actionLoading = ref(false);
const giLoading = ref(false);
const rcbs = ref<RcbInfo[]>([]);
const selectedRcb = ref<RcbInfo | null>(null);
const detailTab = ref('attributes');

const reportData = ref<ReportDataEntry[]>([]);
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
let reportPollTimer: ReturnType<typeof setInterval> | null = null;

const latestHistoryKey = computed(() => {
  if (reportData.value.length === 0) return null;
  return makeEntryKey(reportData.value[reportData.value.length - 1], reportData.value.length - 1);
});

watch(
  () => props.channelId,
  (newId) => {
    resetReportState();
    if (newId) loadRcbs();
  },
);

watch([selectedRcb, autoRefresh, pollInterval], () => {
  startReportPolling();
});

function startReportPolling() {
  stopReportPolling();
  if (!autoRefresh.value || !selectedRcb.value || !props.channelId) return;
  reportPollTimer = setInterval(() => {
    loadReportData(false);
  }, pollInterval.value);
}

function stopReportPolling() {
  if (reportPollTimer !== null) {
    clearInterval(reportPollTimer);
    reportPollTimer = null;
  }
}

async function loadRcbs() {
  if (!props.channelId) return;
  const previousRef = selectedRcb.value?.ref;
  loading.value = true;
  try {
    rcbs.value = await listRcbs(props.channelId);
    await nextTick();
    if (rcbs.value.length > 0) {
      selectedRcb.value = rcbs.value.find((rcb) => rcb.ref === previousRef) || rcbs.value[0];
      selectedEntryKey.value = null;
      await loadReportData(true);
    } else {
      selectedRcb.value = null;
      resetReportData();
    }
  } catch (err) {
    console.error('Load RCBs error:', err);
  } finally {
    loading.value = false;
  }
}

async function loadReportData(showLoading = true) {
  if (!selectedRcb.value || !props.channelId) return;
  if (showLoading) dataLoading.value = true;
  try {
    const resp = await getReportData(props.channelId, selectedRcb.value.ref);
    reportData.value = resp.data || [];
    reportDataTotal.value = resp.total || 0;

    await loadLatestTree();
    const stillExists = selectedEntryKey.value && reportData.value.some((entry, index) => makeEntryKey(entry, index) === selectedEntryKey.value);
    if (!stillExists) selectedEntryKey.value = latestHistoryKey.value;
    await loadSelectedTree();
  } finally {
    if (showLoading) dataLoading.value = false;
  }
}

async function loadLatestTree() {
  if (!selectedRcb.value || !props.channelId) return;
  const result = await getReportDataTree(props.channelId, selectedRcb.value.ref, { latest: true });
  latestEntry.value = result.entry;
  latestTreeItems.value = result.tree_items || [];
}

async function loadSelectedTree() {
  if (!selectedRcb.value || !props.channelId) return;
  if (!selectedEntryKey.value) {
    selectedEntry.value = null;
    selectedTreeItems.value = [];
    return;
  }
  const result = await getReportDataTree(props.channelId, selectedRcb.value.ref, {
    entryKey: selectedEntryKey.value,
    latest: false,
  });
  selectedEntry.value = result.entry;
  selectedTreeItems.value = result.tree_items || [];
}

function onRcbSelect(rcb: RcbInfo) {
  selectedRcb.value = rcb;
  detailTab.value = 'attributes';
  resetReportData();
  loadReportData(true);
}

async function handleHistorySelect(row: { entry_key: string }) {
  selectedEntryKey.value = row.entry_key;
  dataLoading.value = true;
  try {
    await loadSelectedTree();
  } finally {
    dataLoading.value = false;
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
      if (payload.rptEna) await loadReportData(false);
    } else {
      ElMessage.error(t('report.applyConfigFailed'));
    }
  } finally {
    actionLoading.value = false;
  }
}

async function handleGi() {
  if (!selectedRcb.value) return;
  giLoading.value = true;
  try {
    const ok = await triggerGi(props.channelId, selectedRcb.value.ref);
    if (ok) {
      ElMessage.success(t('report.giSuccess'));
      setTimeout(() => loadReportData(false), 1000);
    } else {
      ElMessage.error(t('report.giFailed'));
    }
  } finally {
    giLoading.value = false;
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
  reportData.value = [];
  reportDataTotal.value = 0;
  latestEntry.value = null;
  latestTreeItems.value = [];
  selectedEntry.value = null;
  selectedEntryKey.value = null;
  selectedTreeItems.value = [];
}

function makeEntryKey(entry: ReportDataEntry, index: number): string {
  if (entry.received_at) return `${entry.received_at}|${entry.seq_num}|${index}`;
  return `${entry.rpt_id || ''}|${entry.seq_num}|${index}`;
}

onMounted(() => {
  loadRcbs();
});

onActivated(() => {
  if (props.channelId) loadRcbs();
  startReportPolling();
});

onBeforeUnmount(() => {
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
