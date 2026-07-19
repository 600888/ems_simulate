<template>
  <el-tree
    ref="treeRef"
    :data="treeData"
    :props="treeProps"
    node-key="nodeKey"
    :default-expanded-keys="expandedKeys"
    :current-node-key="currentNodeKey"
    :expand-on-click-node="true"
    highlight-current
    @node-click="(data: any) => handleNodeClick(data)"
    class="device-tree"
  >
    <template #default="{ node, data }">
      <div
        class="tree-node-content"
        :class="{
          'is-group': data.isGroup,
          'is-iec61850-child': data.isIec61850Child,
          'is-iec61850-device': data.isIec61850 && !data.isGroup,
          'is-iec61850-category': data.iec61850Level === 'category',
          'is-iec61850-ld': data.iec61850Level === 'ld',
          'is-iec61850-ln': data.iec61850Level === 'ln',
        }"
      >
        <el-tooltip
          :content="node.label"
          placement="right"
          :disabled="!isCollapse"
        >
          <el-icon class="node-icon">
            <Folder v-if="data.isGroup && !data.isIec61850Child" />
            <Connection v-else-if="data.isIec61850 && !data.isGroup" />
            <component
              :is="getIec61850NodeIcon(data)"
              v-else-if="data.isIec61850Child"
            />
            <Cpu v-else />
          </el-icon>
        </el-tooltip>
        <span class="node-label">{{ node.label }}</span>

        <div class="node-actions" v-if="!isCollapse" @click.stop>
          <template v-if="data.isGroup && !data.isIec61850Child">
            <el-dropdown
              trigger="click"
              @command="(cmd: string) => $emit('group-command', cmd, data)"
            >
              <el-button link size="small" :icon="MoreFilled" />
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit" :icon="Edit">{{
                    $t("common.edit")
                  }}</el-dropdown-item>
                  <el-dropdown-item command="addDevice" :icon="Plus">{{
                    $t("sidebar.addDevice")
                  }}</el-dropdown-item>
                  <el-dropdown-item command="addSubGroup" :icon="FolderAdd">{{
                    $t("sidebar.addSubGroup")
                  }}</el-dropdown-item>
                  <el-dropdown-item command="startAll" :icon="VideoPlay">{{
                    $t("sidebar.startAll")
                  }}</el-dropdown-item>
                  <el-dropdown-item command="stopAll" :icon="VideoPause">{{
                    $t("sidebar.stopAll")
                  }}</el-dropdown-item>
                  <el-dropdown-item command="delete" :icon="Delete" divided>{{
                    $t("sidebar.deleteGroup")
                  }}</el-dropdown-item>
                  <el-dropdown-item
                    command="cascadeDelete"
                    :icon="Delete"
                    style="color: var(--el-color-danger)"
                    >{{ $t("sidebar.cascadeDeleteGroup") }}</el-dropdown-item
                  >
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
          <template v-else-if="!data.isIec61850Child">
            <el-button
              link
              size="small"
              :icon="Edit"
              @click="$emit('edit-device', data)"
            />
            <el-button
              link
              size="small"
              :icon="DocumentCopy"
              @click="$emit('copy-device', data)"
            />
            <el-button
              link
              size="small"
              :icon="Delete"
              @click="$emit('delete-device', data)"
            />
          </template>
        </div>
      </div>
    </template>
  </el-tree>
</template>

<script lang="ts" setup>
import { onMounted, ref, watch, nextTick } from "vue";
import { ElTree } from "element-plus";
import { getIec61850NodeIcon } from "./iec61850NodeIcons";
import {
  Folder,
  Cpu,
  MoreFilled,
  Edit,
  Plus,
  FolderAdd,
  VideoPlay,
  VideoPause,
  Delete,
  DocumentCopy,
  Connection,
} from "@element-plus/icons-vue";

const props = defineProps<{
  treeData: any[];
  treeProps: any;
  expandedKeys: string[];
  currentNodeKey: string;
  isCollapse: boolean;
}>();

const emit = defineEmits<{
  (e: "node-click", data: any): void;
  (e: "group-command", command: string, data: any): void;
  (e: "edit-device", data: any): void;
  (e: "delete-device", data: any): void;
  (e: "copy-device", data: any): void;
}>();

const treeRef = ref<InstanceType<typeof ElTree>>();

// 导入 router 用于 linkTo 导航
import { useRouter } from "vue-router";
const router = useRouter();

