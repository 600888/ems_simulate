<template>
  <div class="scl-diff-result">
    <div class="diff-stats">
      <el-tag type="success" size="small" class="stat-tag"
        >+{{ diffResult.additions }} {{ $t("scl.added") }}</el-tag
      >
      <el-tag type="danger" size="small" class="stat-tag"
        >-{{ diffResult.deletions }} {{ $t("scl.deleted") }}</el-tag
      >
      <el-tag type="warning" size="small" class="stat-tag"
        >±{{ diffResult.modifications }} {{ $t("scl.modified") }}</el-tag
      >
      <span class="stat-summary">{{
        $t("scl.diffStats", {
          add: diffResult.additions,
          del: diffResult.deletions,
          mod: diffResult.modifications,
        })
      }}</span>
    </div>

    <div class="diff-panels">
      <div class="diff-panel">
        <div class="panel-header">{{ fileA }}</div>
        <SclTreePanel
          :tree-data="treeA"
          :diff-mode="true"
          :highlight-nodes="changedPaths"
        />
      </div>
      <div class="diff-panel">
        <div class="panel-header">{{ fileB }}</div>
        <SclTreePanel
          :tree-data="treeB"
          :diff-mode="true"
          :highlight-nodes="changedPaths"
        />
      </div>
    </div>

    <div class="diff-details">
      <el-table :data="diffResult.details" size="small" stripe max-height="200">
        <el-table-column prop="path" :label="$t('scl.path')" min-width="200" />
        <el-table-column :label="$t('scl.pointCategory')" width="80">
          <template #default="{ row }">
            <el-tag
              :type="
                row.type === 'added'
                  ? 'success'
                  : row.type === 'deleted'
                    ? 'danger'
                    : 'warning'
              "
              size="small"
            >
              {{
                row.type === "added"
                  ? $t("scl.diffAdded")
                  : row.type === "deleted"
                    ? $t("scl.diffDeleted")
                    : $t("scl.diffModified")
              }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column
          prop="left_value"
          :label="$t('scl.diffValueA', { file: fileA })"
          min-width="150"
        />
        <el-table-column
          prop="right_value"
          :label="$t('scl.diffValueB', { file: fileB })"
          min-width="150"
        />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type {
  SclDiffResult as SclDiffResultType,
  SclTreeNode,
} from "@/api/sclApi";
import SclTreePanel from "./SclTreePanel.vue";

const props = defineProps<{
  diffResult: SclDiffResultType;
  treeA: SclTreeNode[];
  treeB: SclTreeNode[];
  fileA: string;
  fileB: string;
}>();

const changedPaths = computed(() =>
  props.diffResult.details.map((d) => d.path),
);
</script>

<style scoped>
.scl-diff-result {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.diff-stats {
  display: flex;
  align-items: center;
  gap: 8px;
}
.stat-tag {
  font-size: 12px;
}
.stat-summary {
  font-size: 13px;
  color: var(--text-secondary);
  margin-left: 8px;
}
.diff-panels {
  display: flex;
  gap: 8px;
}
.diff-panel {
  flex: 1;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  overflow: hidden;
}
.panel-header {
  padding: 6px 12px;
  background: var(--bg-muted);
  font-weight: 600;
  font-size: 12px;
  border-bottom: 1px solid var(--border-color);
}
.diff-details {
  margin-top: 8px;
}
</style>
