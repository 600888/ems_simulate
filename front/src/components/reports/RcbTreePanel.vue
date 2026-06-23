<template>
  <aside class="rcb-tree-panel">
    <el-input
      v-model="searchText"
      :placeholder="t('common.searchPlaceholder')"
      clearable
      class="rcb-search"
      :prefix-icon="Search"
    />
    <el-tree
      ref="treeRef"
      :data="treeData"
      :props="treeProps"
      node-key="ref"
      default-expand-all
      highlight-current
      :current-node-key="selectedRef"
      :filter-node-method="filterNode"
      @node-click="handleNodeClick"
    >
      <template #default="{ node, data }">
        <span class="rcb-tree-node">
          <span v-if="data.isRcb" class="rcb-type-badge" :class="data.rcb_type">
            {{ data.rcb_type }}
          </span>
          <span class="rcb-label" :class="{ 'is-enabled': data.rpt_ena }">
            {{ node.label }}
          </span>
          <span v-if="data.rpt_ena" class="rcb-status-dot" />
        </span>
      </template>
    </el-tree>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { Search } from '@element-plus/icons-vue';
import type { ElTree } from 'element-plus';
import type { RcbInfo } from '@/api/reportApi';

interface RcbTreeNode {
  ref: string;
  label: string;
  children?: RcbTreeNode[];
  isRcb?: boolean;
  rcb_type?: string;
  rpt_ena?: boolean;
}

const props = defineProps<{
  rcbs: RcbInfo[];
  selectedRef?: string;
}>();

const emit = defineEmits<{
  (e: 'select', rcb: RcbInfo): void;
}>();

const { t } = useI18n();
const searchText = ref('');
const treeRef = ref<InstanceType<typeof ElTree> | null>(null);
const treeProps = { children: 'children', label: 'label' };

const treeData = computed<RcbTreeNode[]>(() => {
  const ldMap = new Map<string, Map<string, RcbTreeNode[]>>();

  for (const rcb of props.rcbs) {
    const ldName = rcb.ld || 'Unknown';
    const lnName = rcb.ln || 'LLN0';
    if (!ldMap.has(ldName)) ldMap.set(ldName, new Map());
    const lnMap = ldMap.get(ldName)!;
    if (!lnMap.has(lnName)) lnMap.set(lnName, []);
    lnMap.get(lnName)!.push({
      ref: rcb.ref,
      label: rcb.name,
      isRcb: true,
      rcb_type: rcb.rcb_type,
      rpt_ena: rcb.rpt_ena,
    });
  }

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

watch(searchText, (value) => {
  treeRef.value?.filter(value);
});

watch(
  () => props.selectedRef,
  (value) => {
    if (value) treeRef.value?.setCurrentKey(value);
  },
);

function filterNode(value: string, data: RcbTreeNode): boolean {
  if (!value) return true;
  return data.label.toLowerCase().includes(value.toLowerCase());
}

function handleNodeClick(data: RcbTreeNode) {
  if (!data.isRcb) return;
  const rcb = props.rcbs.find((item) => item.ref === data.ref);
  if (rcb) emit('select', rcb);
}
</script>

<style scoped lang="scss">
.rcb-tree-panel {
  width: 320px;
  min-width: 320px;
  min-height: 0;
  border-right: 1px solid #d8dde5;
  background: #f7f9fc;
  padding: 10px;
  overflow: auto;
}

.rcb-search {
  margin-bottom: 10px;
}

.rcb-tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.rcb-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #263241;
}

.rcb-label.is-enabled {
  font-weight: 600;
}

.rcb-type-badge {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 5px;
  border-radius: 2px;
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
  color: #fff;
  background: #1f7dd8;
}

.rcb-type-badge.URCB {
  background: #b56a17;
}

.rcb-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #2f9e44;
  flex: 0 0 auto;
}

@include bp.respond-to("small") {
  .rcb-tree-panel {
    width: 100%;
    min-width: 0;
    max-height: 220px;
    border-right: none;
    border-bottom: 1px solid #d8dde5;
  }
}
</style>
