<template>
  <div class="reports-manager">
    <div class="reports-header">
      <h3>{{ t('report.title') }}</h3>
      <el-button type="primary" size="small" :loading="loading" @click="loadRcbs">
        {{ t('common.refresh') }}
      </el-button>
    </div>

    <div class="reports-body" v-loading="loading">
      <el-empty v-if="!loading && rcbs.length === 0" :description="t('report.noRcbs')" />

      <template v-if="rcbs.length > 0">
        <!-- 左侧 RCB 树 -->
        <div class="rcb-tree-panel">
          <el-input
            v-model="searchText"
            :placeholder="t('common.searchPlaceholder')"
            size="small"
            clearable
            class="rcb-search"
          />
          <el-tree
            ref="rcbTreeRef"
            :data="rcbTreeData"
            :props="{
              children: 'children',
              label: 'label',
            }"
            node-key="ref"
            default-expand-all
            highlight-current
            :filter-node-method="filterRcbNode"
            @node-click="onRcbSelect"
          >
            <template #default="{ node, data }">
              <span class="rcb-tree-node">
                <span v-if="data.isRcb" class="rcb-type-badge" :class="data.rcb_type">
                  {{ data.rcb_type }}
                </span>
                <span :class="{ 'rcb-active': data.rpt_ena }">{{ node.label }}</span>
                <el-tag v-if="data.rpt_ena" type="success" size="small" class="ena-tag">
                  {{ t('report.enabled') }}
                </el-tag>
              </span>
            </template>
          </el-tree>
        </div>

        <!-- 右侧详情面板 -->
        <div class="rcb-detail-panel" v-if="selectedRcb">
          <el-tabs v-model="detailTab">
            <!-- 属性 Tab -->
            <el-tab-pane :label="t('report.attributes')" name="attributes">
              <div class="rcb-detail-info">
                <el-descriptions :column="2" border size="small">
                  <el-descriptions-item :label="t('report.name')" width="120px">
                    {{ selectedRcb.name }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('report.rcbType')">
                    <el-tag :type="selectedRcb.rcb_type === 'BRCB' ? 'primary' : 'warning'" size="small">
                      {{ selectedRcb.rcb_type }}
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('report.rptId')">
                    {{ selectedRcb.rpt_id || '-' }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('report.dataSet')">
                    {{ selectedRcb.data_set_ref || '-' }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('report.confRev')">
                    {{ selectedRcb.conf_rev }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('report.bufTime')">
                    {{ selectedRcb.buf_time }} ms
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('report.intgPeriod')">
                    {{ selectedRcb.intg_period }} ms
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('report.rptEna')">
                    <el-tag v-if="selectedRcb.rpt_ena" type="success" size="small">
                      {{ t('report.enabled') }}
                    </el-tag>
                    <el-tag v-else type="info" size="small">
                      {{ t('report.disabled') }}
                    </el-tag>
                  </el-descriptions-item>
                </el-descriptions>

                <!-- TrgOps -->
                <h4 class="section-title">{{ t('report.trgOps') }}</h4>
                <el-checkbox-group v-model="trgOpsModel" class="trg-ops-group">
                  <el-checkbox label="dchg" :disabled="!canEdit">{{ t('report.dchg') }}</el-checkbox>
                  <el-checkbox label="qchg" :disabled="!canEdit">{{ t('report.qchg') }}</el-checkbox>
                  <el-checkbox label="dupd" :disabled="!canEdit">{{ t('report.dupd') }}</el-checkbox>
                  <el-checkbox label="period" :disabled="!canEdit">{{ t('report.period') }}</el-checkbox>
                  <el-checkbox label="gi" :disabled="!canEdit">{{ t('report.giLabel') }}</el-checkbox>
                </el-checkbox-group>

                <!-- OptFields -->
                <h4 class="section-title">{{ t('report.optFields') }}</h4>
                <el-checkbox-group v-model="optFieldsModel" class="opt-fields-group">
                  <el-checkbox label="seq_num" :disabled="!canEdit">{{ t('report.seqNum') }}</el-checkbox>
                  <el-checkbox label="time_stamp" :disabled="!canEdit">{{ t('report.timeStamp') }}</el-checkbox>
                  <el-checkbox label="data_set" :disabled="!canEdit">{{ t('report.dataSetField') }}</el-checkbox>
                  <el-checkbox label="reason_code" :disabled="!canEdit">{{ t('report.reasonCode') }}</el-checkbox>
                  <el-checkbox label="data_ref" :disabled="!canEdit">{{ t('report.dataRef') }}</el-checkbox>
                  <el-checkbox label="entry_id" :disabled="!canEdit">{{ t('report.entryId') }}</el-checkbox>
                  <el-checkbox label="config_ref" :disabled="!canEdit">{{ t('report.configRef') }}</el-checkbox>
                  <el-checkbox label="buf_ovfl" :disabled="!canEdit">{{ t('report.bufOvfl') }}</el-checkbox>
                </el-checkbox-group>

                <!-- 操作按钮 -->
                <div class="action-buttons">
                  <el-button
                    v-if="!selectedRcb.rpt_ena"
                    type="success"
                    :loading="actionLoading"
                    @click="handleEnable"
                  >
                    {{ t('report.enable') }}
                  </el-button>
                  <el-button
                    v-if="selectedRcb.rpt_ena"
                    type="danger"
                    :loading="actionLoading"
                    @click="handleDisable"
                  >
                    {{ t('report.disable') }}
                  </el-button>
                  <el-button
                    :disabled="!selectedRcb.rpt_ena"
                    :loading="giLoading"
                    @click="handleGi"
                  >
                    {{ t('report.gi') }}
                  </el-button>
                </div>
              </div>
            </el-tab-pane>

            <!-- 报告数据 Tab -->
            <el-tab-pane
              :label="`${t('report.reportData')} (${reportDataTotal})`"
              name="data"
              :lazy="true"
            >
              <div class="report-data-panel">
                <el-alert
                  v-if="reportDataTotal === 0"
                  :title="t('report.noData')"
                  type="info"
                  :closable="false"
                  show-icon
                />
                <el-table
                  v-if="reportDataTotal > 0"
                  :data="reportData"
                  border
                  stripe
                  size="small"
                  max-height="500"
                  style="width: 100%"
                >
                  <el-table-column :label="t('report.seqNumShort')" prop="seq_num" width="60" />
                  <el-table-column :label="t('report.time')" prop="time_stamp" width="160" />
                  <el-table-column :label="t('report.reason')" prop="reason_codes" min-width="120">
                    <template #default="{ row }">
                      <el-tag
                        v-for="(rc, idx) in Object.values(row.reason_codes).slice(0, 3)"
                        :key="idx"
                        size="small"
                        :type="rc === 'data-change' ? 'warning' : rc === 'gi' ? 'success' : 'info'"
                      >
                        {{ rc }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column :label="t('report.values')" min-width="200">
                    <template #default="{ row }">
                      <div class="report-values">
                        <div
                          v-for="(val, ref, idx) in row.data_values"
                          :key="idx"
                          class="report-value-item"
                        >
                          <span class="value-ref">{{ ref }}:</span>
                          <span class="value-val">{{ val }}</span>
                        </div>
                      </div>
                    </template>
                  </el-table-column>
                </el-table>
                <el-button
                  v-if="reportDataTotal > 0"
                  size="small"
                  class="clear-btn"
                  @click="handleClearData"
                >
                  {{ t('common.clear') }}
                </el-button>
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElTree } from 'element-plus';
import {
  listRcbs,
  enableReport,
  disableReport,
  triggerGi,
  getReportData,
  type RcbInfo,
} from '@/api/reportApi';

const { t } = useI18n();

const props = defineProps<{
  channelId: number;
}>();

const loading = ref(false);
const actionLoading = ref(false);
const giLoading = ref(false);
const rcbs = ref<RcbInfo[]>([]);
const searchText = ref('');
const selectedRcb = ref<RcbInfo | null>(null);
const rcbTreeRef = ref<InstanceType<typeof ElTree> | null>(null);
const detailTab = ref('attributes');
const trgOpsModel = ref<string[]>([]);
const optFieldsModel = ref<string[]>([]);

// 报告数据
const reportData = ref<any[]>([]);
const reportDataTotal = ref(0);

const canEdit = computed(() => !selectedRcb.value?.rpt_ena);

// RCB 树形数据
interface RcbTreeNode {
  ref: string;
  label: string;
  children?: RcbTreeNode[];
  isRcb?: boolean;
  rcb_type?: string;
  rpt_ena?: boolean;
}

const rcbTreeData = computed<RcbTreeNode[]>(() => {
  const ldMap = new Map<string, { children: RcbTreeNode[] }>();

  for (const rcb of rcbs.value) {
    const ldName = rcb.ld || 'Unknown';
    const lnName = rcb.ln || 'Unknown';
    const parentKey = ldName;

    if (!ldMap.has(parentKey)) {
      ldMap.set(parentKey, { children: [] });
    }

    ldMap.get(parentKey)!.children.push({
      ref: rcb.ref,
      label: rcb.name,
      isRcb: true,
      rcb_type: rcb.rcb_type,
      rpt_ena: rcb.rpt_ena,
    });
  }

  return Array.from(ldMap.entries()).map(([ldName, ldData]) => ({
    ref: `ld-${ldName}`,
    label: ldName,
    children: ldData.children,
  }));
});

const filterRcbNode = (value: string, data: RcbTreeNode): boolean => {
  if (!value) return true;
  return data.label.toLowerCase().includes(value.toLowerCase());
};

watch(searchText, (val) => {
  rcbTreeRef.value?.filter(val);
});

function onRcbSelect(data: RcbTreeNode) {
  if (!data.isRcb) return;

  selectedRcb.value = rcbs.value.find((r) => r.ref === data.ref) || null;
  if (selectedRcb.value) {
    syncCheckboxes();
    loadReportData();
  }
  detailTab.value = 'attributes';
}

function syncCheckboxes() {
  if (!selectedRcb.value) return;
  const trg = selectedRcb.value.trg_ops;
  trgOpsModel.value = Object.keys(trg).filter((k) => (trg as any)[k]);
  const opt = selectedRcb.value.opt_fields;
  optFieldsModel.value = Object.keys(opt).filter((k) => (opt as any)[k]);
}

async function loadRcbs() {
  if (!props.channelId) return;
  loading.value = true;
  try {
    rcbs.value = await listRcbs(props.channelId);
    if (rcbs.value.length > 0) {
      // 自动选中第一个 RCB
      await nextTick();
      const firstRcb = rcbs.value[0];
      selectedRcb.value = firstRcb;
      syncCheckboxes();
      loadReportData();
    }
  } catch (err) {
    console.error('Load RCBs error:', err);
    ElMessage.error(t('common.failed'));
  } finally {
    loading.value = false;
  }
}

async function loadReportData() {
  if (!selectedRcb.value || !props.channelId) return;
  try {
    const resp = await getReportData(props.channelId, selectedRcb.value.ref);
    reportData.value = resp.data || [];
    reportDataTotal.value = resp.total || 0;
  } catch (err) {
    reportData.value = [];
    reportDataTotal.value = 0;
  }
}

function buildTrgOpsFromModel(): Record<string, boolean> {
  return {
    dchg: trgOpsModel.value.includes('dchg'),
    qchg: trgOpsModel.value.includes('qchg'),
    dupd: trgOpsModel.value.includes('dupd'),
    period: trgOpsModel.value.includes('period'),
    gi: trgOpsModel.value.includes('gi'),
  };
}

function buildOptFieldsFromModel(): Record<string, boolean> {
  return {
    seq_num: optFieldsModel.value.includes('seq_num'),
    time_stamp: optFieldsModel.value.includes('time_stamp'),
    data_set: optFieldsModel.value.includes('data_set'),
    reason_code: optFieldsModel.value.includes('reason_code'),
    data_ref: optFieldsModel.value.includes('data_ref'),
    entry_id: optFieldsModel.value.includes('entry_id'),
    config_ref: optFieldsModel.value.includes('config_ref'),
    buf_ovfl: optFieldsModel.value.includes('buf_ovfl'),
  };
}

async function handleEnable() {
  if (!selectedRcb.value) return;
  actionLoading.value = true;
  try {
    const ok = await enableReport(
      props.channelId,
      selectedRcb.value.ref,
      true,
      buildTrgOpsFromModel(),
      buildOptFieldsFromModel(),
    );
    if (ok) {
      ElMessage.success(t('report.enableSuccess'));
      await loadRcbs();
    } else {
      ElMessage.error(t('report.enableFailed'));
    }
  } finally {
    actionLoading.value = false;
  }
}

async function handleDisable() {
  if (!selectedRcb.value) return;
  actionLoading.value = true;
  try {
    const ok = await disableReport(props.channelId, selectedRcb.value.ref);
    if (ok) {
      ElMessage.success(t('report.disableSuccess'));
      await loadRcbs();
    } else {
      ElMessage.error(t('report.disableFailed'));
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
      // GI 后延迟加载报告数据
      setTimeout(loadReportData, 1000);
    } else {
      ElMessage.error(t('report.giFailed'));
    }
  } finally {
    giLoading.value = false;
  }
}

function handleClearData() {
  reportData.value = [];
  reportDataTotal.value = 0;
}

onMounted(() => {
  loadRcbs();
});
</script>

<style scoped>
.reports-manager {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border-radius: 4px;
}

.reports-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #ebeef5;
}

.reports-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.reports-body {
  display: flex;
  flex: 1;
  overflow: hidden;
  padding: 0;
}

.rcb-tree-panel {
  width: 280px;
  min-width: 280px;
  border-right: 1px solid #ebeef5;
  padding: 8px;
  overflow-y: auto;
}

.rcb-search {
  margin-bottom: 8px;
}

.rcb-tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.rcb-type-badge {
  display: inline-block;
  padding: 0 4px;
  border-radius: 2px;
  font-size: 11px;
  font-weight: 600;
  line-height: 18px;
}

.rcb-type-badge.BRCB {
  background: #ecf5ff;
  color: #409eff;
  border: 1px solid #d9ecff;
}

.rcb-type-badge.URCB {
  background: #fdf6ec;
  color: #e6a23c;
  border: 1px solid #faecd8;
}

.rcb-active {
  font-weight: 600;
  color: #67c23a;
}

.ena-tag {
  margin-left: 4px;
}

.rcb-detail-panel {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}

.rcb-detail-info {
  max-width: 800px;
}

.section-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.trg-ops-group,
.opt-fields-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.action-buttons {
  display: flex;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

.report-data-panel {
  position: relative;
}

.report-values {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.report-value-item {
  font-size: 12px;
  line-height: 1.6;
}

.value-ref {
  color: #909399;
  margin-right: 4px;
}

.value-val {
  color: #303133;
  font-weight: 500;
}

.clear-btn {
  margin-top: 8px;
}
</style>
