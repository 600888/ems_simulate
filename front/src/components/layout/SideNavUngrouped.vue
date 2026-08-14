<template>
  <div
    class="ungrouped-section"
    :class="{ 'is-drop-target': isDropTarget }"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <div class="ungrouped-header">
      <div class="header-left" @click="$emit('toggle')">
        <el-icon><ArrowRight :class="{ 'is-expanded': expanded }" /></el-icon>
        <span>{{
          $t("sidebar.ungroupedDevices", { count: ungroupedDevices.length })
        }}</span>
      </div>

      <div class="header-actions" v-if="!isCollapse" @click.stop>
        <el-dropdown
          trigger="click"
          @command="(cmd: string) => $emit('group-command', cmd)"
        >
          <el-button link size="small" :icon="MoreFilled" />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="addDevice" :icon="Plus">{{
                $t("sidebar.addDevice")
              }}</el-dropdown-item>
              <el-dropdown-item command="startAll" :icon="VideoPlay">{{
                $t("sidebar.startAll")
              }}</el-dropdown-item>
              <el-dropdown-item command="stopAll" :icon="VideoPause">{{
                $t("sidebar.stopAll")
              }}</el-dropdown-item>
              <el-dropdown-item
                command="deleteAllDevices"
                :icon="Delete"
                divided
                style="color: var(--el-color-danger)"
                >{{ $t("sidebar.deleteAllDevices") }}</el-dropdown-item
              >
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
    <div
      v-if="ungroupedDevices.length"
      v-show="expanded"
      class="ungrouped-list"
    >
      <div
        v-for="device in ungroupedDevices"
        :key="device.id"
        class="ungrouped-item-wrapper"
      >
        <div
          class="ungrouped-item"
          :class="{
            'is-active':
              currentDeviceName === device.name ||
              selectedNodeKey === `device-${device.name}`,
            'is-dragging': draggingId === device.id,
          }"
          draggable="true"
          @dragstart="onDeviceDragStart($event, device)"
          @dragend="onDragEnd"
          @click="handleDeviceClick(device)"
        >
          <!-- IEC61850 展开箭头 -->
          <el-icon
            v-if="iec61850Map[device.name]"
            class="expand-arrow"
            :class="{ 'is-expanded': expandedIec61850[device.name] }"
            @click.stop="toggleIec61850(device.name)"
          >
            <ArrowRight />
          </el-icon>
          <span v-else class="expand-arrow-placeholder" />
          <el-tooltip
            :content="device.name"
            placement="right"
            :disabled="!isCollapse"
          >
            <el-icon
              v-if="iec61850Map[device.name]"
              class="node-icon iec61850-icon"
              ><Coin
                v-if="
                  iec61850Map[device.name]?.[0]?.isDlt645Child
                " /><Connection v-else
            /></el-icon>
            <el-icon v-else class="node-icon"><Cpu /></el-icon>
          </el-tooltip>
          <span class="device-name">{{ device.name }}</span>
          <div class="node-actions" v-if="!isCollapse" @click.stop>
            <el-button
              link
              size="small"
              :icon="Edit"
              @click="$emit('edit-device', device.name)"
            />
            <el-button
              link
              size="small"
              :icon="DocumentCopy"
              @click="$emit('copy-device', device.name)"
            />
            <el-button
              link
              size="small"
              :icon="Delete"
              @click="$emit('delete-device', device.name)"
            />
          </div>
        </div>

        <!-- IEC61850 子节点树 -->
        <div
          v-if="iec61850Map[device.name]"
          v-show="expandedIec61850[device.name]"
          class="iec61850-children"
        >
          <div
            v-for="child in iec61850Map[device.name]"
            :key="child.nodeKey"
            class="iec61850-child-item"
            :class="{ 'is-group': child.isGroup }"
          >
            <div
              class="child-row"
              :class="{ 'is-selected': selectedNodeKey === child.nodeKey }"
              @click="handleChildClick(device.name, child)"
            >
              <el-icon
                v-if="child.isGroup"
                class="expand-arrow small"
                :class="{
                  'is-expanded':
                    expandedCategories[`${device.name}::${child.nodeKey}`],
                }"
              >
                <ArrowRight />
              </el-icon>
              <span v-else class="expand-arrow-placeholder small" />
              <el-icon class="child-icon">
                <Collection v-if="child.isDlt645Child && child.isGroup" />
                <Calendar v-else-if="child.isDlt645Child" />
                <component v-else :is="getIec61850NodeIcon(child)" />
              </el-icon>
              <span class="child-label">{{ child.label }}</span>
            </div>
            <!-- 分类下的子项 -->
            <div
              v-if="child.isGroup && child.children"
              v-show="expandedCategories[`${device.name}::${child.nodeKey}`]"
              class="iec61850-sub-children"
            >
              <div
                v-for="subChild in child.children"
                :key="subChild.nodeKey"
                class="iec61850-sub-item-wrapper"
              >
                <div
                  class="iec61850-sub-item"
                  :class="{
                    'is-selected': selectedNodeKey === subChild.nodeKey,
                    'is-group': subChild.isGroup,
                  }"
                  @click="handleSubChildClick(subChild, device.name)"
                >
                  <el-icon
                    v-if="subChild.isGroup"
                    class="expand-arrow small"
                    :class="{
                      'is-expanded':
                        expandedCategories[
                          `${device.name}::${subChild.nodeKey}`
                        ],
                    }"
                  >
                    <ArrowRight />
                  </el-icon>
                  <span v-else class="expand-arrow-placeholder small" />
                  <el-icon class="sub-icon">
                    <Calendar v-if="subChild.isDlt645Child" />
                    <component v-else :is="getIec61850NodeIcon(subChild)" />
                  </el-icon>
                  <span class="sub-label">{{ subChild.label }}</span>
                </div>
                <!-- LD 下的 LN 子节点 (第三层) -->
                <div
                  v-if="subChild.isGroup && subChild.children"
                  v-show="
                    expandedCategories[`${device.name}::${subChild.nodeKey}`]
                  "
                  class="iec61850-ln-children"
                >
                  <div
                    v-for="lnChild in subChild.children"
                    :key="lnChild.nodeKey"
                    class="iec61850-ln-item"
                    :class="{
                      'is-selected': selectedNodeKey === lnChild.nodeKey,
                    }"
                  >
                    <div
                      class="iec61850-ln-row"
                      :class="{ 'is-group': lnChild.isGroup }"
                      @click="handleLnChildClick(lnChild)"
                    >
                      <el-icon
                        v-if="lnChild.isGroup"
                        class="expand-arrow small"
                        :class="{
                          'is-expanded':
                            expandedCategories[
                              `${device.name}::${lnChild.nodeKey}`
                            ],
                        }"
                        @click.stop="
                          toggleIec61850Category(device.name, lnChild.nodeKey)
                        "
                      >
                        <ArrowRight />
                      </el-icon>
                      <span v-else class="expand-arrow-placeholder small" />
                      <el-icon class="ln-icon">
                        <component :is="getIec61850NodeIcon(lnChild)" />
                      </el-icon>
                      <span class="ln-label">{{ lnChild.label }}</span>
                    </div>
                    <!-- LN 下的数据集子节点 (第四层) -->
                    <div
                      v-if="lnChild.isGroup && lnChild.children"
                      v-show="
                        expandedCategories[`${device.name}::${lnChild.nodeKey}`]
                      "
                      class="iec61850-ds-children"
                    >
                      <div
                        v-for="dsChild in lnChild.children"
                        :key="dsChild.nodeKey"
                        class="iec61850-ds-item"
                        :class="{
                          'is-selected': selectedNodeKey === dsChild.nodeKey,
                        }"
                        @click="handleDsChildClick(dsChild)"
                      >
                        <el-icon class="ds-icon">
                          <component :is="getIec61850NodeIcon(dsChild)" />
                        </el-icon>
                        <span class="ds-label">{{ dsChild.label }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div v-else v-show="expanded" class="ungrouped-empty">
      {{ $t("sidebar.ungroupedEmpty") }}
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref, watch } from "vue";
import { getIec61850NodeIcon } from "./iec61850NodeIcons";
import {
  readDragPayload,
  setDragPayload,
  clearDragPayload,
  type DeviceDragPayload,
} from "./deviceDrag";
import {
  ArrowRight,
  Cpu,
  Edit,
  Delete,
  MoreFilled,
  Plus,
  VideoPlay,
  VideoPause,
  DocumentCopy,
  Connection,
  Coin,
  Collection,
  Calendar,
} from "@element-plus/icons-vue";

