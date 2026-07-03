<template>
  <aside class="rcb-tree-panel">
    <div class="rcb-tree-header">
      <el-input
        v-model="searchText"
        :placeholder="t('common.searchPlaceholder')"
        clearable
        class="rcb-search"
        :prefix-icon="Search"
      />
      <div class="rcb-select-actions" v-if="showCheckbox">
        <el-checkbox
          :model-value="selectAllModel"
          :indeterminate="isIndeterminate"
          @change="handleSelectAllChange"
        >
          {{ t('report.selectAll') }}
        </el-checkbox>
        <span class="selected-count">{{ t('report.selectedCount', { count: (props.checkedRefs || []).length }) }}</span>
      </div>
    </div>
    <el-tree
      ref="treeRef"
      :data="treeData"
      :props="treeProps"
      node-key="ref"
      default-expand-all
      highlight-current
      :current-node-key="selectedRef"
      :filter-node-method="filterNode"
      :show-checkbox="showCheckbox"
      :check-strictly="false"
      @node-click="handleNodeClick"
      @check="handleCheck"
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
import { computed, nextTick, ref, watch } from 'vue';
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
  showCheckbox?: boolean;
  checkedRefs?: string[];
}>();

const emit = defineEmits<{
  (e: 'select', rcb: RcbInfo): void;
  (e: 'update:checkedRefs', refs: string[]): void;
}>();

const { t } = useI18n();
const searchText = ref('');
const treeRef = ref<InstanceType<typeof ElTree> | null>(null);
const treeProps = { children: 'children', label: 'label' };

const rcbRefs = computed<string[]>(() => props.rcbs.map((r) => r.ref));
const rcbRefSet = computed(() => new Set(rcbRefs.value));

const selectAllModel = computed(() =>
  (props.checkedRefs || []).length === rcbRefs.value.length && rcbRefs.value.length > 0,
);

const isIndeterminate = computed(() => {
  const checked = props.checkedRefs || [];
  return checked.length > 0 && checked.length < rcbRefs.value.length;
});

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

// Sync checked state only when it actually came from outside the tree. Element Plus
// emits `check-change` once for every affected node, so using that event here made a
// select-all operation repeatedly scan and write back the entire selection.
watch(
  [() => props.checkedRefs, rcbRefs],
  ([newRefs]) => {
    nextTick(() => {
      syncTreeCheckedRefs(newRefs || []);
    });
  },
);

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

interface TreeCheckState {
  checkedKeys: Array<string | number>;
}

function getRcbKeys(keys: Array<string | number>): string[] {
  return keys
    .map(String)
    .filter((key) => rcbRefSet.value.has(key));
}

function hasSameCheckedRefs(refs: string[]): boolean {
  if (!treeRef.value) return false;
  const currentRefs = getRcbKeys(treeRef.value.getCheckedKeys(false) as Array<string | number>);
  if (currentRefs.length !== refs.length) return false;
  const expected = new Set(refs);
  return currentRefs.every((key) => expected.has(key));
}

function syncTreeCheckedRefs(refs: string[]) {
  if (!treeRef.value) return;
  const validRefs = refs.filter((key) => rcbRefSet.value.has(key));
  if (hasSameCheckedRefs(validRefs)) return;

  if (validRefs.length === rcbRefs.value.length && validRefs.length > 0) {
    // Checking top-level nodes avoids Element Plus' quadratic leaf-key lookup.
    treeRef.value.setCheckedKeys(treeData.value.map((node) => node.ref));
  } else {
    treeRef.value.setCheckedKeys(validRefs);
  }
}

function handleCheck(_data: RcbTreeNode, state: TreeCheckState) {
  // The `check` event fires once per user action, after the cascade is complete.
  const rcbKeys = getRcbKeys(state.checkedKeys);
  emit('update:checkedRefs', rcbKeys);
}

function handleSelectAllChange(value: boolean) {
  const refs = value ? [...rcbRefs.value] : [];
  syncTreeCheckedRefs(refs);
  emit('update:checkedRefs', refs);
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

.rcb-tree-header {
  margin-bottom: 10px;
}

.rcb-search {
  margin-bottom: 8px;
}

.rcb-select-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 2px;

  .el-checkbox {
    height: 24px;
    font-size: 13px;

    --el-checkbox-input-height: 16px;
    --el-checkbox-input-width: 16px;

    :deep(.el-checkbox__label) {
      font-size: 13px;
    }
  }
}

.selected-count {
  color: #5d6876;
  font-size: 12px;
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

// 强制树节点复选框保持方形，防止全局样式干扰
.el-tree {
  :deep(.el-checkbox__inner) {
    border-radius: 2px;
  }
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
