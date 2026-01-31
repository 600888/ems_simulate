<template>
  <el-tree
    ref="treeRef"
    :data="treeData"
    :props="treeProps"
    node-key="nodeKey"
    :default-expanded-keys="expandedKeys"
    :current-node-key="currentNodeKey"
    :expand-on-click-node="false"
    highlight-current
    @node-click="(data: any) => $emit('node-click', data)"
    class="device-tree"
  >
    <template #default="{ node, data }">
      <div class="tree-node-content" :class="{ 'is-group': data.isGroup }">
        <el-tooltip :content="node.label" placement="right" :disabled="!isCollapse">
          <el-icon class="node-icon">
            <Folder v-if="data.isGroup" />
            <Cpu v-else />
          </el-icon>
        </el-tooltip>
        <span class="node-label">{{ node.label }}</span>
        
        <div class="node-actions" v-if="!isCollapse" @click.stop>
          <template v-if="data.isGroup">
            <el-dropdown trigger="click" @command="(cmd: string) => $emit('group-command', cmd, data)">
              <el-button link size="small" :icon="MoreFilled" />
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit" :icon="Edit">编辑</el-dropdown-item>
                  <el-dropdown-item command="addDevice" :icon="Plus">添加设备</el-dropdown-item>
                  <el-dropdown-item command="addSubGroup" :icon="FolderAdd">添加子分组</el-dropdown-item>
                  <el-dropdown-item command="startAll" :icon="VideoPlay">启动全部</el-dropdown-item>
                  <el-dropdown-item command="stopAll" :icon="VideoPause">停止全部</el-dropdown-item>
                  <el-dropdown-item command="delete" :icon="Delete" divided>删除</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
          <template v-else>
            <el-button link size="small" :icon="Edit" @click="$emit('edit-device', data)" />
            <el-button link size="small" :icon="Delete" @click="$emit('delete-device', data)" />
          </template>
        </div>
      </div>
    </template>
  </el-tree>
</template>

<script lang="ts" setup>
import { onMounted, ref, watch, nextTick } from "vue";
import { ElTree } from 'element-plus';
import { 
  Folder, Cpu, MoreFilled, Edit, Plus, FolderAdd, 
  VideoPlay, VideoPause, Delete 
} from "@element-plus/icons-vue";

const props = defineProps<{
  treeData: any[];
  treeProps: any;
  expandedKeys: string[];
  currentNodeKey: string;
  isCollapse: boolean;
}>();

defineEmits<{
  (e: 'node-click', data: any): void;
  (e: 'group-command', command: string, data: any): void;
  (e: 'edit-device', data: any): void;
  (e: 'delete-device', data: any): void;
}>();

const treeRef = ref<InstanceType<typeof ElTree>>();

const expandKeys = () => {
  nextTick(() => {
    if (!treeRef.value) return;
    props.expandedKeys.forEach(key => {
      const node = treeRef.value?.getNode(key);
      if (node) {
        node.expanded = true;
      }
    });
  });
};

const setCurrentKey = () => {
  nextTick(() => {
    if (treeRef.value && props.currentNodeKey) {
      treeRef.value.setCurrentKey(props.currentNodeKey);
    }
  });
};

watch(() => props.expandedKeys, expandKeys, { deep: true });
watch(() => props.treeData, () => {
  expandKeys();
  setCurrentKey();
}, { deep: true });
watch(() => props.currentNodeKey, setCurrentKey);
</script>

<style lang="scss" scoped>
.device-tree {
  background-color: transparent;
  padding: 0 12px;
  --el-tree-node-hover-bg-color: var(--item-hover-bg);
}

.device-tree :deep(.el-tree-node) {
  background-color: transparent !important;
}

.device-tree :deep(.el-tree-node__content) {
  height: 44px;
  border-radius: 10px;
  margin-bottom: 6px;
  padding-right: 8px;
  transition: all 0.2s ease;
  color: var(--text-secondary);
}

.device-tree :deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: var(--item-active-bg) !important;
  color: var(--color-primary) !important;
  font-weight: 600;
  box-shadow: inset 2px 0 0 var(--color-primary);
}

.tree-node-content {
  display: flex;
  align-items: center;
  width: 100%;
  padding-left: 4px;
}

.tree-node-content.is-group {
  font-weight: 600;
  color: var(--text-primary);
}

.node-icon {
  margin-right: 12px;
  font-size: 18px;
  color: var(--text-secondary);
}

.is-group .node-icon {
  color: var(--color-primary);
}

.node-label {
  flex: 1;
  font-size: 13.5px;
  letter-spacing: 0.3px;
}

.node-actions {
  display: flex;
  gap: 6px;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.tree-node-content:hover .node-actions {
  opacity: 1;
}

.node-actions .el-button {
  padding: 5px;
  color: var(--text-secondary);
  border-radius: 6px;
  transition: all 0.2s;
}

.node-actions .el-button:hover {
  background-color: var(--item-active-bg);
  color: var(--color-primary);
}
</style>
