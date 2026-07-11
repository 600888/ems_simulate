<template>
  <div class="dataset-table">
    <el-empty v-if="!values.length" description="尚未收到 GOOSE 数据" />
    <el-table
      v-else
      :data="values"
      border
      size="small"
      height="100%"
      :row-class-name="rowClass"
    >
      <el-table-column prop="index" label="#" width="55" align="center" />
      <el-table-column prop="name" label="数据引用" min-width="260" show-overflow-tooltip>
        <template #default="{ row }">{{ row.name || `Entry[${row.index}]` }}</template>
      </el-table-column>
      <el-table-column
        prop="description"
        label="描述"
        min-width="150"
        show-overflow-tooltip
      />
      <el-table-column prop="fc" label="FC" width="70" align="center" />
      <el-table-column prop="type" label="类型" width="105" />
      <el-table-column label="前值" min-width="120"
        ><template #default="{ row }">{{
          formatValue(row.previous_value)
        }}</template></el-table-column
      >
      <el-table-column label="当前值" min-width="140">
        <template #default="{ row }"
          ><strong>{{ formatValue(row.value) }}</strong
          ><el-tag v-if="row.changed" type="warning" size="small" class="changed-tag"
            >已变化</el-tag
          ></template
        >
      </el-table-column>
    </el-table>
  </div>
</template>
<script setup lang="ts">
import type { GooseSubscriptionDataValue } from "@/api/gooseApi";
defineProps<{ values: GooseSubscriptionDataValue[] }>();
function formatValue(value: unknown) {
  if (value === null || value === undefined) return "-";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
function rowClass({ row }: { row: GooseSubscriptionDataValue }) {
  return row.changed ? "changed-row" : "";
}
</script>
<style scoped lang="scss">
.dataset-table {
  height: 100%;
  min-height: 280px;
}
.changed-tag {
  margin-left: 8px;
}
:deep(.changed-row td) {
  animation: changedFlash 2.2s ease-out;
}
@keyframes changedFlash {
  0%,
  45% {
    background: #fff1b8;
  }
  100% {
    background: transparent;
  }
}
</style>
