<template>
  <div class="report-history-panel">
    <div class="history-header">
      <span>{{ t("report.history") }}</span>
      <el-tag size="small" type="info">{{ entries.length }}</el-tag>
    </div>
    <el-empty
      v-if="!loading && entries.length === 0"
      :description="t('report.noData')"
    />
    <el-table
      v-else
      v-loading="loading"
      :data="rows"
      size="small"
      height="100%"
      highlight-current-row
      :row-class-name="rowClassName"
      @row-click="handleRowClick"
    >
      <el-table-column
        prop="seq_num"
        :label="t('report.seqNumShort')"
        width="58"
      />
      <el-table-column
        prop="display_time"
        :label="t('report.time')"
        min-width="150"
      />
      <el-table-column
        prop="value_count"
        :label="t('report.values')"
        width="72"
        align="right"
      />
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import type { ReportEntrySummary } from "@/api/reportApi";

export interface ReportHistoryRow {
  entry_key: string;
  index: number;
  seq_num: number | string;
  display_time: string;
  value_count: number;
}

const props = defineProps<{
  entries: ReportEntrySummary[];
  selectedEntryKey?: string | null;
  loading?: boolean;
}>();

const emit = defineEmits<{
  (e: "select", row: ReportHistoryRow): void;
}>();

const { t } = useI18n();

const rows = computed<ReportHistoryRow[]>(() =>
  props.entries.map((entry, index) => ({
    entry_key: entry.entry_key,
    index: entry.index ?? index,
    seq_num: entry.seq_num ?? "-",
    display_time: entry.received_at || entry.time_stamp || "-",
    value_count: entry.value_count,
  })),
);

function handleRowClick(row: ReportHistoryRow) {
  emit("select", row);
}

function rowClassName({ row }: { row: ReportHistoryRow }) {
  return row.entry_key === props.selectedEntryKey ? "is-selected-report" : "";
}
</script>

<style scoped lang="scss">
.report-history-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  border-right: 1px solid var(--border-color);
  background: var(--bg-subtle);
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 38px;
  padding: 0 10px;
  border-bottom: 1px solid var(--border-color);
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

:deep(.is-selected-report td) {
  background: #d8e8fb !important;
}
</style>
