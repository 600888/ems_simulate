<template>
  <el-aside
    class="sidebar"
    :style="sidebarStyle"
    :class="[
      `sidebar-theme-${currentTheme}`,
      { 'sidebar-collapsed': sidebarDisplayCollapsed },
      { 'sidebar-overlay-mode': overlayMode },
      { 'is-resizing': isResizing },
    ]"
  >
    <el-scrollbar ref="scrollbarRef">
      <!-- 1. 头部徽标与主题切换 -->
      <SideNavHeader :is-collapse="sidebarDisplayCollapsed" />

      <!-- 2. 操作按钮组 -->
      <SideNavActions
        :is-collapse="sidebarDisplayCollapsed"
        @add-device="showAddDeviceDialog"
        @add-group="() => showAddGroupDialog()"
      />

      <!-- 3. 设备组树形菜单 -->
      <SideNavTree
        :key="treeKey"
        :tree-data="treeData"
        :tree-props="treeProps"
        :expanded-keys="expandedKeys"
        :current-node-key="currentNodeKey"
        :is-collapse="sidebarDisplayCollapsed"
        @node-click="handleNodeClick"
        @group-command="handleGroupCommand"
        @edit-device="handleEditDevice"
        @delete-device="handleDeleteDevice"
        @copy-device="handleCopyDevice"
      />

      <!-- 4. 未分组设备 -->
      <SideNavUngrouped
        :ungrouped-devices="ungroupedDevices"
        :iec61850-map="iec61850UngroupedMap as any"
        :expanded="ungroupedExpanded"
        :current-device-name="currentDeviceName"
        :is-collapse="sidebarDisplayCollapsed"
        @toggle="toggleUngrouped"
        @device-click="handleDeviceClick"
        @edit-device="handleEditDeviceByName"
        @delete-device="handleDeleteDeviceByName"
        @group-command="handleUngroupedCommand"
        @copy-device="handleCopyDeviceByName"
        @node-click="handleUngroupedNodeClick"
      />
    </el-scrollbar>

    <!-- 6. 后端状态栏 -->
    <SideBarStatus :is-collapse="sidebarDisplayCollapsed" />

    <div
      v-if="!sidebarDisplayCollapsed && !overlayMode"
      class="sidebar-resizer"
      role="separator"
      aria-orientation="vertical"
      aria-label="调整侧边栏宽度"
      :aria-valuenow="sidebarWidth"
      :aria-valuemin="SIDEBAR_MIN_WIDTH"
      :aria-valuemax="SIDEBAR_MAX_WIDTH"
      tabindex="0"
      title="拖动调整侧边栏宽度，双击恢复默认宽度"
      @pointerdown="startSidebarResize"
      @dblclick="resetSidebarWidth"
      @keydown.left.prevent="adjustSidebarWidth(-10)"
      @keydown.right.prevent="adjustSidebarWidth(10)"
    />
  </el-aside>

  <!-- 5. 对话框组件 -->
  <AddDeviceDialog
    v-model:visible="addDeviceDialogVisible"
    :channel-id="editingChannelId"
    :initial-group-id="parentGroupIdForNewDevice"
    @success="handleDeviceAdded"
    @close="editingChannelId = null"
  />

  <AddDeviceGroupDialog
    v-model:visible="addGroupDialogVisible"
    :group-id="editingGroupId"
    :parent-options="groupTreeForSelect"
    :initial-parent-id="parentGroupIdForNewGroup"
    @success="handleGroupChanged"
    @close="editingGroupId = null"
  />

  <CopyDeviceDialog
    v-model:visible="copyDeviceDialogVisible"
    :channel-id="copyingChannelId || 0"
    :device-name="copyingDeviceName"
    :device-ip="copyingDeviceIp"
    :device-port="copyingDevicePort"
    :point-count="copyingPointCount"
    :protocol-type="copyingProtocolType"
    :model-name="copyingModelName"
    :model-path="copyingModelPath"
    :device-group-id="copyingDeviceGroupId"
    :group-options="groupTreeForSelect"
    @success="handleCopyDeviceSuccess"
    @close="handleCopyDeviceClose"
  />
