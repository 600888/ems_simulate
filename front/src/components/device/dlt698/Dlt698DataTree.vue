<template>
  <el-tree
    :data="nodes"
    default-expand-all
    :expand-on-click-node="false"
    node-key="id"
  >
    <template #default="{ data }"
      ><span class="typed-value"
        ><span>{{ data.label }}</span
        ><el-tag size="small" effect="plain">{{ data.type }}</el-tag
        ><code>{{ data.value }}</code></span
      ></template
    >
  </el-tree>
</template>
<script setup lang="ts">
import { computed } from "vue";
import type { Dlt698Data } from "@/types/dlt698";
import { dataText } from "@/utils/dlt698";
const props = defineProps<{ data: Dlt698Data }>();
type Node = {
  id: string;
  label: string;
  type: string;
  value: string;
  children?: Node[];
};
function node(data: Dlt698Data, id: string, label: string): Node {
  return {
    id,
    label,
    type: data.type,
    value: dataText(data),
    children: Array.isArray(data.value)
      ? data.value.map((child, i) => node(child, `${id}.${i}`, `[${i + 1}]`))
      : undefined,
  };
}
const nodes = computed(() => [node(props.data, "root", "Data")]);
</script>
<style scoped>
.typed-value {
  display: flex;
  gap: 12px;
  align-items: center;
}
code {
  font-variant-numeric: tabular-nums;
}
</style>
