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
        <div class="rcb-selection-controls">
          <el-checkbox
            :model-value="selectAllModel"
            :indeterminate="isIndeterminate"
            @change="handleSelectAllChange"
          >
            {{ t("report.selectAll") }}
          </el-checkbox>
          <el-select
            v-if="instanceOptions.length > 1"
            :model-value="selectedInstanceIndex"
            :placeholder="t('report.selectByInstance')"
            clearable
            size="small"
            class="rcb-instance-select"
            @change="handleInstanceSelect"
          >
            <el-option
              v-for="option in instanceOptions"
              :key="option.index"
              :label="
                t('report.reportInstance', {
                  index: option.index,
                  count: option.refs.length,
                })
              "
              :value="option.index"
            />
          </el-select>
        </div>
        <span class="selected-count">{{
          t("report.selectedCount", { count: (props.checkedRefs || []).length })
        }}</span>
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
          <el-icon
            v-if="data.isRcb && data.locked"
            class="rcb-lock-icon"
            :title="t('report.lockedByOtherClient')"
          >
            <Lock />
          </el-icon>
          <span v-else-if="data.rpt_ena" class="rcb-status-dot" />
        </span>
      </template>
    </el-tree>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Lock, Search } from "@element-plus/icons-vue";
import type { ElTree } from "element-plus";
import type { RcbInfo } from "@/api/reportApi";

interface RcbTreeNode {
  ref: string;
  label: string;
  children?: RcbTreeNode[];
  isRcb?: boolean;
  rcb_type?: string;
  rpt_ena?: boolean;
  locked?: boolean;
}

const props = defineProps<{
  rcbs: RcbInfo[];
  selectedRef?: string;
  showCheckbox?: boolean;
  checkedRefs?: string[];
}>();

const emit = defineEmits<{
  (e: "select", rcb: RcbInfo): void;
  (e: "update:checkedRefs", refs: string[]): void;
}>();

const { t } = useI18n();
const searchText = ref("");
const treeRef = ref<InstanceType<typeof ElTree> | null>(null);
const treeProps = { children: "children", label: "label" };

const rcbRefs = computed<string[]>(() => props.rcbs.map((r) => r.ref));
const rcbRefSet = computed(() => new Set(rcbRefs.value));

const selectAllModel = computed(
  () =>
    (props.checkedRefs || []).length === rcbRefs.value.length &&
    rcbRefs.value.length > 0,
);

const isIndeterminate = computed(() => {
  const checked = props.checkedRefs || [];
  return checked.length > 0 && checked.length < rcbRefs.value.length;
});