</template>

<script lang="ts" setup>
import { useI18n } from "vue-i18n";
import { onMounted, onUnmounted, ref, computed, watch, nextTick } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import type { ElTree, ElScrollbar } from "element-plus";

import SideNavHeader from "@/components/layout/SideNavHeader.vue";
import SideNavActions from "@/components/layout/SideNavActions.vue";
import SideNavTree from "@/components/layout/SideNavTree.vue";
import SideNavUngrouped from "@/components/layout/SideNavUngrouped.vue";
import SideBarStatus from "@/components/layout/SideBarStatus.vue";
import AddDeviceDialog from "@/components/device/AddDeviceDialog.vue";
import AddDeviceGroupDialog from "@/components/device/AddDeviceGroupDialog.vue";
import CopyDeviceDialog from "@/components/device/CopyDeviceDialog.vue";

import { currentTheme } from "@/utils/theme";
import { isCollapse, sidebarOverlayMode } from "@/components/header/isCollapse";
import menuRouter from "@/router/index";
import {
  delView,
  visitedViews,
  updateChannelIdDeviceMap,
} from "@/store/tagsView";
import { deleteChannel, getChannelList } from "@/api/channelApi";
import {
  getDeviceGroupTree,
  deleteDeviceGroup,
  batchDeviceOperation,
  type DeviceGroupTreeNode,
  type DeviceInfo,
} from "@/api/deviceGroupApi";
import { useIec61850Tree, type TreeNode } from "@/composables";
import { useSidebarRefresh } from "@/composables";
import { effectiveViewportWidth } from "@/composables/useAppSettings";

const router = useRouter();
const { t } = useI18n();
const overlayMode = sidebarOverlayMode;
const isCompactViewport = computed(() => effectiveViewportWidth.value < 1200);
const sidebarDisplayCollapsed = computed(() =>
  isCompactViewport.value ? !overlayMode.value : isCollapse.value,
);
const treeRef = ref<InstanceType<typeof ElTree>>();
const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>();

const SIDEBAR_DEFAULT_WIDTH = 280;
const SIDEBAR_MIN_WIDTH = 240;
const SIDEBAR_MAX_WIDTH = 480;
const SIDEBAR_WIDTH_STORAGE_KEY = "sidebar-width";
const sidebarWidth = ref(SIDEBAR_DEFAULT_WIDTH);
const isResizing = ref(false);
const sidebarStyle = computed(() => ({
  "--sidebar-width": `${sidebarWidth.value}px`,
}));

const clampSidebarWidth = (width: number) =>
  Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, width));

const setSidebarWidth = (width: number, persist = true) => {
  sidebarWidth.value = clampSidebarWidth(width);
  if (persist)
    localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(sidebarWidth.value));
};

const handleSidebarResize = (event: PointerEvent) => {
  if (!isResizing.value) return;
  setSidebarWidth(event.clientX, false);
};

const stopSidebarResize = () => {
  if (!isResizing.value) return;
  isResizing.value = false;
  localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(sidebarWidth.value));
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
  window.removeEventListener("pointermove", handleSidebarResize);
  window.removeEventListener("pointerup", stopSidebarResize);
};

const startSidebarResize = (event: PointerEvent) => {
  if (event.button !== 0) return;
  isResizing.value = true;
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
  window.addEventListener("pointermove", handleSidebarResize);
  window.addEventListener("pointerup", stopSidebarResize);
};

const adjustSidebarWidth = (delta: number) =>
  setSidebarWidth(sidebarWidth.value + delta);
const resetSidebarWidth = () => setSidebarWidth(SIDEBAR_DEFAULT_WIDTH);

// 状态管理
const addDeviceDialogVisible = ref(false);
const addGroupDialogVisible = ref(false);
const editingChannelId = ref<number | null>(null);
const editingGroupId = ref<number | null>(null);
const parentGroupIdForNewDevice = ref<number | null>(null);
const parentGroupIdForNewGroup = ref<number | null>(null);