// 处理节点点击，为 IEC61850 子节点补充 category 信息
const handleNodeClick = (data: any) => {
  // 优先处理 linkTo 导航 (如 Reports/GOOSE 跳转到独立管理页面)
  if (data.linkTo) {
    router.push(data.linkTo);
    return;
  }
  if (data.isIec61850Child) {
    // 从 nodeKey 推断 category: nodeKey 格式如 "device-{name}-DataModel" 或 "device-{name}-DataModel-{idx}"
    // type 字段在构建树时已经设置
    const enrichedData = { ...data };
    // 如果没有 type 字段，从 nodeKey 中提取
    if (!enrichedData.type && enrichedData.nodeKey) {
      // 尝试匹配 category: "device-{deviceName}-{category}" 或 "ungrouped-{deviceName}-{category}-{idx}"
      const categories = [
        "GOOSE",
        "Reports",
        "SettingGroups",
        "Files",
        "DataSets",
        "DataModel",
      ];
      for (const cat of categories) {
        if (String(enrichedData.nodeKey).includes(cat.replace(" ", ""))) {
          enrichedData.type = cat;
          break;
        }
      }
    }
    emit("node-click", enrichedData);
  } else {
    emit("node-click", data);
  }
};

const expandKeys = () => {
  nextTick(() => {
    if (!treeRef.value) return;
    props.expandedKeys.forEach((key) => {
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
      if (treeRef.value.getNode(props.currentNodeKey)) {
        treeRef.value.setCurrentKey(props.currentNodeKey);
      } else {
        // 节点可能尚未渲染，延迟重试
        setTimeout(() => {
          treeRef.value?.setCurrentKey(props.currentNodeKey);
        }, 100);
      }
    }
  });
};

watch(() => props.expandedKeys, expandKeys, { deep: true });
watch(
  () => props.treeData,
  () => {
    // 数据更新时，先展开，再设置选中。给予更多时间确保 DOM 更新。
    expandKeys();
    setTimeout(setCurrentKey, 50);
  },
  { deep: true },
);
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

/* IEC61850 子节点行高：匹配未分组区域的紧凑样式 */
.device-tree :deep(.el-tree-node__content:has(> .is-iec61850-category)) {
  height: 32px;
  border-radius: 8px;
  margin-bottom: 2px;
}

.device-tree :deep(.el-tree-node__content:has(> .is-iec61850-ld)) {
  height: 28px;
  border-radius: 6px;
  margin-bottom: 1px;
}

.device-tree :deep(.el-tree-node__content:has(> .is-iec61850-ln)) {
  height: 26px;
  border-radius: 5px;
  margin-bottom: 1px;
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
  min-width: 0;
  overflow: hidden;
  padding-left: 4px;
}

.tree-node-content.is-group {
  font-weight: 600;
  color: var(--text-primary);
}

.tree-node-content.is-iec61850-child {
  padding-left: 4px;
}

/* category 层 (DataModel, GOOSE...) - 对应未分组 .child-row */
.tree-node-content.is-iec61850-category .node-label {
  font-size: 12.5px;
  color: var(--text-secondary);
}

.tree-node-content.is-iec61850-category .node-icon {
  color: var(--color-primary);
  font-size: 16px;
  margin-right: 10px;
}

/* LD 层 - 对应未分组 .iec61850-sub-item */
.tree-node-content.is-iec61850-ld .node-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.tree-node-content.is-iec61850-ld .node-icon {
  color: var(--text-secondary);
  font-size: 14px;
  margin-right: 8px;
}

/* LN 层 - 对应未分组 .iec61850-ln-item */
.tree-node-content.is-iec61850-ln .node-label {
  font-size: 11.5px;
  color: var(--text-secondary);
}

.tree-node-content.is-iec61850-ln .node-icon {
  color: var(--text-secondary);
  font-size: 12px;
  margin-right: 6px;
}

.tree-node-content.is-iec61850-device {
  font-weight: 500;
}

.node-icon {
  margin-right: 12px;
  font-size: 18px;
  color: var(--text-secondary);
}

.is-group .node-icon {
  color: var(--color-primary);
}

.is-iec61850-device .node-icon {
  color: var(--color-primary);
}

/* IEC61850 子节点的 group 图标 (如 LD 有子节点时) */
.is-iec61850-ld.is-group .node-icon {
  color: var(--color-primary);
  font-size: 14px;
}

.node-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13.5px;
  letter-spacing: 0.3px;
}

.node-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
  flex-shrink: 0;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.tree-node-content:hover .node-actions {
  opacity: 1;
}

.node-actions .el-button {
  padding: 5px;
  margin-left: 0;
  color: var(--text-secondary);
  border-radius: 6px;
  transition: all 0.2s;
}

.node-actions .el-button:hover {
  background-color: var(--item-active-bg);
  color: var(--color-primary);
}
</style>
