<template>
  <div class="scl-tree-panel">
    <el-input
      v-model="searchText"
      :placeholder="$t('scl.searchNode')"
      clearable
      class="search-input"
      :prefix-icon="Search"
    />
    <div class="tree-wrapper">
      <el-tree
        ref="treeRef"
        :data="filteredTree"
        :props="treeProps"
        node-key="id"
        :default-expanded-keys="defaultExpanded"
        :highlight-current="true"
        :filter-node-method="filterNode"
        @node-click="handleNodeClick"
      >
        <template #default="{ node, data }">
          <span
            class="tree-node-wrapper"
            :class="{ 'diff-highlight': isDiffHighlight(data) }"
          >
            <span class="tree-node-icon">{{ getNodeIcon(data) }}</span>
            <span class="tree-node-label">{{ data.label }}</span>
            <span v-if="data.badge" class="tree-node-badge">{{
              data.badge
            }}</span>
          </span>
        </template>
      </el-tree>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { Search } from "@element-plus/icons-vue";
import type { SclTreeNode } from "@/api/sclApi";

const props = withDefaults(
  defineProps<{
    treeData: SclTreeNode[];
    selectedPath?: string;
    diffMode?: boolean;
    highlightNodes?: string[];
  }>(),
  {
    selectedPath: "",
    diffMode: false,
    highlightNodes: () => [],
  },
);

const emit = defineEmits<{
  (e: "node-select", path: string, node: SclTreeNode): void;
  (e: "node-expand", path: string): void;
}>();

const searchText = ref("");
const treeRef = ref<any>(null);
const defaultExpanded = ref<string[]>([]);

const treeProps = { children: "children", label: "label" };

const filteredTree = computed(() => {
  if (!searchText.value) return props.treeData;
  return props.treeData;
});

watch(searchText, (val) => {
  treeRef.value?.filter(val);
});

function filterNode(value: string, data: SclTreeNode): boolean {
  if (!value) return true;
  return data.label.toLowerCase().includes(value.toLowerCase());
}

function handleNodeClick(data: SclTreeNode) {
  emit("node-select", data.id, data);
}

function isDiffHighlight(data: SclTreeNode): boolean {
  return props.highlightNodes.includes(data.id);
}

function getNodeIcon(data: SclTreeNode): string {
  if (data.icon) return data.icon;
  const map: Record<string, string> = {
    IED: "📁",
    AP: "🔌",
    Server: "🖥",
    LDevice: "📁",
    LN: "📄",
    DO: "📋",
    DA: "🔹",
    DataSet: "📊",
    FCDA: "📌",
    GoCB: "🎛️",
    RCB: "📋",
    DataType: "📘",
    Communication: "📡",
  };
  return map[data.type] || "📄";
}
</script>

<style scoped>
.scl-tree-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.search-input {
  margin-bottom: 12px;
}
.tree-wrapper {
  flex: 1;
  overflow: auto;
}
.tree-node-wrapper {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
}
.tree-node-icon {
  font-size: 15px;
  flex-shrink: 0;
}
.tree-node-label {
  font-size: 13px;
  white-space: nowrap;
  color: var(--text-primary);
}
.tree-node-badge {
  font-size: 11px;
  color: var(--text-secondary);
  margin-left: auto;
  padding: 0 8px;
  background: var(--bg-muted);
  border-radius: 10px;
  white-space: nowrap;
}
.diff-highlight {
  background: rgba(255, 193, 7, 0.15);
  border-radius: 4px;
}
</style>
