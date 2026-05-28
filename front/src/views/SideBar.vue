<template>
  <el-aside
    class="sidebar"
    :class="[`sidebar-theme-${currentTheme}`, { 'sidebar-collapsed': isCollapse }, { 'sidebar-overlay-mode': overlayMode }]"
  >
    <el-scrollbar ref="scrollbarRef">
      <!-- 1. 头部徽标与主题切换 -->
      <SideNavHeader :is-collapse="isCollapse" />

      <!-- 2. 操作按钮组 -->
      <SideNavActions
        :is-collapse="isCollapse"
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
        :is-collapse="isCollapse"
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
        :is-collapse="isCollapse"
        @toggle="toggleUngrouped"
        @device-click="handleDeviceClick"
        @edit-device="handleEditDeviceByName"
        @delete-device="handleDeleteDeviceByName"
        @group-command="handleUngroupedCommand"
        @copy-device="handleCopyDeviceByName"
        @node-click="handleUngroupedNodeClick"
      />
    </el-scrollbar>
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
    @success="handleCopyDeviceSuccess"
    @close="copyingChannelId = null"
  />
</template>

<script lang="ts" setup>
import { useI18n } from 'vue-i18n'
import { onMounted, ref, computed, watch, nextTick } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import type { ElTree, ElScrollbar } from "element-plus";

import SideNavHeader from "@/components/layout/SideNavHeader.vue";
import SideNavActions from "@/components/layout/SideNavActions.vue";
import SideNavTree from "@/components/layout/SideNavTree.vue";
import SideNavUngrouped from "@/components/layout/SideNavUngrouped.vue";
import AddDeviceDialog from "@/components/device/AddDeviceDialog.vue";
import AddDeviceGroupDialog from "@/components/device/AddDeviceGroupDialog.vue";
import CopyDeviceDialog from "@/components/device/CopyDeviceDialog.vue";

import { currentTheme } from "@/utils/theme";
import { isCollapse, sidebarOverlayMode } from "@/components/header/isCollapse";
import menuRouter from "@/router/index";
import { delView, visitedViews } from "@/store/tagsView";
import { deleteChannel, getChannelList } from "@/api/channelApi";
import {
  getDeviceGroupTree,
  deleteDeviceGroup,
  batchDeviceOperation,
  type DeviceGroupTreeNode,
  type DeviceInfo
} from "@/api/deviceGroupApi";
import { useIec61850Tree, type TreeNode } from "@/composables";
import { useSidebarRefresh } from "@/composables";

const router = useRouter();
const { t } = useI18n()
const overlayMode = sidebarOverlayMode;
const treeRef = ref<InstanceType<typeof ElTree>>();
const scrollbarRef = ref<InstanceType<typeof ElScrollbar>>();

// 状态管理
const addDeviceDialogVisible = ref(false);
const addGroupDialogVisible = ref(false);
const editingChannelId = ref<number | null>(null);
const editingGroupId = ref<number | null>(null);
const parentGroupIdForNewDevice = ref<number | null>(null);
const parentGroupIdForNewGroup = ref<number | null>(null);

const copyDeviceDialogVisible = ref(false);
const copyingChannelId = ref<number | null>(null);
const copyingDeviceName = ref<string>('');
const copyingDeviceIp = ref<string>('');
const copyingDevicePort = ref<number>(502);
const copyingPointCount = ref<number>(0);

const treeData = ref<TreeNode[]>([]);
const treeKey = ref(0);  // 递增计数，强制 el-tree 重建
const ungroupedDevices = ref<DeviceInfo[]>([]);
const expandedKeys = ref<string[]>([]);
const currentNodeKey = ref<string>('');
const currentDeviceName = ref<string>('');
const ungroupedExpanded = ref(true);

// IEC61850 设备树 composable
const { iec61850UngroupedMap, fetchIEC61850Structure, markIEC61850Devices, markUngroupedIEC61850Devices, setStructureLoadedCallback } = useIec61850Tree();

// IEC61850 结构加载完成后强制重建 el-tree
setStructureLoadedCallback(() => {
  treeKey.value++;
});

// 侧边栏刷新触发器
const { refreshCounter } = useSidebarRefresh();

const treeProps = { children: 'children', label: 'label' };

// 计算父级设备组选项
const groupTreeForSelect = computed(() => {
  const convertToSelectTree = (nodes: TreeNode[]): DeviceGroupTreeNode[] => {
    return nodes.filter(n => n.isGroup).map(n => ({
      id: n.id,
      code: '',
      name: n.name,
      parent_id: null,
      description: null,
      status: 0,
      enable: true,
      created_at: null,
      updated_at: null,
      children: n.children ? convertToSelectTree(n.children) : [],
      devices: []
    }));
  };
  return convertToSelectTree(treeData.value);
});

