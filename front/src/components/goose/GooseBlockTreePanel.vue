<template>
  <aside class="goose-tree-panel">
    <div class="tree-header">
      <el-input
        v-model="search"
        clearable
        :placeholder="$t('goose.searchBlocks')"
        :prefix-icon="Search"
      />
      <div v-if="batchMode" class="batch-row">
        <el-checkbox v-model="selectAll" :indeterminate="indeterminate">{{
          $t("goose.selectAll")
        }}</el-checkbox>
        <span>{{ $t("goose.selected") }} {{ checkedKeys.length }}</span>
      </div>
    </div>
    <el-tree
      ref="treeRef"
      :data="treeData"
      node-key="key"
      default-expand-all
      highlight-current
      :filter-node-method="filterNode"
      :show-checkbox="batchMode"
      :check-strictly="false"
      @node-click="selectNode"
      @check="handleCheck"
    >
      <template #default="{ data }">
        <span class="tree-node">
          <span
            v-if="data.isBlock"
            class="state-dot"
            :class="stateClass(data.block)"
          />
          <span v-if="data.isBlock" class="block-kind" :class="data.block.kind">
            {{ data.block.kind === "publisher" ? "PUB" : "SUB" }}
          </span>
          <span v-else class="node-badge">{{ data.kind }}</span>
          <span :class="{ enabled: data.block?.enabled }">{{
            data.label
          }}</span>
          <span
            v-if="data.isBlock && data.block.message_count"
            class="message-count"
          >
            {{ data.block.message_count }}
          </span>
        </span>
      </template>
    </el-tree>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { Search } from "@element-plus/icons-vue";
import type { ElTree } from "element-plus";
import type { GooseBlockItem } from "./gooseWorkbench";

interface TreeNode {
  key: string;
  label: string;
  kind?: string;
  isBlock?: boolean;
  block?: GooseBlockItem;
  children?: TreeNode[];
}

const props = defineProps<{
  blocks: GooseBlockItem[];
  selectedKey?: string;
  batchMode?: boolean;
}>();
const emit = defineEmits<{
  (e: "select", block: GooseBlockItem): void;
  (e: "checked", keys: string[]): void;
}>();
const search = ref("");
const treeRef = ref<InstanceType<typeof ElTree>>();
const checkedKeys = ref<string[]>([]);

const treeData = computed<TreeNode[]>(() => {
  // 去除 IEC 61850 前缀（LD、LN、LN 下 PUB/SUB）
  const stripPrefix = (s: string) => s.replace(/^(LD|LN|PUB|SUB)/, "");
  // 按 ld_inst -> ln_name 二级组织，每个块直接挂在 ln 下（去掉 IED 层和 GOOSE 包装层）
  const lds = new Map<string, Map<string, GooseBlockItem[]>>();
  for (const block of props.blocks) {
    const ldKey = stripPrefix(block.ld_inst) || block.ld_inst;
    const lnKey = stripPrefix(block.ln_name) || block.ln_name;
    if (!lds.has(ldKey)) lds.set(ldKey, new Map());
    const lns = lds.get(ldKey)!;
    if (!lns.has(lnKey)) lns.set(lnKey, []);
    lns.get(lnKey)!.push(block);
  }
  return [...lds.entries()].map(([ld, lns]) => ({
    key: `ld:${ld}`,
    label: ld,
    kind: "LD",
    children: [...lns.entries()].map(([ln, blocks]) => ({
      key: `ln:${ld}:${ln}`,
      label: ln,
      kind: "LN",
      children: blocks.map((block) => ({
        key: block.key,
        label: stripPrefix(block.display_name) || block.display_name,
        isBlock: true,
        block,
      })),
    })),
  }));
});

const selectAll = computed({
  get: () =>
    props.blocks.length > 0 && checkedKeys.value.length === props.blocks.length,
  set: (value) => {
    checkedKeys.value = value ? props.blocks.map((item) => item.key) : [];
    treeRef.value?.setCheckedKeys(checkedKeys.value);
    emit("checked", checkedKeys.value);
  },
});
const indeterminate = computed(
  () =>
    checkedKeys.value.length > 0 &&
    checkedKeys.value.length < props.blocks.length,
);

watch(search, (value) => treeRef.value?.filter(value));
watch(
  () => props.selectedKey,
  (key) => nextTick(() => key && treeRef.value?.setCurrentKey(key)),
);
watch(
  () => props.blocks.map((item) => item.key),
  () => {
    checkedKeys.value = checkedKeys.value.filter((key) =>
      props.blocks.some((item) => item.key === key),
    );
  },
);

function filterNode(value: string, data: TreeNode) {
  return (
    !value ||
    data.label.toLowerCase().includes(value.toLowerCase()) ||
    !!data.block?.go_cb_ref.toLowerCase().includes(value.toLowerCase())
  );
}
function selectNode(data: TreeNode) {
  if (data.block) emit("select", data.block);
}
function handleCheck() {
  const leafKeys = new Set(props.blocks.map((item) => item.key));
  checkedKeys.value = (treeRef.value?.getCheckedKeys(true) || [])
    .map(String)
    .filter((key) => leafKeys.has(key));
  emit("checked", checkedKeys.value);
}
function stateClass(block?: GooseBlockItem) {
  if (!block?.enabled) return "disabled";
  if (block.subscription?.config_mismatch) return "warning";
  if (block.state === "connected") return "connected";
  if (block.state === "lost" || block.state === "error") return "error";
  return "waiting";
}
</script>

<style scoped lang="scss">
.goose-tree-panel {
  width: 330px;
  min-width: 280px;
  height: 100%;
  border-right: 1px solid var(--border-color);
  overflow-y: auto;
  background: var(--bg-subtle);
}
.tree-header {
  position: sticky;
  top: 0;
  z-index: 2;
  padding: 12px;
  border-bottom: 1px solid var(--border-color);
  background: var(--panel-bg);
}
.batch-row {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}
.tree-node {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  width: calc(100% - 8px);
}
.node-badge {
  min-width: 26px;
  padding: 1px 4px;
  border-radius: 2px;
  background: #65758b;
  color: #fff;
  font-size: 10px;
  text-align: center;
}
.block-kind {
  min-width: 30px;
  padding: 1px 4px;
  border-radius: 2px;
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  text-align: center;
}
.block-kind.publisher {
  background: #7b61c9;
}
.block-kind.subscriber {
  background: #2f82c9;
}
.state-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #909399;
}
.state-dot.connected {
  background: #21a366;
  box-shadow: 0 0 0 3px #21a36622;
}
.state-dot.waiting {
  background: #409eff;
}
.state-dot.error {
  background: #f56c6c;
}
.state-dot.warning {
  background: #e6a23c;
  box-shadow: 0 0 0 3px #e6a23c22;
}
.enabled {
  font-weight: 700;
  color: var(--color-success);
}
.message-count {
  margin-left: auto;
  margin-right: 8px;
  color: #8492a6;
  font-size: 11px;
}
:deep(.el-tree) {
  background: transparent;
}
:deep(.el-tree-node__content) {
  height: 32px;
}
@container (max-width: 900px) {
  .goose-tree-panel {
    width: 100%;
    max-height: 280px;
    border-right: 0;
    border-bottom: 1px solid var(--border-color);
  }
}
</style>
