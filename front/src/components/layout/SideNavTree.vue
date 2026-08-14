<template>
  <!-- 拖拽分组时显示的顶层落点：拖到此处提升为顶层分组。
       用 v-show 而非 v-if：dragstart 期间同步插入 DOM 节点会取消浏览器原生拖拽 -->
  <div
    v-show="isGroupDragging"
    class="top-level-drop-zone"
    :class="{ 'is-over': isTopLevelDropActive }"
    @dragover="onTopLevelDragOver"
    @dragleave="onTopLevelDragLeave"
    @drop="onTopLevelDrop"
  >
    <el-icon class="top-level-drop-icon"><Top /></el-icon>
    <span>{{
      draggingDeviceInGroup
        ? $t("sidebar.dropToUngrouped")
        : $t("sidebar.dropToTopLevel")
    }}</span>
  </div>
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
          'is-dlt645-child': data.isDlt645Child,
          'is-dlt645-category':
            data.isDlt645Child && data.dlt645Settlement === undefined,
          'is-dlt645-settlement':
            data.isDlt645Child && data.dlt645Settlement !== undefined,
          'is-draggable': isDraggableNode(data),
          'is-dragging': isDraggingNode(data),
          'is-drop-target': isDropTargetNode(data),
        }"
        :draggable="isDraggableNode(data)"
        @dragstart="onDragStart($event, data)"
        @dragover="onDragOver($event, data)"
        @dragleave="onDragLeave($event, data)"
        @drop="onDrop($event, data)"
        @dragend="onDragEnd"
      >
        <el-tooltip
          :content="node.label"
          placement="right"
          :disabled="!isCollapse"
        >
          <el-icon class="node-icon">
            <Folder
              v-if="
                data.isGroup && !data.isIec61850Child && !data.isDlt645Child
              "
            />
            <Connection v-else-if="data.isIec61850 && !data.isGroup" />
            <Coin v-else-if="data.isDlt645 && !data.isGroup" />
            <Collection v-else-if="data.isDlt645Child && data.isGroup" />
            <Calendar v-else-if="data.isDlt645Child" />
            <component
              :is="getIec61850NodeIcon(data)"
              v-else-if="data.isIec61850Child"
            />
            <Cpu v-else />
          </el-icon>
        </el-tooltip>
        <span class="node-label">{{ node.label }}</span>

        <div class="node-actions" v-if="!isCollapse" @click.stop>
          <template
            v-if="data.isGroup && !data.isIec61850Child && !data.isDlt645Child"
          >
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
          <template v-else-if="!data.isIec61850Child && !data.isDlt645Child">
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
import { onMounted, ref, watch, nextTick, computed } from "vue";
import { ElTree } from "element-plus";
import { getIec61850NodeIcon } from "./iec61850NodeIcons";
import {
  readDragPayload,
  setDragPayload,
  clearDragPayload,
  type DeviceDragPayload,
} from "./deviceDrag";
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
  Coin,
  Collection,
  Calendar,
  Top,
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
  (e: "device-drop", deviceId: number, groupId: number): void;
  (e: "group-drop", groupId: number, targetGroupId: number): void;
  (e: "group-drop-top", groupId: number): void;
  (e: "device-drop-top", deviceId: number): void;
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
  } else if (data.isDlt645Child) {
    emit("node-click", data);
  } else {
    emit("node-click", data);
  }
};

// ========== 拖拽修改设备分组 ==========

/** 可拖拽的节点：普通分组与设备节点（排除 IEC61850/dlt645 子结构节点） */
const isDraggableNode = (data: any) =>
  !data.isIec61850Child && !data.isDlt645Child;