// 数据转换逻辑
const transformToTreeData = (groups: DeviceGroupTreeNode[]): TreeNode[] => {
  return groups.map(group => {
    const children: TreeNode[] = [];
    if (group.children?.length) children.push(...transformToTreeData(group.children));
    if (group.devices?.length) {
      children.push(...group.devices.map(d => ({
        nodeKey: `device-${d.name}`,
        label: d.name,
        isGroup: false,
        id: d.id,
        name: d.name,
        groupId: group.id
      })));
    }
    return {
      nodeKey: `group-${group.id}`,
      label: group.name,
      isGroup: true,
      id: group.id,
      name: group.name,
      children
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
            const hasDevice = node.children.some((child: TreeNode) => !child.isGroup && child.name === currentDeviceName.value);
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

    // 如果是未分组设备，展开未分组区域
    if (currentDeviceName.value) {
      const isUngrouped = newUngrouped.some(d => d.name === currentDeviceName.value);
      if (isUngrouped) {
        ungroupedExpanded.value = true;
      }

      // 等待展开动画或渲染后滚动
      nextTick(() => {
        scrollToCurrentDevice();
      });
    }
  } catch (error: any) {
    console.error('获取设备组失败:', error);
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
    // data.type 是分类 (如 "Data Model")，data.value 是完整过滤路径 (如 "GenericLD/MMXU1")
    const deviceName = data.deviceName || data.name;
    const category = data.type || (data.isGroup ? data.name : '');
    // DataSets 下的分组节点(LD/LN)只做展开/折叠，不做导航
    if (category === 'DataSets' && data.isGroup) {
      return;
    }
    // 优先使用 value (Data Model 下 LN 节点的完整路径)，其次使用 name
    const item = data.isGroup ? '' : (data.value || data.name || data.label);
    navigateToDevice(deviceName, false, data.isIec61850Child, { ...data, _category: category, _item: item });
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
    // data.type 是分类 (如 "Data Model")，data.value 是完整过滤路径 (如 "GenericLD/MMXU1")
    const category = data.type || (data.isGroup ? data.name : '');
    const item = data.isGroup ? '' : (data.value || data.name);
    navigateToDevice(deviceName, false, true, { ...data, _category: category, _item: item });
  }
};

const navigateToDevice = (deviceName: string, forceRefresh = false, isIec61850Child = false, treeNode?: any) => {
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
    const category = treeNode._category || (treeNode.isGroup ? (treeNode.type || treeNode.name || treeNode.label) : '');
    const item = treeNode._item || (treeNode.isGroup ? '' : (treeNode.name || treeNode.label));
    if (category) query.category = category;
    if (item) query.item = item;
  }

  if (forceRefresh) {
  }
  router.push({ path, query: Object.keys(query).length > 0 ? query : undefined });
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
    edit: () => { editingGroupId.value = data.id; addGroupDialogVisible.value = true; },
    addDevice: () => { parentGroupIdForNewDevice.value = data.id; addDeviceDialogVisible.value = true; },
    addSubGroup: () => showAddGroupDialog(data.id),
    startAll: () => handleBatchOperation(data.id, 'start'),
    stopAll: () => handleBatchOperation(data.id, 'stop'),
    delete: () => handleDeleteGroup(data)
  };
  actions[command]?.();
};

const handleUngroupedCommand = async (command: string) => {
  const actions: Record<string, Function> = {
    addDevice: () => { parentGroupIdForNewDevice.value = null; addDeviceDialogVisible.value = true; },
    startAll: () => handleBatchOperation(0, 'start'),
    stopAll: () => handleBatchOperation(0, 'stop'),
  };
  actions[command]?.();
};

const handleBatchOperation = async (groupId: number, operation: 'start' | 'stop' | 'reset') => {
    await batchDeviceOperation(groupId, operation);
    ElMessage.success(t('sidebar.' + (operation === 'start' ? 'startSuccess' : 'stopSuccess')));
};

const handleDeleteGroup = async (data: TreeNode) => {
    await ElMessageBox.confirm(t('sidebar.confirmDeleteGroup', { name: data.name }), t('common.hint'), { type: 'warning' });
    await deleteDeviceGroup(data.id, false);
    ElMessage.success(t('sidebar.success'));
    await fetchDeviceGroupTree();
};

const handleEditDevice = (data: TreeNode) => handleEditDeviceByName(data.name);
const handleEditDeviceByName = async (deviceName: string) => {
  const channel = (await getChannelList()).find(c => c.name === deviceName);
  if (channel) {
    editingChannelId.value = channel.id;
    addDeviceDialogVisible.value = true;
  }
};