const copyDeviceDialogVisible = ref(false);
const copyingChannelId = ref<number | null>(null);
const copyingDeviceName = ref<string>("");
const copyingDeviceIp = ref<string>("");
const copyingDevicePort = ref<number>(502);
const copyingPointCount = ref<number>(0);
const copyingProtocolType = ref<number>(-1);
const copyingModelName = ref<string>("");
const copyingModelPath = ref<string>("");
const copyingDeviceGroupId = ref<number | null>(null);

const treeData = ref<TreeNode[]>([]);
const treeKey = ref(0); // 递增计数，强制 el-tree 重建
const ungroupedDevices = ref<DeviceInfo[]>([]);
const expandedKeys = ref<string[]>([]);
const currentNodeKey = ref<string>("");
const currentDeviceName = ref<string>("");
const ungroupedExpanded = ref(true);

// IEC61850 设备树 composable
const {
  iec61850UngroupedMap,
  fetchIEC61850Structure,
  markIEC61850Devices,
  markUngroupedIEC61850Devices,
  setStructureLoadedCallback,
  invalidateStructureCache,
} = useIec61850Tree();

// IEC61850 结构加载完成后强制重建 el-tree
setStructureLoadedCallback(() => {
  treeKey.value++;
});

// 侧边栏刷新触发器
const { refreshCounter } = useSidebarRefresh();

const treeProps = { children: "children", label: "label" };

// 计算父级设备组选项
const groupTreeForSelect = computed(() => {
  const convertToSelectTree = (nodes: TreeNode[]): DeviceGroupTreeNode[] => {
    return nodes
      .filter((n) => n.isGroup)
      .map((n) => ({
        id: n.id,
        code: "",
        name: n.name,
        parent_id: null,
        description: null,
        status: 0,
        enable: true,
        created_at: null,
        updated_at: null,
        children: n.children ? convertToSelectTree(n.children) : [],
        devices: [],
      }));
  };
  return convertToSelectTree(treeData.value);
});

// 数据转换逻辑
const transformToTreeData = (groups: DeviceGroupTreeNode[]): TreeNode[] => {
  return groups.map((group) => {
    const children: TreeNode[] = [];
    if (group.children?.length)
      children.push(...transformToTreeData(group.children));
    if (group.devices?.length) {
      children.push(
        ...group.devices.map((d) => ({
          nodeKey: `device-${d.name}`,
          label: d.name,
          isGroup: false,
          id: d.id,
          name: d.name,
          groupId: group.id,
        })),
      );
    }
    return {
      nodeKey: `group-${group.id}`,
      label: group.name,
      isGroup: true,
      id: group.id,
      name: group.name,
      children,
    };
  });
};

// 获取 IEC61850 子节点结构
// IEC61850 逻辑已提取到 useIec61850Tree composable

