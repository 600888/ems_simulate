<template>
  <div class="report-control-panel">
    <el-empty v-if="!rcb" :description="t('report.noRcbs')" />
    <template v-else>
      <el-descriptions :column="2" border size="small" label-width="150px">
        <el-descriptions-item :label="`${t('report.name')} (Name)`">
          {{ rcb.name }}
        </el-descriptions-item>
        <el-descriptions-item :label="`${t('report.rcbType')} (Type)`">
          <el-tag :type="rcb.rcb_type === 'BRCB' ? 'primary' : 'warning'" size="small">
            {{ rcb.rcb_type }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="t('report.ref')" :span="2">
          <span class="ref-text" :title="rcb.ref">{{ rcb.ref || '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item :label="`${t('report.rptId')} (RptID)`">
          {{ rcb.rpt_id || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="`${t('report.dataSet')} (DatSet)`">
          {{ rcb.data_set_ref || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="`${t('report.confRev')} (ConfRev)`">
          {{ rcb.conf_rev }}
        </el-descriptions-item>
        <el-descriptions-item :label="`${t('report.sqNum')} (SqNum)`">
          {{ rcb.sq_num ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="`${t('report.rptEna')} (RptEna)`">
          <el-tag :type="rcb.rpt_ena ? 'success' : 'danger'" size="small">
            {{ rcb.rpt_ena ? t('report.enabled') : t('report.disabled') }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item :label="`${t('report.bufTime')} (BufTm)`">
          {{ rcb.buf_time }} ms
        </el-descriptions-item>
        <el-descriptions-item :label="`${t('report.intgPeriod')} (IntgPd)`">
          {{ rcb.intg_period }} ms
        </el-descriptions-item>
        <el-descriptions-item v-if="rcb.rcb_type === 'BRCB'" :label="`${t('report.entryId')} (EntryID)`">
          {{ rcb.entry_id || '-' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="rcb.rcb_type === 'BRCB'" :label="`${t('report.timeOfEntry')} (TimeOfEntry)`">
          {{ rcb.time_of_entry || '-' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="rcb.rcb_type === 'URCB'" :label="`${t('report.owner')} (Owner)`">
          {{ rcb.owner || '-' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="rcb.rcb_type === 'URCB'" :label="`${t('report.resv')} (Resv)`">
          {{ rcb.resv ? 'True' : 'False' }}
        </el-descriptions-item>
      </el-descriptions>

      <section class="control-section">
        <div class="section-title">{{ t('report.reportConfig') }}</div>
        <div class="rpt-row">
          <el-checkbox v-model="rptEnaModel">
            {{ t('report.rptEnaToggle') }}
          </el-checkbox>
          <el-tag :type="rcb.rpt_ena ? 'success' : 'danger'" size="small">
            {{ rcb.rpt_ena ? t('report.enabled') : t('report.disabled') }}
          </el-tag>
        </div>
      </section>

      <section class="control-section" :class="{ 'is-disabled': rcb.rpt_ena }">
        <el-alert
          v-if="rcb.rpt_ena"
          :title="t('report.configFieldsDisabledHint')"
          type="warning"
          :closable="false"
          show-icon
          class="config-disabled-alert"
        />

        <div class="section-title">{{ t('report.trgOps') }}</div>
        <el-checkbox-group v-model="trgOpsModel" class="checkbox-grid">
          <el-checkbox v-for="item in trgOpsOptions" :key="item.value" :label="item.value" :disabled="rcb.rpt_ena">
            {{ item.label }}
          </el-checkbox>
        </el-checkbox-group>

        <div class="section-title">{{ t('report.optFields') }}</div>
        <el-checkbox-group v-model="optFieldsModel" class="checkbox-grid">
          <el-checkbox v-for="item in optFieldOptions" :key="item.value" :label="item.value" :disabled="rcb.rpt_ena">
            {{ item.label }}
          </el-checkbox>
        </el-checkbox-group>
      </section>

      <div class="action-row">
        <el-button type="primary" :loading="actionLoading" @click="handleApply">
          {{ t('report.applyConfig') }}
        </el-button>
        <el-button type="warning" :disabled="!rcb.rpt_ena" :loading="giLoading" @click="emit('gi')">
          {{ t('report.gi') }}
        </el-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import type { OptFields, RcbInfo, TrgOps } from '@/api/reportApi';

const props = defineProps<{
  rcb: RcbInfo | null;
  actionLoading?: boolean;
  giLoading?: boolean;
}>();

const emit = defineEmits<{
  (e: 'apply', payload: { rptEna: boolean; trgOps: TrgOps; optFields: OptFields }): void;
  (e: 'gi'): void;
}>();

const { t } = useI18n();
const rptEnaModel = ref(false);
const trgOpsModel = ref<string[]>([]);
const optFieldsModel = ref<string[]>([]);

const trgOpsOptions = computed(() => [
  { value: 'dchg', label: `${t('report.dchg')} (dchg)` },
  { value: 'qchg', label: `${t('report.qchg')} (qchg)` },
  { value: 'dupd', label: `${t('report.dupd')} (dupd)` },
  { value: 'period', label: `${t('report.period')} (period)` },
  { value: 'gi', label: `${t('report.giLabel')} (gi)` },
]);

const optFieldOptions = computed(() => [
  { value: 'seq_num', label: `${t('report.seqNum')} (seqNum)` },
  { value: 'time_stamp', label: `${t('report.timeStamp')} (timeStamp)` },
  { value: 'data_set', label: `${t('report.dataSetField')} (dataSet)` },
  { value: 'reason_code', label: `${t('report.reasonCode')} (reasonCode)` },
  { value: 'data_ref', label: `${t('report.dataRef')} (dataRef)` },
  { value: 'entry_id', label: `${t('report.entryId')} (entryID)` },
  { value: 'config_ref', label: `${t('report.configRef')} (configRef)` },
  { value: 'buf_ovfl', label: `${t('report.bufOvfl')} (bufOvfl)` },
]);

watch(
  () => props.rcb,
  () => syncModels(),
  { immediate: true },
);

function syncModels() {
  if (!props.rcb) {
    rptEnaModel.value = false;
    trgOpsModel.value = [];
    optFieldsModel.value = [];
    return;
  }
  rptEnaModel.value = !!props.rcb.rpt_ena;
  trgOpsModel.value = Object.entries(props.rcb.trg_ops || {})
    .filter(([, value]) => value)
    .map(([key]) => key);
  optFieldsModel.value = Object.entries(props.rcb.opt_fields || {})
    .filter(([, value]) => value)
    .map(([key]) => key);
}

function handleApply() {
  emit('apply', {
    rptEna: rptEnaModel.value,
    trgOps: {
      dchg: trgOpsModel.value.includes('dchg'),
      qchg: trgOpsModel.value.includes('qchg'),
      dupd: trgOpsModel.value.includes('dupd'),
      period: trgOpsModel.value.includes('period'),
      gi: trgOpsModel.value.includes('gi'),
    },
    optFields: {
      seq_num: optFieldsModel.value.includes('seq_num'),
      time_stamp: optFieldsModel.value.includes('time_stamp'),
      data_set: optFieldsModel.value.includes('data_set'),
      reason_code: optFieldsModel.value.includes('reason_code'),
      data_ref: optFieldsModel.value.includes('data_ref'),
      entry_id: optFieldsModel.value.includes('entry_id'),
      config_ref: optFieldsModel.value.includes('config_ref'),
      buf_ovfl: optFieldsModel.value.includes('buf_ovfl'),
    },
  });
}
</script>

<style scoped lang="scss">
.report-control-panel {
  min-height: 0;
}

.ref-text {
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  word-break: break-all;
}

.control-section {
  margin-top: 14px;
  padding: 12px;
  border: 1px solid #e3e8ef;
  background: #fbfcfe;
}

.control-section.is-disabled {
  background: #f3f5f8;
}

.section-title {
  margin: 0 0 8px;
  color: #263241;
  font-size: 13px;
  font-weight: 700;
}

.rpt-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.checkbox-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 6px 12px;
  margin-bottom: 10px;

  .el-checkbox {
    height: 32px;
    margin-right: 0;
    font-size: 15px;
    line-height: 32px;

    --el-checkbox-input-height: 18px;
    --el-checkbox-input-width: 18px;

    :deep(.el-checkbox__label) {
      font-size: 15px;
    }
  }
}

.rpt-row {
  .el-checkbox {
    height: 32px;
    font-size: 15px;
    line-height: 32px;

    --el-checkbox-input-height: 18px;
    --el-checkbox-input-width: 18px;

    :deep(.el-checkbox__label) {
      font-size: 15px;
    }
  }
}

.config-disabled-alert {
  margin-bottom: 12px;
}

.action-row {
  display: flex;
  gap: 10px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #e3e8ef;
}

@include bp.respond-to("small") {
  .checkbox-grid {
    grid-template-columns: repeat(2, minmax(110px, 1fr));
  }
}
</style>


