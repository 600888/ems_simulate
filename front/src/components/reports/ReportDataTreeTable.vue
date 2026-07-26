<template>
  <div class="report-tree-table" v-loading="loading">
    <el-empty
      v-if="!loading && treeItems.length === 0"
      :description="t('report.noData')"
    />
    <el-table
      v-else
      :data="treeItems"
      row-key="id"
      border
      size="small"
      height="100%"
      default-expand-all
      :tree-props="{ children: 'children' }"
      class="ied-table"
    >
      <el-table-column
        :label="t('report.treeName')"
        prop="label"
        min-width="260"
      >
        <template #default="{ row }">
          <span class="name-cell">
            <span class="node-badge" :class="`type-${row.node_type}`">
              {{ nodeBadge(row.node_type) }}
            </span>
            <span class="node-label" :title="row.raw_ref || row.label">{{
              row.label
            }}</span>
          </span>
        </template>
      </el-table-column>
      <el-table-column
        :label="t('table.fc')"
        prop="fc"
        width="78"
        align="center"
      >
        <template #default="{ row }">
          <span v-if="row.fc" class="fc-badge">{{ row.fc }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="t('report.reason')" prop="reason" width="150">
        <template #default="{ row }">
          <el-tag v-if="row.reason" size="small" :type="reasonType(row.reason)">
            {{ row.reason }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="t('report.value')" prop="value" min-width="180">
        <template #default="{ row }">
          <span class="value-text" :title="formatValue(row.value)">
            {{ formatValue(row.value) }}
          </span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from "vue-i18n";
import type { ReportTreeNode } from "@/api/reportApi";

defineProps<{
  treeItems: ReportTreeNode[];
  loading?: boolean;
}>();

const { t } = useI18n();

function nodeBadge(type: string): string {
  const map: Record<string, string> = {
    ld: "LD",
    ln: "LN",
    do: "DO",
    da: "DA",
    bda: "",
    group: "",
    value: "",
  };
  return map[type] ?? "";
}

function reasonType(
  reason: string,
): "success" | "warning" | "primary" | "info" {
  if (reason === "gi") return "success";
  if (reason === "data-change") return "warning";
  if (reason === "integrity") return "primary";
  return "info";
}

function formatValue(value: any): string {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
</script>

<style scoped lang="scss">
.report-tree-table {
  height: 100%;
  min-height: 260px;
}

.ied-table {
  --el-table-border-color: var(--border-color);
  --el-table-header-bg-color: var(--table-header-bg);
  --el-table-tr-bg-color: var(--table-row-bg);
  --el-table-row-hover-bg-color: var(--table-hover-bg);
  color: var(--text-primary);
  font-size: 14px;
}

:deep(.el-table__header th) {
  height: 32px;
  background: var(--table-header-bg) !important;
  color: var(--text-primary);
  font-weight: 600;
}

:deep(.el-table__row) {
  height: 36px;
}

:deep(.el-table__cell) {
  padding: 4px 0;
}

.name-cell {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.node-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 22px;
  border-radius: 2px;
  padding: 0 4px;
  background: transparent;
  color: transparent;
  font-size: 12px;
  font-weight: 700;
}

.node-badge.type-do,
.node-badge.type-da {
  background: #1976d2;
  color: #fff;
}

.node-badge.type-ld,
.node-badge.type-ln {
  background: #5f6f82;
  color: #fff;
}

.node-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
}

.fc-badge {
  font-family: Consolas, Monaco, monospace;
  font-size: 13px;
  color: #111827;
}

.value-text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
}
</style>
