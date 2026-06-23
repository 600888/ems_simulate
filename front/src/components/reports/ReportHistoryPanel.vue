<template>
  <div class="report-history-panel">
    <div class="history-header">
      <span>{{ t('report.history') }}</span>
      <el-tag size="small" type="info">{{ entries.length }}</el-tag>
    </div>
    <el-empty v-if="entries.length === 0" :description="t('report.noData')" />
    <el-table
      v-else
      :data="rows"
      size="small"
      height="100%"
      highlight-current-row
      :row-class-name="rowClassName"
      @row-click="handleRowClick"
    >
      <el-table-column prop="seq_num" :label="t('report.seqNumShort')" width="58" />
      <el-table-column prop="display_time" :label="t('report.time')" min-width="150" />
      <el-table-column prop="value_count" :label="t('report.values')" width="72" align="right" />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { ReportDataEntry } from '@/api/reportApi';

export interface ReportHistoryRow {
  entry_key: string;
  index: number;
  seq_num: number | string;
  display_time: string;
  value_count: number;
}

const props = defineProps<{
  entries: ReportDataEntry[];
  selectedEntryKey?: string | null;
}>();

const emit = defineEmits<{
  (e: 'select', row: ReportHistoryRow): void;
}>();

const { t } = useI18n();

const rows = computed<ReportHistoryRow[]>(() =>
  props.entries.map((entry, index) => ({
    entry_key: makeEntryKey(entry, index),
    index,
    seq_num: entry.seq_num ?? '-',
    display_time: entry.received_at || entry.time_stamp || '-',
    value_count: Object.keys(entry.data_values || {}).length,
  })),
);

function handleRowClick(row: ReportHistoryRow) {
  emit('select', row);
}

function rowClassName({ row }: { row: ReportHistoryRow }) {
  return row.entry_key === props.selectedEntryKey ? 'is-selected-report' : '';
}

function makeEntryKey(entry: ReportDataEntry, index: number): string {
  if (entry.received_at) return `${entry.received_at}|${entry.seq_num}|${index}`;
  return `${entry.rpt_id || ''}|${entry.seq_num}|${index}`;
}
</script>

<style scoped lang="scss">
.report-history-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  border-right: 1px solid #d8dde5;
  background: #f6f8fb;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 38px;
  padding: 0 10px;
  border-bottom: 1px solid #d8dde5;
  color: #263241;
  font-size: 13px;
  font-weight: 600;
}

:deep(.is-selected-report td) {
  background: #d8e8fb !important;
}
</style>