interface TreeNode {
  nodeKey: string;
  label: string;
  isGroup: boolean;
  id: number;
  isIec61850Child?: boolean;
  isDlt645Child?: boolean;
  dlt645Prefix?: number;
  dlt645Settlement?: number;
  iec61850Level?: "category" | "ld" | "ln";
  name: string;
  type?: string;
  value?: string;
  deviceName?: string;
  children?: TreeNode[];
}

const props = defineProps<{
  ungroupedDevices: any[];
  iec61850Map: Record<string, TreeNode[]>;
  expanded: boolean;
  currentDeviceName: string;
  isCollapse: boolean;
  selectedNodeKey?: string;
}>();

const emit = defineEmits<{
  (e: "toggle"): void;
  (e: "device-click", device: any): void;
  (e: "edit-device", name: string): void;
  (e: "delete-device", name: string): void;
  (e: "group-command", command: string): void;
  (e: "copy-device", name: string): void;
  (e: "node-click", data: any): void;
  (e: "device-drop-ungrouped", deviceId: number): void;
}>();

// ========== 拖拽修改设备分组 ==========

const draggingId = ref<number | null>(null);
const isDropTarget = ref(false);

const onDeviceDragStart = (event: DragEvent, device: any) => {
  // 从操作按钮区域开始拖动时取消拖拽，避免与编辑/删除/复制按钮误触
  const target = event.target as HTMLElement | null;
  if (target?.closest(".node-actions")) {
    event.preventDefault();
    return;
  }
  setDragPayload(event, {
    type: "device",
    id: device.id,
    name: device.name,
    groupId: null,
  });
  draggingId.value = device.id;
};