const treeData = computed<RcbTreeNode[]>(() => {
  const ldMap = new Map<string, Map<string, RcbTreeNode[]>>();

  for (const rcb of props.rcbs) {
    const ldName = rcb.ld || "Unknown";
    const lnName = rcb.ln || "LLN0";
    if (!ldMap.has(ldName)) ldMap.set(ldName, new Map());
    const lnMap = ldMap.get(ldName)!;
    if (!lnMap.has(lnName)) lnMap.set(lnName, []);
    lnMap.get(lnName)!.push({
      ref: rcb.ref,
      label: rcb.name,
      isRcb: true,
      rcb_type: rcb.rcb_type,
      rpt_ena: rcb.rpt_ena,
      locked: rcb.locked,
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
watch([() => props.checkedRefs, rcbRefs], ([newRefs]) => {
  nextTick(() => {
    syncTreeCheckedRefs(newRefs || []);
  });
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
  if (rcb) emit("select", rcb);
}

interface TreeCheckState {
  checkedKeys: Array<string | number>;
}

interface RcbInstanceOption {
  index: number;
  refs: string[];
}

interface RcbInstanceCandidate {
  rcb: RcbInfo;
  candidateIndex: number;
  candidateGroup: string;
  hasInstanceSuffix: boolean;
  matchesReportId: boolean;
}

function getReportIdName(rptId: string): string {
  const parts = rptId.split(/[.$/]/).filter(Boolean);
  return parts[parts.length - 1] || "";
}

const instanceOptions = computed<RcbInstanceOption[]>(() => {
  const candidates: RcbInstanceCandidate[] = props.rcbs.map((rcb) => {
    const suffixMatch = rcb.name.match(/^(.*?)(\d{2})$/);
    const baseName = suffixMatch?.[1] || rcb.name;
    const candidateIndex = suffixMatch ? Number(suffixMatch[2]) : 1;
    const candidateGroup = [rcb.ld, rcb.ln, rcb.rcb_type, baseName].join(
      "\u0000",
    );
    return {
      rcb,
      candidateIndex,
      candidateGroup,
      hasInstanceSuffix: !!suffixMatch && candidateIndex > 0,
      matchesReportId:
        !!suffixMatch && getReportIdName(rcb.rpt_id || "") === baseName,
    };
  });

  const candidateGroupSizes = new Map<string, number>();
  for (const candidate of candidates) {
    candidateGroupSizes.set(
      candidate.candidateGroup,
      (candidateGroupSizes.get(candidate.candidateGroup) || 0) + 1,
    );
  }

  const refsByIndex = new Map<number, string[]>();
  for (const candidate of candidates) {
    const isExpandedInstance =
      candidate.hasInstanceSuffix &&
      (candidate.matchesReportId ||
        (candidateGroupSizes.get(candidate.candidateGroup) || 0) > 1);
    const index = isExpandedInstance ? candidate.candidateIndex : 1;
    const refs = refsByIndex.get(index) || [];
    refs.push(candidate.rcb.ref);
    refsByIndex.set(index, refs);
  }

  return Array.from(refsByIndex.entries())
    .sort(([left], [right]) => left - right)
    .map(([index, refs]) => ({ index, refs }));
});

const selectedInstanceIndex = computed<number | undefined>(() => {
  const checkedRefs = props.checkedRefs || [];
  if (checkedRefs.length === 0) return undefined;
  return instanceOptions.value.find((option) =>
    isSameRefSelection(option.refs, checkedRefs),
  )?.index;
});

function getRcbKeys(keys: Array<string | number>): string[] {
  return keys.map(String).filter((key) => rcbRefSet.value.has(key));
}

function isSameRefSelection(left: string[], right: string[]): boolean {
  if (left.length !== right.length) return false;
  const rightSet = new Set(right);
  return left.every((ref) => rightSet.has(ref));
}

function hasSameCheckedRefs(refs: string[]): boolean {
  if (!treeRef.value) return false;
  const currentRefs = getRcbKeys(
    treeRef.value.getCheckedKeys(false) as Array<string | number>,
  );
  return isSameRefSelection(currentRefs, refs);
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
  emit("update:checkedRefs", rcbKeys);
}

function handleSelectAllChange(value: boolean) {
  const refs = value ? [...rcbRefs.value] : [];
  syncTreeCheckedRefs(refs);
  emit("update:checkedRefs", refs);
}

function handleInstanceSelect(index?: number) {
  const refs =
    instanceOptions.value.find((option) => option.index === index)?.refs || [];
  syncTreeCheckedRefs(refs);
  emit("update:checkedRefs", [...refs]);
}
</script>

<style scoped lang="scss">
.rcb-tree-panel {
  width: 320px;
  min-width: 320px;
  min-height: 0;
  border-right: 1px solid var(--border-color);
  background: var(--bg-subtle);
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
  gap: 8px;
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

.rcb-selection-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.rcb-instance-select {
  width: 138px;
}

.selected-count {
  color: #5d6876;
  font-size: 12px;
  flex: 0 0 auto;
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
  color: var(--text-primary);
}

.rcb-label.is-enabled {
  font-weight: 600;
}

.rcb-lock-icon {
  color: #d48806;
  font-size: 16px;
  flex: 0 0 auto;
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
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;

  &::before {
    content: "";
    display: block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #2f9e44;
    flex: 0 0 auto;
  }
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
    border-bottom: 1px solid var(--border-color);
  }
}
</style>
