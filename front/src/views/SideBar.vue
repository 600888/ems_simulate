<template>
  <el-aside class="sidebar" :class="[`sidebar-theme-${currentTheme}`, { 'sidebar-collapsed': isCollapse }]">
    <el-scrollbar>
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
        :tree-data="treeData"
        :tree-props="treeProps"
        :expanded-keys="expandedKeys"
        :current-node-key="currentNodeKey"
        :is-collapse="isCollapse"
        @node-click="handleNodeClick"
        @group-command="handleGroupCommand"
        @edit-device="handleEditDevice"
        @delete-device="handleDeleteDevice"
      />
      
      <!-- 4. 未分组设备 -->
      <SideNavUngrouped
        :ungrouped-devices="ungroupedDevices"
        :expanded="ungroupedExpanded"
        :current-device-name="currentDeviceName"
        :is-collapse="isCollapse"
        @toggle="toggleUngrouped"
        @device-click="handleDeviceClick"
        @edit-device="handleEditDeviceByName"
        @delete-device="handleDeleteDeviceByName"
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
    @success="handleGroupChanged"
    @close="editingGroupId = null"
  />
</template>

<script lang="ts" setup>
import { onMounted, ref, computed, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import type { ElTree } from "element-plus";

import SideNavHeader from "@/components/layout/SideNavHeader.vue";
import SideNavActions from "@/components/layout/SideNavActions.vue";
import SideNavTree from "@/components/layout/SideNavTree.vue";
import SideNavUngrouped from "@/components/layout/SideNavUngrouped.vue";
import AddDeviceDialog from "@/components/device/AddDeviceDialog.vue";
import AddDeviceGroupDialog from "@/components/device/AddDeviceGroupDialog.vue";

import { currentTheme } from "@/utils/theme";
import { isCollapse } from "@/components/header/isCollapse";
import menuRouter from "@/router/index";
import { deleteChannel, getChannelList } from "@/api/channelApi";
import { 
  getDeviceGroupTree, 
  deleteDeviceGroup, 
  batchDeviceOperation,
  type DeviceGroupTreeNode,
  type DeviceInfo
} from "@/api/deviceGroupApi";

// 类型定义
interface TreeNode {
  nodeKey: string;
  label: string;
  isGroup: boolean;
  id: number;
  name: string;
  groupId?: number;
  children?: TreeNode[];
}

const router = useRouter();
const treeRef = ref<InstanceType<typeof ElTree>>();

// 状态管理
const addDeviceDialogVisible = ref(false);
const addGroupDialogVisible = ref(false);
const editingChannelId = ref<number | null>(null);
const editingGroupId = ref<number | null>(null);
const parentGroupIdForNewDevice = ref<number | null>(null);

const treeData = ref<TreeNode[]>([]);
const ungroupedDevices = ref<DeviceInfo[]>([]);
const expandedKeys = ref<string[]>([]);
const currentNodeKey = ref<string>('');
const currentDeviceName = ref<string>('');
const ungroupedExpanded = ref(true);

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
        nodeKey: `device-${d.id}`,
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

const fetchDeviceGroupTree = async () => {
  try {
    const response = await getDeviceGroupTree();
    treeData.value = transformToTreeData(response.groups || []);
    ungroupedDevices.value = response.ungrouped || [];
    if (currentDeviceName.value) {
      currentNodeKey.value = `device-${currentDeviceName.value}`;
    }
  } catch (error: any) {
    ElMessage.error('获取设备组失败: ' + error.message);
  }
};

// 交互处理
const handleNodeClick = (data: TreeNode) => {
  if (!data.isGroup) navigateToDevice(data.name);
};

const handleDeviceClick = (device: DeviceInfo) => navigateToDevice(device.name);

const navigateToDevice = (deviceName: string) => {
  currentDeviceName.value = deviceName;
  currentNodeKey.value = `device-${deviceName}`;
  const path = `/device/${deviceName}`;
  localStorage.setItem("activeRoute", path);
  router.push(path);
};

const showAddDeviceDialog = () => {
  editingChannelId.value = null;
  parentGroupIdForNewDevice.value = null;
  addDeviceDialogVisible.value = true;
};

const showAddGroupDialog = (parentId?: number) => {
  editingGroupId.value = null;
  parentGroupIdForNewDevice.value = parentId || null;
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

const handleBatchOperation = async (groupId: number, operation: 'start' | 'stop' | 'reset') => {
  try {
    await batchDeviceOperation(groupId, operation);
    ElMessage.success(`${operation === 'start' ? '启动' : '停止'}成功`);
  } catch (error: any) {
    ElMessage.error('操作失败: ' + error.message);
  }
};

const handleDeleteGroup = async (data: TreeNode) => {
  try {
    await ElMessageBox.confirm(`确定删除组 "${data.name}"？`, '提示', { type: 'warning' });
    await deleteDeviceGroup(data.id, false);
    ElMessage.success('成功');
    await fetchDeviceGroupTree();
  } catch {}
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
  try {
    await ElMessageBox.confirm(`确定删除 "${deviceName}"？`, '提示', { type: 'warning' });
    const channel = (await getChannelList()).find(c => c.name === deviceName);
    if (channel) {
      await deleteChannel(channel.id);
      window.location.reload();
    }
  } catch {}
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
        const hasDevice = node.children.some(child => !child.isGroup && child.name === deviceName);
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

  navigateToDevice(deviceName);
};

const handleGroupChanged = () => fetchDeviceGroupTree();
const toggleUngrouped = () => { ungroupedExpanded.value = !ungroupedExpanded.value; };

onMounted(() => {
  fetchDeviceGroupTree();
  const collapsed = localStorage.getItem("isCollapse");
  if (collapsed) isCollapse.value = collapsed === "true";
});

// 监听路由同步
watch(() => router.currentRoute.value.path, (path) => {
  if (path.startsWith('/device/')) {
    const name = path.split('/').pop() || '';
    currentDeviceName.value = name;
    currentNodeKey.value = `device-${name}`;
  }
}, { immediate: true });
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
    width: 64px !important;
    min-width: 64px;
    
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
        .node-actions {
          display: none !important;
        }
        
        .el-icon {
          margin-right: 0;
        }
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
</style>
