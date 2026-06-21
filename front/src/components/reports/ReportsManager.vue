<template>
  <div class="reports-manager">
    <div class="reports-header">
      <h3>{{ t('report.title') }}</h3>
      <el-button type="primary" :loading="loading" @click="loadRcbs">
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
                <el-descriptions :column="2" border size="small" label-width="155px">
                  <el-descriptions-item :label="`${t('report.name')} (Name)`">
                    {{ selectedRcb.name }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="`${t('report.rcbType')} (Type)`">
                    <el-tag :type="selectedRcb.rcb_type === 'BRCB' ? 'primary' : 'warning'" size="small">
                      {{ selectedRcb.rcb_type }}
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item :label="t('report.ref')" :span="2">
                    <span class="ref-text" :title="selectedRcb.ref">{{ selectedRcb.ref || '-' }}</span>
                  </el-descriptions-item>
                  <el-descriptions-item :label="`${t('report.rptId')} (RptID)`">
                    {{ selectedRcb.rpt_id || '-' }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="`${t('report.dataSet')} (DatSet)`">
                    {{ selectedRcb.data_set_ref || '-' }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="`${t('report.confRev')} (ConfRev)`">
                    {{ selectedRcb.conf_rev }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="`${t('report.sqNum')} (SqNum)`">
                    {{ selectedRcb.sq_num != null ? selectedRcb.sq_num : '-' }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="`${t('report.rptEna')} (RptEna)`">
                    <el-tag v-if="selectedRcb.rpt_ena" type="success" size="small">
                      {{ t('report.enabled') }}
                    </el-tag>
                    <el-tag v-else type="danger" size="small">
                      {{ t('report.disabled') }}
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item :label="`${t('report.trgOps')} (TrgOps)`" :span="2">
                    <span class="field-summary">{{ trgOpsSummary || '-' }}</span>
                  </el-descriptions-item>
                  <el-descriptions-item :label="`${t('report.optFields')} (OptFlds)`" :span="2">
                    <span class="field-summary">{{ optFieldsSummary || '-' }}</span>
                  </el-descriptions-item>
                  <el-descriptions-item :label="`${t('report.bufTime')} (BufTm)`">
                    {{ selectedRcb.buf_time }} ms
                  </el-descriptions-item>
                  <el-descriptions-item :label="`${t('report.intgPeriod')} (IntgPd)`">
                    {{ selectedRcb.intg_period }} ms
                  </el-descriptions-item>
                  <el-descriptions-item :label="`${t('report.giLabel')} (GI)`">
                    <el-tag v-if="giEnabled" type="success" size="small">True</el-tag>
                    <el-tag v-else type="danger" size="small">False</el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item
                    v-if="selectedRcb.rcb_type === 'BRCB'"
                    :label="`${t('report.entryId')} (EntryID)`"
                  >
                    {{ selectedRcb.entry_id || '-' }}
                  </el-descriptions-item>
                  <el-descriptions-item
                    v-if="selectedRcb.rcb_type === 'BRCB'"
                    :label="`${t('report.timeOfEntry')} (TimeOfEntry)`"
                  >
                    {{ formatTimeOfEntry(selectedRcb.time_of_entry) }}
                  </el-descriptions-item>
                  <el-descriptions-item
                    v-if="selectedRcb.rcb_type === 'BRCB'"
                    :label="`${t('report.purgeBuf')} (PurgeBuf)`"
                  >
                    <el-tag :type="selectedRcb.purge_buf ? 'warning' : 'info'" size="small">
                      {{ selectedRcb.purge_buf ? 'True' : 'False' }}
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item
                    v-if="selectedRcb.rcb_type === 'URCB'"
                    :label="`${t('report.owner')} (Owner)`"
                  >
                    {{ selectedRcb.owner || '-' }}
                  </el-descriptions-item>
                  <el-descriptions-item
                    v-if="selectedRcb.rcb_type === 'URCB'"
                    :label="`${t('report.resv')} (Resv)`"
                  >
                    <el-tag :type="selectedRcb.resv ? 'warning' : 'danger'" size="small">
                      {{ selectedRcb.resv ? 'True' : 'False' }}
                    </el-tag>
                  </el-descriptions-item>
                </el-descriptions>

                <!-- 报告使能 (独立勾选) -->
                <h4 class="section-title">{{ t('report.reportConfig') }}</h4>
                <div class="rpt-ena-row">
                  <el-checkbox v-model="rptEnaModel" size="default">
                    {{ t('report.rptEnaToggle') }}
                  </el-checkbox>
                  <el-tag
                    v-if="selectedRcb.rpt_ena"
                    type="success"
                    size="small"
                    class="ena-tag"
                  >
                    {{ t('report.enabled') }}
                  </el-tag>
                  <el-tag v-else type="danger" size="small" class="ena-tag">
                    {{ t('report.disabled') }}
                  </el-tag>
                </div>

                <!-- TrgOps + OptFields (报告使能时整体禁用) -->
                <div class="config-fields-section" :class="{ 'is-disabled': selectedRcb.rpt_ena }">
                  <div class="config-fields-header">
                    <h4 class="section-title" style="margin:0">{{ t('report.configFields') }}</h4>
                    <el-alert
                      v-if="selectedRcb.rpt_ena"
                      :title="t('report.configFieldsDisabledHint')"
                      type="warning"
                      :closable="false"
                      show-icon
                      size="small"
                    />
                  </div>

                  <h5 class="subsection-title">{{ t('report.trgOps') }}</h5>
                  <el-checkbox-group v-model="trgOpsModel" class="config-checkbox-group">
                    <el-checkbox label="dchg" size="default" :disabled="selectedRcb.rpt_ena">{{ t('report.dchg') }}</el-checkbox>
                    <el-checkbox label="qchg" size="default" :disabled="selectedRcb.rpt_ena">{{ t('report.qchg') }}</el-checkbox>
                    <el-checkbox label="dupd" size="default" :disabled="selectedRcb.rpt_ena">{{ t('report.dupd') }}</el-checkbox>
                    <el-checkbox label="period" size="default" :disabled="selectedRcb.rpt_ena">{{ t('report.period') }}</el-checkbox>
                    <el-checkbox label="gi" size="default" :disabled="selectedRcb.rpt_ena">{{ t('report.giLabel') }}</el-checkbox>
                  </el-checkbox-group>

                  <h5 class="subsection-title">{{ t('report.optFields') }}</h5>
                  <el-checkbox-group v-model="optFieldsModel" class="config-checkbox-group">
                    <el-checkbox label="seq_num" size="default" :disabled="selectedRcb.rpt_ena">{{ t('report.seqNum') }}</el-checkbox>
                    <el-checkbox label="time_stamp" size="default" :disabled="selectedRcb.rpt_ena">{{ t('report.timeStamp') }}</el-checkbox>
                    <el-checkbox label="data_set" size="default" :disabled="selectedRcb.rpt_ena">{{ t('report.dataSetField') }}</el-checkbox>
                    <el-checkbox label="reason_code" size="default" :disabled="selectedRcb.rpt_ena">{{ t('report.reasonCode') }}</el-checkbox>
                    <el-checkbox label="data_ref" size="default" :disabled="selectedRcb.rpt_ena">{{ t('report.dataRef') }}</el-checkbox>
                    <el-checkbox label="entry_id" size="default" :disabled="selectedRcb.rpt_ena">{{ t('report.entryId') }}</el-checkbox>
                    <el-checkbox label="config_ref" size="default" :disabled="selectedRcb.rpt_ena">{{ t('report.configRef') }}</el-checkbox>
                    <el-checkbox label="buf_ovfl" size="default" :disabled="selectedRcb.rpt_ena">{{ t('report.bufOvfl') }}</el-checkbox>
                  </el-checkbox-group>
                </div>

                <!-- 操作按钮: 应用配置 + 总召唤 -->
                <div class="action-buttons">
                  <el-button
                    type="primary"
                    :loading="actionLoading"
                    @click="handleApplyConfig"
                  >
                    {{ t('report.applyConfig') }}
                  </el-button>
                  <el-button
                    type="warning"
                    :disabled="!selectedRcb.rpt_ena"
                    :loading="giLoading"
                    @click="handleGi"
                  >
                    {{ t('report.gi') }}
                  </el-button>
                </div>

                <!-- Information received in last Report -->
                <h4 class="section-title">{{ t('report.lastReportInfo') }}</h4>
                <el-alert
                  v-if="!lastReport"
                  :title="t('report.noData')"
                  type="info"
                  :closable="false"
                  show-icon
                />
                <template v-if="lastReport">
                  <el-descriptions :column="2" border size="small" label-width="130px">
                    <el-descriptions-item :label="t('report.rptId')">
                      {{ lastReport.rpt_id || '-' }}
                    </el-descriptions-item>
                    <el-descriptions-item :label="t('report.seqNum')">
                      {{ lastReport.seq_num != null ? lastReport.seq_num : '-' }}
                    </el-descriptions-item>
                    <el-descriptions-item :label="t('report.timeOfEntry')">
                      {{ lastReport.time_stamp || '-' }}
                    </el-descriptions-item>
                    <el-descriptions-item :label="t('report.dataSet')">
                      {{ lastReport.data_set || '-' }}
                    </el-descriptions-item>
                    <el-descriptions-item :label="t('report.confRev')">
                      {{ lastReport.conf_rev != null ? lastReport.conf_rev : '-' }}
                    </el-descriptions-item>
                    <el-descriptions-item
                      v-if="selectedRcb.rcb_type === 'BRCB'"
                      :label="t('report.entryId')"
                    >
                      {{ lastReport.entry_id || '-' }}
                    </el-descriptions-item>
                  </el-descriptions>

                  <h4 class="section-title">{{ t('report.reportDataItems') }}</h4>
                  <el-table
                    :data="lastReportDataItems"
                    border
                    size="small"
                    max-height="400"
                    style="width: 100%"
                  >
                    <el-table-column :label="t('report.dataRef')" prop="ref" min-width="180" />
                    <el-table-column :label="t('report.value')" prop="value" min-width="120" />
                    <el-table-column :label="t('report.reason')" width="130">
                      <template #default="{ row }">
                        <el-tag
                          size="small"
                          :type="row.reason === 'data-change' ? 'warning'
                            : row.reason === 'gi' ? 'success'
                            : row.reason === 'integrity' ? 'primary' : 'info'"
                        >
                          {{ row.reason }}
                        </el-tag>
                      </template>
                    </el-table-column>
                  </el-table>
                </template>
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
                          v-for="(val, ref) in row.data_values"
                          :key="ref"
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
import { ref, computed, watch, onMounted, onActivated, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { ElMessage, ElTree } from 'element-plus';
import {
  listRcbs,
  applyConfig,
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
const rptEnaModel = ref(false);          // 报告使能配置项 (待应用)

// 报告数据
const reportData = ref<any[]>([]);
const reportDataTotal = ref(0);

// 全称映射
const TRGOPS_NAME_MAP: Record<string, string> = {
  dchg: 'DataChange',
  qchg: 'QualityChange',
  dupd: 'DataUpdate',
  period: 'Integrity',
  gi: 'GeneralInterrogation',
};

const OPTFLDS_NAME_MAP: Record<string, string> = {
  seq_num: 'SeqNum',
  time_stamp: 'TimeStamp',
  data_set: 'DataSetRef',
  reason_code: 'ReasonCode',
  data_ref: 'DataRef',
  entry_id: 'EntryID',
  config_ref: 'ConfigRef',
  buf_ovfl: 'BufOvfl',
};

// TrgOps 摘要 (如: "DataChange, GeneralInterrogation")
const trgOpsSummary = computed(() => {
  return trgOpsModel.value.map(k => TRGOPS_NAME_MAP[k] || k).join(', ') || '';
});

// OptFlds 摘要 (如: "SeqNum, TimeStamp, DataSetRef, ReasonCode")
const optFieldsSummary = computed(() => {
  return optFieldsModel.value.map(k => OPTFLDS_NAME_MAP[k] || k).join(', ') || '';
});

// GI 使能状态 (用于属性展示)
const giEnabled = computed(() => trgOpsModel.value.includes('gi'));

// 最近一次报告信息 (来自报告数据列表的第一条/最新一条)
const lastReport = computed(() => {
  if (reportData.value.length === 0) return null;
  // 报告数据按接收时间排序，取最新一条 (最后一条)
  return reportData.value[reportData.value.length - 1];
});

// 最近一条报告中的数据项 (ref, value, reason)
interface LastReportItem {
  ref: string;
  value: any;
  reason: string;
}

const lastReportDataItems = computed<LastReportItem[]>(() => {
  if (!lastReport.value) return [];
  const items: LastReportItem[] = [];
  const dv = lastReport.value.data_values || {};
  const rc = lastReport.value.reason_codes || {};
  for (const key of Object.keys(dv)) {
    items.push({
      ref: key,
      value: dv[key],
      reason: rc[key] || 'unknown',
    });
  }
  return items;
});

// 格式化 TimeOfEntry (毫秒级 Unix 时间戳 → 可读时间字符串)
function formatTimeOfEntry(timeOfEntry: number | null | undefined): string {
  if (timeOfEntry == null || timeOfEntry <= 0) return '-';
  try {
    const t = Number(timeOfEntry);
    // 支持毫秒级时间戳
    const ms = t > 1e12 ? t : t * 1000;
    return new Date(ms).toLocaleString();
  } catch {
    return String(timeOfEntry);
  }
}

// RCB 树形数据: LD → LN (LLN0) → RCB 三层结构
interface RcbTreeNode {
  ref: string;
  label: string;
  children?: RcbTreeNode[];
  isRcb?: boolean;
  rcb_type?: string;
  rpt_ena?: boolean;
}

const rcbTreeData = computed<RcbTreeNode[]>(() => {
  // ldMap: ldName -> { lnMap: lnName -> { rcbs: RcbTreeNode[] } }
  const ldMap = new Map<string, Map<string, RcbTreeNode[]>>();

  for (const rcb of rcbs.value) {
    const ldName = rcb.ld || 'Unknown';
    const lnName = rcb.ln || 'LLN0';

    if (!ldMap.has(ldName)) {
      ldMap.set(ldName, new Map());
    }
    const lnMap = ldMap.get(ldName)!;

    if (!lnMap.has(lnName)) {
      lnMap.set(lnName, []);
    }
    lnMap.get(lnName)!.push({
      ref: rcb.ref,
      label: rcb.name,
      isRcb: true,
      rcb_type: rcb.rcb_type,
      rpt_ena: rcb.rpt_ena,
    });
  }

  // 构建三层树: LD → LN → RCB
  return Array.from(ldMap.entries()).map(([ldName, lnMap]) => ({
    ref: `ld-${ldName}`,
    label: ldName,
    children: Array.from(lnMap.entries()).map(([lnName, rcbs]) => ({
      ref: `ln-${ldName}/${lnName}`,
      label: lnName,
      children: rcbs,
    })),
  }));
});

const filterRcbNode = (value: string, data: Record<string, any>): boolean => {
  if (!value) return true;
  return data.label.toLowerCase().includes(value.toLowerCase());
};

watch(searchText, (val) => {
  rcbTreeRef.value?.filter(val);
});

// 监听 channelId 变化，重新加载 RCB 列表
watch(
  () => props.channelId,
  (newId) => {
    if (newId) {
      selectedRcb.value = null;
      loadRcbs();
    }
  },
);

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
  trgOpsModel.value = trg ? Object.keys(trg).filter((k) => (trg as any)[k]) : [];
  const opt = selectedRcb.value.opt_fields;
  optFieldsModel.value = opt ? Object.keys(opt).filter((k) => (opt as any)[k]) : [];
  // 同步报告使能勾选框与后端状态
  rptEnaModel.value = !!selectedRcb.value.rpt_ena;
}

async function loadRcbs() {
  if (!props.channelId) return;
  // 记住当前选中的 RCB ref，刷新后保持选中
  const prevRef = selectedRcb.value?.ref;
  loading.value = true;
  try {
    rcbs.value = await listRcbs(props.channelId);
    if (rcbs.value.length > 0) {
      await nextTick();
      // 优先保持之前选中的 RCB，否则选中第一个
      const target = prevRef
        ? rcbs.value.find((r) => r.ref === prevRef)
        : null;
      selectedRcb.value = target || rcbs.value[0];
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

/**
 * 应用配置: 一次性写入所有配置项 (报告使能 + 总召唤使能 + 触发选项 + 可选字段)
 * - rptEnaModel=true: 调用 enableReport 写入 RptEna=True + TrgOps + OptFields
 * - rptEnaModel=false: 调用 disableReport 设置 RptEna=False
 *
 * 总召唤(GI)的"使能"体现为 TrgOps.gi 位，随配置一起写入；
 * 总召唤的"触发"是独立的手动动作，由"总召唤"按钮单独调用。
 */
async function handleApplyConfig() {
  if (!selectedRcb.value) return;
  actionLoading.value = true;
  try {
    // 统一调用 applyConfig 接口，根据 rptEnaModel 决定使能/禁用
    // 一次性写入 RptEna + TrgOps + OptFields
    const result = await applyConfig(
      props.channelId,
      selectedRcb.value.ref,
      rptEnaModel.value,
      buildTrgOpsFromModel(),
      buildOptFieldsFromModel(),
    );
    if (result.success) {
      ElMessage.success(t('report.applyConfigSuccess'));
      // 直接用后端返回的 rcb 数据更新本地状态
      if (result.rcb) {
        updateRcbInList(result.rcb);
      }
    } else {
      ElMessage.error(t('report.applyConfigFailed'));
      // 失败回滚勾选框到后端实际状态
      rptEnaModel.value = !!selectedRcb.value.rpt_ena;
    }
  } finally {
    actionLoading.value = false;
  }
}

/** 用后端返回的 rcb 数据更新本地列表和选中状态，并同步勾选框 */
function updateRcbInList(rcb: RcbInfo) {
  const idx = rcbs.value.findIndex((r) => r.ref === rcb.ref);
  if (idx >= 0) {
    rcbs.value[idx] = rcb;
  }
  selectedRcb.value = rcb;
  syncCheckboxes();
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

// keep-alive 组件从其他路由切回来时重新加载，确保获取最新 RCB 列表
onActivated(() => {
  if (props.channelId) {
    loadRcbs();
  }
});
</script>

<style scoped lang="scss">
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

  h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }

  @include bp.respond-to('small') {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
}

.reports-body {
  display: flex;
  flex: 1;
  min-height: 0; // 防止 flex 子元素撑开父容器
  overflow: hidden;
  padding: 0;

  // 空状态居中显示
  .el-empty {
    width: 100%;
    padding: 48px 0;
  }

  @include bp.respond-to('small') {
    flex-direction: column;
  }
}

.rcb-tree-panel {
  width: 340px;
  min-width: 340px;
  min-height: 0; // 防止 flex 子元素撑开
  border-right: 1px solid #ebeef5;
  padding: 8px;
  overflow-y: auto;

  @include bp.respond-to('medium-down') {
    width: 260px;
    min-width: 260px;
  }

  @include bp.respond-to('small') {
    width: 100%;
    min-width: unset;
    border-right: none;
    border-bottom: 1px solid #ebeef5;
    max-height: 200px;
  }
}

.rcb-search {
  margin-bottom: 8px;
}

.ref-text {
  font-family: monospace;
  font-size: 12px;
  word-break: break-all;
}

.field-summary {
  font-family: monospace;
  font-size: 12px;
  color: #606266;
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

  &.BRCB {
    background: #ecf5ff;
    color: #409eff;
    border: 1px solid #d9ecff;
  }

  &.URCB {
    background: #fdf6ec;
    color: #e6a23c;
    border: 1px solid #faecd8;
  }
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
  min-width: 0; // 防止 flex 子元素撑开
  min-height: 0; // 防止 flex 子元素撑开
  padding: 16px;
  overflow-y: auto;

  @include bp.respond-to('small') {
    padding: 12px;
  }
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

.subsection-title {
  margin: 12px 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: #606266;
}

.config-fields-section {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 12px 16px;
  margin-top: 8px;
  transition: opacity 0.2s;

  &.is-disabled {
    opacity: 0.6;
    background: #fafafa;
    cursor: not-allowed;
  }
}

.config-fields-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.trg-ops-group,
.opt-fields-group,
.config-checkbox-group {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px 12px;
  align-items: center;

  // 每个 checkbox 项占一格，保证上下对齐；放大勾选框为中号
  .el-checkbox {
    margin-right: 0;
    height: 32px;
    line-height: 32px;
    font-size: 15px;

    // 放大复选框图标
    --el-checkbox-input-height: 18px;
    --el-checkbox-input-width: 18px;

    .el-checkbox__label {
      font-size: 15px;
    }
  }

  @include bp.respond-to('small') {
    grid-template-columns: repeat(2, 1fr);
  }
}

.rpt-ena-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;

  .el-checkbox {
    height: 32px;
    line-height: 32px;
    font-size: 15px;
    --el-checkbox-input-height: 18px;
    --el-checkbox-input-width: 18px;

    .el-checkbox__label {
      font-size: 15px;
    }
  }
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