/** 未分组区域仅接收仍处于分组中的设备（移出分组）；分组提升为顶层请拖到分组树顶部的顶层落点 */
const canAccept = (payload: DeviceDragPayload) =>
  payload.type === "device" && payload.groupId !== null;

const onDragOver = (event: DragEvent) => {
  const payload = readDragPayload(event);
  if (!payload || !canAccept(payload)) return;
  event.preventDefault();
  event.dataTransfer!.dropEffect = "move";
  isDropTarget.value = true;
};

const onDragLeave = (event: DragEvent) => {
  const related = event.relatedTarget as Node | null;
  if (
    related &&
    event.currentTarget instanceof Node &&
    event.currentTarget.contains(related)
  ) {
    return;
  }
  isDropTarget.value = false;
};

const onDrop = (event: DragEvent) => {
  const payload = readDragPayload(event);
  if (!payload || !canAccept(payload)) return;
  event.preventDefault();
  clearDragPayload();
  draggingId.value = null;
  isDropTarget.value = false;
  if (payload.type === "device") {
    emit("device-drop-ungrouped", payload.id);
  }
};

const onDragEnd = () => {
  clearDragPayload();
  draggingId.value = null;
  isDropTarget.value = false;
};

// IEC61850 设备展开状态
const expandedIec61850 = ref<Record<string, boolean>>({});
const expandedCategories = ref<Record<string, boolean>>({});
const selectedNodeKey = ref<string>("");

const toggleIec61850 = (deviceName: string) => {
  expandedIec61850.value[deviceName] = !expandedIec61850.value[deviceName];
  expandedIec61850.value = { ...expandedIec61850.value };
};

const toggleIec61850Category = (deviceName: string, nodeKey: string) => {
  const key = `${deviceName}::${nodeKey}`;
  expandedCategories.value[key] = !expandedCategories.value[key];
  expandedCategories.value = { ...expandedCategories.value };
};

// 点击设备行：如果是 IEC61850 设备则展开/折叠树，同时选中设备
const handleDeviceClick = (device: any) => {
  selectedNodeKey.value = `device-${device.name}`;
  if (props.iec61850Map[device.name]) {
    toggleIec61850(device.name);
  }
  emit("device-click", device);
};

// 点击 IEC61850 子节点
const handleChildClick = (deviceName: string, child: TreeNode) => {
  selectedNodeKey.value = child.nodeKey;
  if (child.isGroup) {
    toggleIec61850Category(deviceName, child.nodeKey);
  }
  // 发出 node-click 事件，传递完整的节点信息（包含 category/type）
  emit("node-click", {
    ...child,
    deviceName,
    isIec61850Child: child.isIec61850Child === true,
  });
};