const draggingId = ref<number | null>(null);
const dropTargetId = ref<number | null>(null);
/** 当前拖拽的分组 id（用于显示顶层落点） */
const draggingGroupId = ref<number | null>(null);
/** 当前拖拽的设备是否位于分组内（设备拖到顶层落点 = 移出分组） */
const draggingDeviceInGroup = ref(false);
/** 分组是否悬停在顶层落点上 */
const isTopLevelDropActive = ref(false);
/** 是否显示顶层落点：拖拽分组（提升为顶层）或拖拽分组内设备（移出分组） */
const isGroupDragging = computed(
  () => draggingGroupId.value !== null || draggingDeviceInGroup.value,
);

const isDraggingNode = (data: any) =>
  draggingId.value !== null && data.id === draggingId.value;
const isDropTargetNode = (data: any) =>
  dropTargetId.value !== null && data.id === dropTargetId.value;

const onDragStart = (event: DragEvent, data: any) => {
  if (!isDraggableNode(data)) return;
  // 从操作按钮区域开始拖动时取消拖拽，避免与编辑/删除/复制按钮误触
  const target = event.target as HTMLElement | null;
  if (target?.closest(".node-actions")) {
    event.preventDefault();
    return;
  }
  const payload: DeviceDragPayload = data.isGroup
    ? { type: "group", id: data.id, name: data.name }
    : {
        type: "device",
        id: data.id,
        name: data.name,
        groupId: data.groupId ?? null,
      };
  setDragPayload(event, payload);
  draggingId.value = data.id;
  // 延迟设置拖拽状态：dragstart 期间同步更新 DOM（哪怕只是 display）可能中断浏览器原生拖拽
  setTimeout(() => {
    if (draggingId.value === data.id) {
      draggingGroupId.value = data.isGroup ? data.id : null;
      draggingDeviceInGroup.value = !data.isGroup && payload.groupId != null;
    }
  }, 0);
};

/** 判断 targetId 是否位于 sourceId 分组（不含自身）的子孙分组中 */
const isTargetInSubtree = (
  sourceId: number,
  targetId: number,
  nodes: any[],
): boolean => {
  for (const node of nodes) {
    if (!node.isGroup || !node.children) continue;
    if (node.id === sourceId) {
      return containsGroup(node.children, targetId);
    }
    if (isTargetInSubtree(sourceId, targetId, node.children)) return true;
  }
  return false;
};

const containsGroup = (nodes: any[], targetId: number): boolean => {
  for (const node of nodes) {
    if (!node.isGroup) continue;
    if (node.id === targetId) return true;
    if (node.children && containsGroup(node.children, targetId)) return true;
  }
  return false;
};

/** 只有真正的设备组节点可接收拖放（排除 IEC61850/dlt645 子结构分组） */
const isValidDropTarget = (data: any, payload: DeviceDragPayload) => {
  if (!data.isGroup || data.isIec61850Child || data.isDlt645Child) {
    return false;
  }
  if (payload.type === "device") {
    // 设备拖回自己当前所在的分组没有意义
    return payload.groupId !== data.id;
  }
  if (payload.type === "group") {
    // 分组不能拖到自己或自己的子孙分组下（避免循环）
    if (data.id === payload.id) return false;
    return !isTargetInSubtree(payload.id, data.id, props.treeData);
  }
  return false;
};

const onDragOver = (event: DragEvent, data: any) => {
  const payload = readDragPayload(event);
  if (!payload || !isValidDropTarget(data, payload)) return;
  event.preventDefault();
  event.dataTransfer!.dropEffect = "move";
  dropTargetId.value = data.id;
};

const onDragLeave = (event: DragEvent, data: any) => {
  if (dropTargetId.value !== data.id) return;
  const related = event.relatedTarget as Node | null;
  if (
    related &&
    event.currentTarget instanceof Node &&
    event.currentTarget.contains(related)
  ) {
    // 仍在节点内部移动（子元素之间），保持高亮
    return;
  }
  dropTargetId.value = null;
};