const fetchDeviceGroupTree = async () => {
  try {
    const response = await getDeviceGroupTree();
    const newTreeData = transformToTreeData(response.groups || []);
    const newUngrouped = response.ungrouped || [];

    // 准备要展开的keys
    const newExpandedKeys: string[] = [];

    if (currentDeviceName.value) {
      currentNodeKey.value = `device-${currentDeviceName.value}`;

      // 遍历寻找当前设备所在的分组并展开
      const findAndExpand = (nodes: TreeNode[]) => {
        for (const node of nodes) {
          if (node.isGroup && node.children) {
            // 检查直接子节点是否有该设备
            const hasDevice = node.children.some(
              (child: TreeNode) =>
                !child.isGroup && child.name === currentDeviceName.value,
            );
            if (hasDevice) {
              if (!newExpandedKeys.includes(node.nodeKey)) {
                newExpandedKeys.push(node.nodeKey);
              }
              return true;
            }
            // 递归检查子分组
            if (findAndExpand(node.children)) {
              if (!newExpandedKeys.includes(node.nodeKey)) {
                newExpandedKeys.push(node.nodeKey);
              }
              return true;
            }
          }
        }
        return false;
      };

      findAndExpand(newTreeData);
    }

    // 批量更新状态
    expandedKeys.value = newExpandedKeys;
    ungroupedDevices.value = newUngrouped;
    treeData.value = newTreeData; // 最后更新 treeData，触发 SideNavTree 的监听

    // 标记并获取 IEC61850 设备结构
    await markIEC61850Devices(newTreeData, treeData);

    // 标记并获取未分组设备的 IEC61850 结构
    await markUngroupedIEC61850Devices(newUngrouped);

    // 构建 channelId -> deviceName 映射，供 TagsView 在 GOOSE/报告/文件页面高亮对应设备标签
    const channels = await getChannelList();
    channels.forEach((ch) => {
      if (ch.name) updateChannelIdDeviceMap(ch.id, ch.name);
    });

    // 如果是未分组设备，展开未分组区域
    if (currentDeviceName.value) {
      const isUngrouped = newUngrouped.some(
        (d) => d.name === currentDeviceName.value,
      );
      if (isUngrouped) {
        ungroupedExpanded.value = true;
      }

      // 等待展开动画或渲染后滚动
      nextTick(() => {
        scrollToCurrentDevice();
      });
    }
  } catch (error: any) {
    console.error("获取设备组失败:", error);
    // error message is handled by global interceptor
  }
};

// 交互处理
const handleNodeClick = (data: TreeNode) => {
  // 如果有 linkTo，直接导航 (如 GOOSE 节点导航到 /goose)
  if (data.linkTo) {
    router.push(data.linkTo);
    return;
  }
  if (data.isIec61850Child) {
    // IEC61850 子节点点击: 携带 category/item 导航到设备页面
    // data.type 是分类 (如 "DataModel")，data.value 是完整过滤路径 (如 "GenericLD/MMXU1")
    const deviceName = data.deviceName || data.name;
    const category = data.type || (data.isGroup ? data.name : "");
    // DataSets 下的分组节点(LD/LN)只做展开/折叠，不做导航
    if (category === "DataSets" && data.isGroup) {
      return;
    }
    // 优先使用 value (DataModel 下 LN 节点的完整路径)，其次使用 name
    const item = data.isGroup ? "" : data.value || data.name || data.label;
    navigateToDevice(deviceName, false, data.isIec61850Child, {
      ...data,
      _category: category,
      _item: item,
    });
    return;
  }
  if (!data.isGroup) navigateToDevice(data.name);
};

const handleDeviceClick = (device: DeviceInfo) => navigateToDevice(device.name);

// 处理未分组区域的 IEC61850 子节点点击
const handleUngroupedNodeClick = (data: any) => {
  // 如果有 linkTo，直接导航
  if (data.linkTo) {
    router.push(data.linkTo);
    return;
  }
  if (data.isIec61850Child) {
    // 找到该子节点所属的设备名
    const deviceName = data.deviceName || currentDeviceName.value;
    // 构建 category 和 item 信息
    // data.type 是分类 (如 "DataModel")，data.value 是完整过滤路径 (如 "GenericLD/MMXU1")
    const category = data.type || (data.isGroup ? data.name : "");
    const item = data.isGroup ? "" : data.value || data.name;
    navigateToDevice(deviceName, false, true, {
      ...data,
      _category: category,
      _item: item,
    });
  }
};