// 点击 IEC61850 子项 (LD 层)
const handleSubChildClick = (subChild: TreeNode, deviceName: string) => {
  selectedNodeKey.value = subChild.nodeKey;
  if (subChild.isGroup) {
    toggleIec61850Category(deviceName, subChild.nodeKey);
  }
  // 发出 node-click 事件，传递完整的节点信息
  emit("node-click", {
    ...subChild,
    isIec61850Child: subChild.isIec61850Child === true,
    deviceName: subChild.deviceName || deviceName,
  });
};

// 点击 IEC61850 LN 子节点 (第三层)
const handleLnChildClick = (lnChild: TreeNode) => {
  selectedNodeKey.value = lnChild.nodeKey;
  // 如果 LN 有子节点（如 DataSet 下的数据集），切换展开/折叠
  // LN 节点不触发导航（只有叶子节点如数据集的 DS 才导航到主面板）
  if (lnChild.isGroup) {
    toggleIec61850Category(lnChild.deviceName || "", lnChild.nodeKey);
    return;
  }
  // 无子节点的 LN 也允许导航
  emit("node-click", {
    ...lnChild,
    isIec61850Child: true,
    deviceName: lnChild.deviceName,
  });
};

// 点击 IEC61850 数据集子节点 (第四层)
const handleDsChildClick = (dsChild: TreeNode) => {
  selectedNodeKey.value = dsChild.nodeKey;
  // 发出 node-click 事件，传递完整的节点信息
  emit("node-click", {
    ...dsChild,
    isIec61850Child: true,
    deviceName: dsChild.deviceName,
  });
};

// 当 iec61850Map 变化时，重置展开状态
watch(
  () => props.iec61850Map,
  () => {
    // 数据刷新时重置展开状态
  },
  { deep: true },
);

// 路由刷新时，同步 selectedNodeKey 以正确高亮当前设备
watch(
  () => props.currentDeviceName,
  (name) => {
    if (name) {
      selectedNodeKey.value = `device-${name}`;
    }
  },
  { immediate: true },
);
</script>

<style lang="scss" scoped>
.ungrouped-section {
  margin: 20px 12px 10px;
  border-top: 1px solid var(--sb-border);
  padding-top: 20px;
}

/* ===== 拖拽修改设备分组 ===== */
.ungrouped-item.is-dragging {
  opacity: 0.4;
}

.ungrouped-section.is-drop-target {
  outline: 2px dashed var(--color-primary);
  outline-offset: 2px;
  border-radius: 10px;
}

.ungrouped-empty {
  padding: 16px 14px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  text-align: center;
  border: 1px dashed var(--sb-border);
  border-radius: 10px;
}

.ungrouped-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  color: var(--text-secondary);
  border-radius: 8px;
  transition: all 0.2s;
}

.ungrouped-header:hover {
  background-color: var(--item-hover-bg);
  color: var(--text-primary);
}

.header-left {
  display: flex;
  align-items: center;
  cursor: pointer;
  flex: 1;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: 600;
}

.header-left .el-icon {
  margin-right: 10px;
  transition: transform 0.2s;
}

.header-left .el-icon.is-expanded {
  transform: rotate(90deg);
}