const onDrop = (event: DragEvent, data: any) => {
  const payload = readDragPayload(event);
  if (!payload || !isValidDropTarget(data, payload)) return;
  event.preventDefault();
  clearDragPayload();
  draggingId.value = null;
  dropTargetId.value = null;
  draggingGroupId.value = null;
  draggingDeviceInGroup.value = false;
  isTopLevelDropActive.value = false;
  if (payload.type === "device") {
    emit("device-drop", payload.id, data.id);
  } else {
    emit("group-drop", payload.id, data.id);
  }
};

const onDragEnd = () => {
  clearDragPayload();
  draggingId.value = null;
  dropTargetId.value = null;
  draggingGroupId.value = null;
  draggingDeviceInGroup.value = false;
  isTopLevelDropActive.value = false;
};

/** 顶层落点可接收：分组（提升为顶层）与分组内的设备（移出分组） */
const isTopLevelDropValid = (payload: DeviceDragPayload | null): boolean =>
  !!payload &&
  (payload.type === "group" ||
    (payload.type === "device" && payload.groupId != null));

const onTopLevelDragOver = (event: DragEvent) => {
  const payload = readDragPayload(event);
  if (!payload) return;
  if (!isTopLevelDropValid(payload)) return;
  event.preventDefault();
  event.dataTransfer!.dropEffect = "move";
  isTopLevelDropActive.value = true;
};

const onTopLevelDragLeave = () => {
  isTopLevelDropActive.value = false;
};

const onTopLevelDrop = (event: DragEvent) => {
  const payload = readDragPayload(event);
  if (!payload) return;
  if (!isTopLevelDropValid(payload)) return;
  event.preventDefault();
  clearDragPayload();
  draggingId.value = null;
  dropTargetId.value = null;
  draggingGroupId.value = null;
  draggingDeviceInGroup.value = false;
  isTopLevelDropActive.value = false;
  if (payload.type === "device") {
    emit("device-drop-top", payload.id);
  } else {
    emit("group-drop-top", payload.id);
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

/* 拖拽分组时的顶层落点 */
.top-level-drop-zone {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin: 0 12px 8px;
  padding: 8px 12px;
  border: 1.5px dashed var(--sb-border);
  border-radius: 10px;
  color: var(--text-secondary);
  font-size: 12.5px;
  cursor: copy;
  transition: all 0.2s;
}

.top-level-drop-zone.is-over {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--item-active-bg);
}

.top-level-drop-icon {
  font-size: 15px;
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

/* dlt645 子节点行高：与 IEC61850 保持一致（category → 32px，settlement → 28px） */
.device-tree :deep(.el-tree-node__content:has(> .is-dlt645-category)) {
  height: 32px;
  border-radius: 8px;
  margin-bottom: 2px;
}

.device-tree :deep(.el-tree-node__content:has(> .is-dlt645-settlement)) {
  height: 28px;
  border-radius: 6px;
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

.tree-node-content.is-iec61850-child,
.tree-node-content.is-dlt645-child {
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

/* dlt645 category 层 - 与 IEC61850 category 保持一致 */
.tree-node-content.is-dlt645-category .node-label {
  font-size: 12.5px;
  color: var(--text-secondary);
}

.tree-node-content.is-dlt645-category .node-icon {
  color: var(--color-primary);
  font-size: 16px;
  margin-right: 10px;
}

/* dlt645 settlement 层 - 与 IEC61850 LD 层保持一致 */
.tree-node-content.is-dlt645-settlement .node-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.tree-node-content.is-dlt645-settlement .node-icon {
  color: var(--text-secondary);
  font-size: 14px;
  margin-right: 8px;
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

/* ===== 拖拽修改设备分组 ===== */
.tree-node-content.is-draggable {
  cursor: grab;
}

.tree-node-content.is-dragging {
  opacity: 0.4;
}

.tree-node-content.is-drop-target {
  background: var(--item-active-bg) !important;
  box-shadow: inset 0 0 0 2px var(--color-primary);
  border-radius: 10px;
}
</style>