const navigateToDevice = (
  deviceName: string,
  forceRefresh = false,
  isIec61850Child = false,
  treeNode?: any,
) => {
  // 关闭 overlay 模式（small 断点下弹出后点击导航自动收起）
  sidebarOverlayMode.value = false;
  currentDeviceName.value = deviceName;
  currentNodeKey.value = `device-${deviceName}`;
  const path = `/device/${deviceName}`;
  localStorage.setItem("activeRoute", path);

  // 构建查询参数，IEC61850 子节点携带 category/item
  const query: Record<string, string> = {};
  if (isIec61850Child && treeNode) {
    // 优先使用 _category/_item (来自 handleUngroupedNodeClick 的计算值)
    const category =
      treeNode._category ||
      (treeNode.isGroup
        ? treeNode.type || treeNode.name || treeNode.label
        : "");
    const item =
      treeNode._item ||
      (treeNode.isGroup ? "" : treeNode.name || treeNode.label);
    if (category) query.category = category;
    if (item) query.item = item;
  }

  if (forceRefresh) {
  }
  router.push({
    path,
    query: Object.keys(query).length > 0 ? query : undefined,
  });
};

const showAddDeviceDialog = () => {
  editingChannelId.value = null;
  parentGroupIdForNewDevice.value = null;
  addDeviceDialogVisible.value = true;
};

const showAddGroupDialog = (parentId?: number) => {
  editingGroupId.value = null;
  parentGroupIdForNewGroup.value = parentId || null;
  addGroupDialogVisible.value = true;
};

const handleGroupCommand = async (command: string, data: TreeNode) => {
  const actions: Record<string, Function> = {
    edit: () => {
      editingGroupId.value = data.id;
      addGroupDialogVisible.value = true;
    },
    addDevice: () => {
      parentGroupIdForNewDevice.value = data.id;
      addDeviceDialogVisible.value = true;
    },
    addSubGroup: () => showAddGroupDialog(data.id),
    startAll: () => handleBatchOperation(data.id, "start"),
    stopAll: () => handleBatchOperation(data.id, "stop"),
    delete: () => handleDeleteGroup(data),
    cascadeDelete: () => handleDeleteGroup(data, true),
  };
  actions[command]?.();
};

const handleUngroupedCommand = async (command: string) => {
  const actions: Record<string, Function> = {
    addDevice: () => {
      parentGroupIdForNewDevice.value = null;
      addDeviceDialogVisible.value = true;
    },
    startAll: () => handleBatchOperation(0, "start"),
    stopAll: () => handleBatchOperation(0, "stop"),
  };
  actions[command]?.();
};

const handleBatchOperation = async (
  groupId: number,
  operation: "start" | "stop" | "reset",
) => {
  await batchDeviceOperation(groupId, operation);
  ElMessage.success(
    t("sidebar." + (operation === "start" ? "startSuccess" : "stopSuccess")),
  );
};

const handleDeleteGroup = async (data: TreeNode, cascade = false) => {
  await ElMessageBox.confirm(
    t(
      cascade
        ? "sidebar.confirmCascadeDeleteGroup"
        : "sidebar.confirmDeleteGroup",
      { name: data.name },
    ),
    t(cascade ? "sidebar.cascadeDeleteTitle" : "common.hint"),
    {
      confirmButtonText: t(
        cascade ? "sidebar.confirmCascadeDelete" : "common.confirm",
      ),
      cancelButtonText: t("common.cancel"),
      type: cascade ? "error" : "warning",
      confirmButtonClass: cascade ? "el-button--danger" : "",
    },
  );
  await deleteDeviceGroup(data.id, cascade);
  ElMessage.success(t("sidebar.success"));
  await fetchDeviceGroupTree();
};

const handleEditDevice = (data: TreeNode) => handleEditDeviceByName(data.name);
const handleEditDeviceByName = async (deviceName: string) => {
  const channel = (await getChannelList()).find((c) => c.name === deviceName);
  if (channel) {
    editingChannelId.value = channel.id;
    addDeviceDialogVisible.value = true;
  }
};

const handleDeleteDevice = (data: TreeNode) =>
  handleDeleteDeviceByName(data.name);