const handleDeleteDevice = (data: TreeNode) => handleDeleteDeviceByName(data.name);
const handleDeleteDeviceByName = async (deviceName: string) => {
  await ElMessageBox.confirm(t('sidebar.confirmDeleteDevice', { name: deviceName }), t('common.hint'), { type: 'warning' });
  const channel = (await getChannelList()).find(c => c.name === deviceName);
  if (channel) {
    await deleteChannel(channel.id);
    ElMessage.success(t('sidebar.deleteSuccess'));

    const path = `/device/${deviceName}`;
    // 如果存在这个标签，需要关闭它
    const targetView = visitedViews.value.find(v => v.path === path);
    if (targetView) {
      await delView(targetView);
    }

    if (currentDeviceName.value === deviceName) {
      currentDeviceName.value = '';
      currentNodeKey.value = '';
      localStorage.removeItem("activeRoute");

      // Navigate to another view if available
      const latestView = visitedViews.value.slice(-1)[0];
      if (latestView) {
        router.push((latestView.fullPath || latestView.path) as string);
      } else {
        router.push('/');
      }
    }

    if (menuRouter.hasRoute(deviceName)) {
      menuRouter.removeRoute(deviceName);
    }

    await fetchDeviceGroupTree();
  }
};

const handleCopyDevice = async (data: TreeNode) => {
  await handleCopyDeviceByName(data.name);
};

const handleCopyDeviceByName = async (deviceName: string) => {
  try {
    const channelList = await getChannelList();
    const channel = channelList.find(c => c.name === deviceName);
    if (channel) {
      copyingChannelId.value = channel.id;
      copyingDeviceName.value = channel.name;
      copyingDeviceIp.value = channel.ip || '0.0.0.0';
      copyingDevicePort.value = channel.port || 502;
      copyingPointCount.value = 0;
      copyDeviceDialogVisible.value = true;
    }
  } catch (error) {
    console.error('获取设备信息失败:', error);
  }
};

const handleCopyDeviceSuccess = async () => {
  await fetchDeviceGroupTree();
};

const handleDeviceAdded = async (deviceName: string, isEdit?: boolean, oldName?: string) => {
  if (isEdit && oldName && oldName !== deviceName) menuRouter.removeRoute(oldName);
  menuRouter.addRoute({
    path: `/device/${deviceName}`,
    name: deviceName,
    component: () => import("@/views/Device.vue")
  });
  await fetchDeviceGroupTree();

  // 自动展开新设备所在的分组
  let found = false;
  // 1. 检查分组设备
  const expandGroup = (nodes: TreeNode[]) => {
    for (const node of nodes) {
      if (node.isGroup && node.children) {
        // 检查子节点是否由新设备
        const hasDevice = node.children.some((child: TreeNode) => !child.isGroup && child.name === deviceName);
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
    const isUngrouped = ungroupedDevices.value.some(d => d.name === deviceName);
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

  const treeNode = document.querySelector('.el-tree-node.is-current');
  const ungroupedNode = document.querySelector('.ungrouped-item.is-active');

  const target = treeNode || ungroupedNode || document.querySelector('.is-current');

  if (target) {
    target.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
};

const handleGroupChanged = () => fetchDeviceGroupTree();
const toggleUngrouped = () => { ungroupedExpanded.value = !ungroupedExpanded.value; };

onMounted(() => {
  fetchDeviceGroupTree();
  const collapsed = localStorage.getItem("isCollapse");
  if (collapsed) isCollapse.value = collapsed === "true";
});

// 监听路由同步
watch(() => router.currentRoute.value.params.deviceName, (name) => {
  if (name) {
    const nameStr = name as string;
    currentDeviceName.value = nameStr;
    currentNodeKey.value = `device-${nameStr}`;
  }
}, { immediate: true });

// 监听侧边栏刷新触发（如 IEC61850 客户端连接成功）
watch(refreshCounter, () => {
  fetchDeviceGroupTree();
});
</script>

<style lang="scss" scoped>
/* 全局侧边栏基础样式 - 通过主题变量驱动 */
.sidebar {
  width: auto !important;
  min-width: var(--sidebar-width);
  height: 100vh;
  background: var(--sb-bg-main);
  border-right: 1px solid var(--sb-border);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
  box-shadow: var(--sb-shadow);

  &.sidebar-collapsed {
    width: var(--sidebar-collapsed-width) !important;
    min-width: var(--sidebar-collapsed-width);

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
  --sb-bg-main: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
  --sb-logo-bg: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  --sb-logo-shadow: rgba(37, 99, 235, 0.3);
  --sb-text-primary: #f8fafc;
  --sb-text-secondary: #94a3b8;
  --sb-btn-primary-bg: rgba(59, 130, 246, 0.2);
  --sb-btn-primary-hover: #3b82f6;
  --sb-item-hover: rgba(255, 255, 255, 0.03);
  --sb-item-active: rgba(59, 130, 246, 0.15);
  --sb-border: rgba(255, 255, 255, 0.05);
  --sb-shadow: 10px 0 30px rgba(0, 0, 0, 0.15);
  --sb-icon-color: #94a3b8;
  --sb-btn-text: #fff;
  --sb-scrollbar: rgba(255, 255, 255, 0.1);
}

/* small 断点下侧边栏 overlay 弹出模式 */
.sidebar-overlay-mode {
  position: fixed;
  top: 0;
  left: 0;
  height: 100vh;
  width: 230px !important;
  min-width: 230px !important;
  z-index: 999;
  box-shadow: 4px 0 24px rgba(0, 0, 0, 0.2);
}
</style>