.header-actions {
  display: flex;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.ungrouped-header:hover .header-actions {
  opacity: 1;
}

.header-actions .el-button {
  padding: 5px;
  color: var(--text-secondary);
  border-radius: 6px;
  transition: all 0.2s;
}

.header-actions .el-button:hover {
  background-color: var(--item-active-bg);
  color: var(--color-primary);
}

.ungrouped-list {
  padding: 8px 0 0 10px;
}

.ungrouped-item-wrapper {
  margin-bottom: 2px;
}

.ungrouped-item {
  display: flex;
  align-items: center;
  min-width: 0;
  overflow: hidden;
  padding: 10px 14px;
  cursor: pointer;
  border-radius: 10px;
  transition: all 0.2s;
  color: var(--text-secondary);
}

.ungrouped-item:hover {
  background-color: var(--item-hover-bg);
  color: var(--text-primary);
}

.ungrouped-item.is-active {
  background: var(--item-active-bg);
  color: var(--color-primary);
  font-weight: 600;
  box-shadow: inset 2px 0 0 var(--color-primary);
}

.ungrouped-item .node-icon {
  margin-right: 12px;
  font-size: 18px;
  color: var(--text-secondary);
}

.ungrouped-item .iec61850-icon {
  color: var(--color-primary);
  cursor: pointer;
}

.ungrouped-item .device-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13.5px;
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

.ungrouped-item:hover .node-actions {
  opacity: 1;
}

.node-actions .el-button {
  padding: 5px;
  margin-left: 0;
  color: var(--text-secondary);
  border-radius: 6px;
}

.node-actions .el-button:hover {
  background-color: var(--item-active-bg);
  color: var(--color-primary);
}

/* 展开箭头 */
.expand-arrow {
  width: 16px;
  height: 16px;
  margin-right: 2px;
  font-size: 12px;
  color: var(--text-secondary);
  transition: transform 0.2s;
  flex-shrink: 0;
}

.expand-arrow.is-expanded {
  transform: rotate(90deg);
}

.expand-arrow-placeholder {
  width: 16px;
  margin-right: 2px;
  flex-shrink: 0;
}

.expand-arrow-placeholder.small {
  width: 12px;
  margin-right: 1px;
}

.expand-arrow.small {
  width: 12px;
  height: 12px;
  font-size: 10px;
  margin-right: 1px;
}

/* IEC61850 子节点样式 */
.iec61850-children {
  padding: 4px 0 6px 24px;
}

.iec61850-child-item {
  border-radius: 8px;
  transition: all 0.15s;
}

.iec61850-child-item.is-group {
  font-weight: 500;
}

.child-row {
  display: flex;
  align-items: center;
  padding: 6px 10px;
  cursor: pointer;
  border-radius: 8px;
  transition: all 0.15s;
  color: var(--text-secondary);
}

.child-row:hover {
  background-color: var(--item-hover-bg);
  color: var(--text-primary);
}

.child-row.is-selected {
  background: var(--item-active-bg);
  color: var(--color-primary);
  font-weight: 500;
}

.child-icon {
  margin-right: 10px;
  font-size: 16px;
  color: var(--color-primary);
}

.iec61850-child-item:not(.is-group) .child-icon {
  color: var(--text-secondary);
}

.child-label {
  font-size: 12.5px;
}

/* IEC61850 子项 */
.iec61850-sub-children {
  padding: 2px 0 4px 20px;
}

.iec61850-sub-item {
  display: flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.iec61850-sub-item:hover {
  background-color: var(--item-hover-bg);
  color: var(--text-primary);
}

.iec61850-sub-item.is-selected {
  background: var(--item-active-bg);
  color: var(--color-primary);
  font-weight: 500;
}

.sub-icon {
  margin-right: 8px;
  font-size: 14px;
  color: var(--text-secondary);
}

.sub-label {
  font-size: 12px;
}

/* LD 下的 LN 子节点 (第三层) */
.iec61850-ln-children {
  padding: 2px 0 4px 16px;
}

.iec61850-ln-item {
  display: flex;
  align-items: center;
  padding: 3px 6px;
  border-radius: 5px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.iec61850-ln-item:hover {
  background-color: var(--item-hover-bg);
  color: var(--text-primary);
}

.iec61850-ln-item.is-selected {
  background: var(--item-active-bg);
  color: var(--color-primary);
  font-weight: 500;
}

.ln-icon {
  margin-right: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.ln-label {
  font-size: 11.5px;
}

/* LN 行（可展开/折叠） */
.iec61850-ln-row {
  display: flex;
  align-items: center;
  flex: 1;
  padding: 3px 4px;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.15s;
}

.iec61850-ln-row:hover {
  background-color: var(--item-hover-bg);
}

/* LN 下的数据集子节点 (第四层) */
.iec61850-ds-children {
  padding: 2px 0 4px 14px;
}

.iec61850-ds-item {
  display: flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 4px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.iec61850-ds-item:hover {
  background-color: var(--item-hover-bg);
  color: var(--text-primary);
}

.iec61850-ds-item.is-selected {
  background: var(--item-active-bg);
  color: var(--color-primary);
  font-weight: 500;
}

.ds-icon {
  margin-right: 5px;
  font-size: 11px;
  color: var(--text-secondary);
}

.ds-label {
  font-size: 11px;
}
</style>