const handleDeleteDeviceByName = async (deviceName: string) => {
  await ElMessageBox.confirm(
    t("sidebar.confirmDeleteDevice", { name: deviceName }),
    t("common.hint"),
    {
      confirmButtonText: t("common.confirm"),
      cancelButtonText: t("common.cancel"),
      type: "warning",
    },
  );
  const channel = (await getChannelList()).find((c) => c.name === deviceName);
  if (channel) {
    await deleteChannel(channel.id);
    ElMessage.success(t("sidebar.deleteSuccess"));

    const path = `/device/${deviceName}`;
    // 如果存在这个标签，需要关闭它
    const targetView = visitedViews.value.find((v) => v.path === path);
    if (targetView) {
      await delView(targetView);
    }

    if (currentDeviceName.value === deviceName) {
      currentDeviceName.value = "";
      currentNodeKey.value = "";
      localStorage.removeItem("activeRoute");

      // Navigate to another view if available
      const latestView = visitedViews.value.slice(-1)[0];
      if (latestView) {
        router.push(latestView.path as string);
      } else {
        router.push("/");
      }
    }

    if (menuRouter.hasRoute(deviceName)) {
      menuRouter.removeRoute(deviceName);
    }

    await fetchDeviceGroupTree();
  }
};

const handleCopyDevice = async (data: TreeNode) => {
  await handleCopyDeviceByName(data.name, data.groupId || null);
};

const handleCopyDeviceByName = async (
  deviceName: string,
  groupId: number | null = null,
) => {
  try {
    const channelList = await getChannelList();
    const channel = channelList.find((c) => c.name === deviceName);
    if (channel) {
      copyingChannelId.value = channel.id;
      copyingDeviceName.value = channel.name;
      copyingDeviceIp.value = channel.ip || "0.0.0.0";
      copyingDevicePort.value = channel.port || 502;
      copyingPointCount.value = 0;
      copyingProtocolType.value = channel.protocol_type;
      copyingModelName.value = channel.model_name || "";
      copyingModelPath.value = channel.icd_path || "";
      copyingDeviceGroupId.value = groupId;
      copyDeviceDialogVisible.value = true;
    }
  } catch (error) {
    console.error("获取设备信息失败:", error);
  }
};

const handleCopyDeviceClose = () => {
  copyingChannelId.value = null;
  copyingProtocolType.value = -1;
  copyingModelName.value = "";
  copyingModelPath.value = "";
  copyingDeviceGroupId.value = null;
};

const handleCopyDeviceSuccess = async () => {
  await fetchDeviceGroupTree();
};

const handleDeviceAdded = async (
  deviceName: string,
  isEdit?: boolean,
  oldName?: string,
) => {
  if (isEdit && oldName && oldName !== deviceName)
    menuRouter.removeRoute(oldName);
  menuRouter.addRoute({
    path: `/device/${deviceName}`,
    name: deviceName,
    component: () => import("@/views/Device.vue"),
  });
  await fetchDeviceGroupTree();

  // 自动展开新设备所在的分组
  let found = false;
  // 1. 检查分组设备
  const expandGroup = (nodes: TreeNode[]) => {
    for (const node of nodes) {
      if (node.isGroup && node.children) {
        // 检查子节点是否由新设备
        const hasDevice = node.children.some(
          (child: TreeNode) => !child.isGroup && child.name === deviceName,
        );
        if (hasDevice) {
          if (!expandedKeys.value.includes(node.nodeKey)) {
            expandedKeys.value.push(node.nodeKey);
          }
          found = true;
          return; // 暂不支持多层嵌套展开，找到即止，若支持多层需递归查找
        }
        // 递归检查子分组
        expandGroup(node.children);
        if (found) return;
      }
    }
  };
  expandGroup(treeData.value);

  // 2. 检查未分组
  if (!found) {
    const isUngrouped = ungroupedDevices.value.some(
      (d) => d.name === deviceName,
    );
    if (isUngrouped) {
      ungroupedExpanded.value = true;
    }
  }

  // 3. 滚动到当前设备
  nextTick(() => {
    scrollToCurrentDevice();
  });

  navigateToDevice(deviceName, isEdit);
};

const scrollToCurrentDevice = () => {
  if (!scrollbarRef.value) return;

  // 查找当前选中的节点 DOM
  // element-plus 的 tree 节点 current 类名为 is-current
  // 但不仅仅是在 tree 中，未分组列表也可能有

  const treeNode = document.querySelector(".el-tree-node.is-current");
  const ungroupedNode = document.querySelector(".ungrouped-item.is-active");

  const target =
    treeNode || ungroupedNode || document.querySelector(".is-current");

  if (target) {
    target.scrollIntoView({ block: "center", behavior: "smooth" });
  }
};

const handleGroupChanged = () => fetchDeviceGroupTree();
const toggleUngrouped = () => {
  ungroupedExpanded.value = !ungroupedExpanded.value;
};

onMounted(async () => {
  const storedSidebarWidth = Number(
    localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY),
  );
  if (Number.isFinite(storedSidebarWidth) && storedSidebarWidth > 0) {
    setSidebarWidth(storedSidebarWidth, false);
  }
  await fetchDeviceGroupTree();
  // 检查是否有添加设备后的待导航设备
  const pendingDevice = localStorage.getItem("_pendingDevice");
  if (pendingDevice) {
    localStorage.removeItem("_pendingDevice");
    // 静态 route '/device/:deviceName' 已存在，直接 push 即可
    router.push(`/device/${pendingDevice}`);
  }
  const collapsed = localStorage.getItem("isCollapse");
  if (collapsed) isCollapse.value = collapsed === "true";
});

onUnmounted(stopSidebarResize);

// 监听路由同步
watch(
  () => router.currentRoute.value.params.deviceName,
  (name) => {
    if (name) {
      const nameStr = name as string;
      currentDeviceName.value = nameStr;
      currentNodeKey.value = `device-${nameStr}`;
    }
  },
  { immediate: true },
);

// 监听侧边栏刷新触发（如 IEC61850 客户端连接成功）
watch(refreshCounter, () => {
  // 清除结构缓存，强制从后端重新获取最新 IEC61850 结构数据
  invalidateStructureCache();
  fetchDeviceGroupTree();
});
</script>

<style lang="scss" scoped>
/* 全局侧边栏基础样式 - 通过主题变量驱动 */
.sidebar {
  position: relative;
  display: flex;
  flex-direction: column;
  width: var(--sidebar-width) !important;
  min-width: var(--sidebar-width);
  max-width: var(--sidebar-width);
  flex: 0 0 var(--sidebar-width);
  height: 100%;
  background: var(--sb-bg-main);
  border-right: 1px solid var(--sb-border);
  transition:
    width 0.3s ease,
    min-width 0.3s ease,
    max-width 0.3s ease,
    flex-basis 0.3s ease;
  overflow: visible;
  box-shadow: var(--sb-shadow);

  &.is-resizing {
    transition: none;
  }

  /* 让滚动区域弹性伸缩占满剩余空间，将状态栏固定在底部 */
  :deep(> .el-scrollbar) {
    flex: 1;
    min-height: 0;
    height: auto;
    overflow: hidden;
  }

  &.sidebar-collapsed {
    width: var(--sidebar-collapsed-width) !important;
    min-width: var(--sidebar-collapsed-width);
    max-width: var(--sidebar-collapsed-width);
    flex-basis: var(--sidebar-collapsed-width);

    /* 折叠时隐藏树形结构的文字和操作按钮，只显示图标 */
    :deep(.device-tree) {
      padding: 0 6px;

      .el-tree-node__content {
        padding-left: 0 !important;
        padding-right: 0 !important;
        justify-content: center;
      }

      .el-tree-node__expand-icon {
        display: none;
      }

      .tree-node-content {
        justify-content: center;
        padding-left: 0;
      }

      .node-label,
      .node-actions {
        display: none !important;
      }

      .node-icon {
        margin-right: 0;
      }
    }

    /* 折叠时隐藏未分组设备区域 */
    :deep(.ungrouped-section) {
      margin: 10px 6px;
      padding-top: 10px;

      .ungrouped-header {
        justify-content: center;
        padding: 10px;

        span {
          display: none;
        }

        .el-icon {
          margin-right: 0;
        }
      }

      .ungrouped-list {
        padding: 8px 0 0 0;
      }

      .ungrouped-item {
        justify-content: center;
        padding: 10px;

        span,
        .node-actions,
        .expand-arrow,
        .expand-arrow-placeholder {
          display: none !important;
        }

        .el-icon {
          margin-right: 0;
        }
      }

      .iec61850-children,
      .iec61850-sub-children {
        display: none !important;
      }
    }
  }
}

.sidebar-resizer {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  width: 6px;
  cursor: col-resize;
  outline: none;
}

.sidebar-resizer::before {
  content: "⠿";
  position: absolute;
  top: 50%;
  left: 100%;
  display: grid;
  place-items: center;
  width: 22px;
  height: 48px;
  border: 1px solid var(--el-border-color);
  border-radius: 7px;
  background: var(--el-bg-color);
  box-shadow: var(--el-box-shadow-light);
  color: var(--el-text-color-secondary);
  font-size: 18px;
  line-height: 1;
  transform: translate(-50%, -50%);
  transition:
    border-color 0.2s,
    color 0.2s;
  pointer-events: none;
}

.sidebar-resizer::after {
  content: "";
  position: absolute;
  top: 0;
  right: 0;
  width: 2px;
  height: 100%;
  background: var(--color-primary);
  opacity: 0;
  transition: opacity 0.2s;
}

.sidebar-resizer:hover::after,
.sidebar-resizer:focus-visible::after,
.sidebar.is-resizing .sidebar-resizer::after {
  opacity: 0.7;
}

.sidebar-resizer:hover::before,
.sidebar-resizer:focus-visible::before,
.sidebar.is-resizing .sidebar-resizer::before {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

/* 主题类定义 */
.sidebar-theme-light {
  --sb-bg-main: linear-gradient(180deg, #fdfdff 0%, #f5f7fa 100%);
  --sb-logo-bg: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
  --sb-logo-shadow: rgba(79, 70, 229, 0.25);
  --sb-text-primary: #2d3748;
  --sb-text-secondary: #64748b;
  --sb-btn-primary-bg: rgba(79, 70, 229, 0.1);
  --sb-btn-primary-hover: #4f46e5;
  --sb-item-hover: rgba(79, 70, 229, 0.05);
  --sb-item-active: rgba(79, 70, 229, 0.1);
  --sb-border: rgba(0, 0, 0, 0.05);
  --sb-shadow: 4px 0 15px rgba(0, 0, 0, 0.02);
  --sb-icon-color: #64748b;
  --sb-btn-text: #4f46e5;
  --sb-scrollbar: rgba(0, 0, 0, 0.1);
}

.sidebar-theme-dark {
  --sb-bg-main: linear-gradient(180deg, #293241 0%, #252e3d 100%);
  --sb-logo-bg: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  --sb-logo-shadow: rgba(37, 99, 235, 0.3);
  --sb-text-primary: #edf2f8;
  --sb-text-secondary: #aebcce;
  --sb-btn-primary-bg: rgba(59, 130, 246, 0.2);
  --sb-btn-primary-hover: #3b82f6;
  --sb-item-hover: rgba(148, 181, 224, 0.1);
  --sb-item-active: rgba(96, 165, 250, 0.2);
  --sb-border: rgba(184, 199, 219, 0.16);
  --sb-shadow: 8px 0 24px rgba(7, 12, 20, 0.16);
  --sb-icon-color: #aebcce;
  --sb-btn-text: #fff;
  --sb-scrollbar: rgba(255, 255, 255, 0.1);
}

/* small 断点下侧边栏 overlay 弹出模式 */
.sidebar-overlay-mode {
  position: fixed;
  top: 0;
  bottom: 0;
  left: 0;
  height: auto;
  width: 280px !important;
  min-width: 280px !important;
  max-width: 280px !important;
  flex-basis: 280px;
  z-index: 999;
  box-shadow: 4px 0 24px rgba(0, 0, 0, 0.2);
}
</style>
