/**
 * IEC61850 设备树结构 composable
 * 从 SideBar.vue 中提取的 IEC61850 树节点构建与标记逻辑
 */

import { ref } from 'vue';
import { getChannelList, getIEC61850Structure } from '@/api/channelApi';
import { IEC61850_CATEGORIES } from '@/constants/protocol';
import type { DeviceInfo } from '@/api/deviceGroupApi';

export interface TreeNode {
  nodeKey: string;
  label: string;
  isGroup: boolean;
  id: number;
  name: string;
  groupId?: number;
  children?: TreeNode[];
  isIec61850?: boolean;
  isIec61850Child?: boolean;
  iec61850ChannelId?: number;
  iec61850Children?: TreeNode[];
  deviceName?: string;
  type?: string;
  value?: string;
  iec61850Level?: 'category' | 'ld' | 'ln';
  linkTo?: string;  // 导航链接 (如 GOOSE 节点导航到 /goose)
}

/**
 * 根据 IEC61850 结构数据构建树节点
 */
export function buildIEC61850Children(structure: any, deviceName: string, keyPrefix: string, channelId?: number): TreeNode[] {
  const children: TreeNode[] = [];
  IEC61850_CATEGORIES.forEach((cat) => {
    const items = structure[cat.key] || [];
    // 为 Reports/GOOSE 构造带 channel_id 的导航链接
    const makeLinkTo = (basePath: string) => {
      return channelId ? `${basePath}?channel_id=${channelId}` : basePath;
    };
    if (items.length > 0) {
      let categoryChildren: TreeNode[];

      if (cat.key === 'Data Model') {
        // Data Model 返回层级结构: [{name: "LD0", children: ["LLN0", "MMXU1"]}, ...]
        categoryChildren = items.map((ldItem: any, ldIndex: number) => {
          const ldName = typeof ldItem === 'string' ? ldItem : ldItem.name;
          const lnList = typeof ldItem === 'object' && ldItem.children ? ldItem.children : [];
          const lnChildren: TreeNode[] = lnList.map((ln: string, lnIndex: number) => ({
            nodeKey: `${keyPrefix}-${deviceName}-${cat.key}-${ldIndex}-${lnIndex}`,
            label: ln,
            isGroup: false,
            id: 0,
            isIec61850Child: true,
            iec61850Level: 'ln' as const,
            name: ln,
            deviceName: deviceName,
            type: cat.label,
            value: `${ldName}/${ln}`,
          }));
          return {
            nodeKey: `${keyPrefix}-${deviceName}-${cat.key}-${ldIndex}`,
            label: ldName,
            isGroup: lnChildren.length > 0,
            id: 0,
            isIec61850Child: true,
            iec61850Level: 'ld' as const,
            name: ldName,
            deviceName: deviceName,
            type: cat.label,
            value: ldName,
            children: lnChildren.length > 0 ? lnChildren : undefined,
          };
        });
      } else if (cat.key === 'DataSets') {
        // DataSets 返回层级结构: [{name: "LD0", children: [{name: "LLN0", datasets: [...]}]}]
        categoryChildren = items.map((ldItem: any, ldIndex: number) => {
          const ldName = typeof ldItem === 'string' ? ldItem : ldItem.name;
          const lnList = typeof ldItem === 'object' && ldItem.children ? ldItem.children : [];
          const lnChildren: TreeNode[] = lnList.map((lnItem: any, lnIndex: number) => {
            const lnName = typeof lnItem === 'string' ? lnItem : lnItem.name;
            const dsList = typeof lnItem === 'object' && lnItem.datasets ? lnItem.datasets : [];
            const dsChildren: TreeNode[] = dsList.map((ds: any, dsIndex: number) => ({
              nodeKey: `${keyPrefix}-${deviceName}-${cat.key}-${ldIndex}-${lnIndex}-${dsIndex}`,
              label: `${ds.name} (${ds.member_count || 0} members)`,
              isGroup: false,
              id: 0,
              isIec61850Child: true,
              iec61850Level: 'ln' as const,
              name: ds.name || ds.ref || '',
              deviceName: deviceName,
              type: cat.label,
              value: ds.ref || ds.name || '',
            }));
            return {
              nodeKey: `${keyPrefix}-${deviceName}-${cat.key}-${ldIndex}-${lnIndex}`,
              label: lnName,
              isGroup: dsChildren.length > 0,
              id: 0,
              isIec61850Child: true,
              iec61850Level: 'ln' as const,
              name: lnName,
              deviceName: deviceName,
              type: cat.label,
              value: `${ldName}/${lnName}`,
              children: dsChildren.length > 0 ? dsChildren : undefined,
            };
          });
          return {
            nodeKey: `${keyPrefix}-${deviceName}-${cat.key}-${ldIndex}`,
            label: ldName,
            isGroup: lnChildren.length > 0,
            id: 0,
            isIec61850Child: true,
            iec61850Level: 'ld' as const,
            name: ldName,
            deviceName: deviceName,
            type: cat.label,
            value: ldName,
            children: lnChildren.length > 0 ? lnChildren : undefined,
          };
        });
      } else if (cat.key === 'GOOSE') {
        // GOOSE 分类: 整个分类和条目点击都导航到 GOOSE 管理页面
        categoryChildren = items.map((item: string, itemIndex: number) => ({
          nodeKey: `${keyPrefix}-${deviceName}-${cat.key}-${itemIndex}`,
          label: item,
          isGroup: false,
          id: 0,
          isIec61850Child: true,
          iec61850Level: 'ld' as const,
          name: item,
          deviceName: deviceName,
          type: cat.label,
          linkTo: makeLinkTo('/goose'),
        }));
      } else if (cat.key === 'Reports') {
        // Reports 分类: 导航到 Reports 管理页面
        categoryChildren = items.map((item: string, itemIndex: number) => ({
          nodeKey: `${keyPrefix}-${deviceName}-${cat.key}-${itemIndex}`,
          label: item,
          isGroup: false,
          id: 0,
          isIec61850Child: true,
          iec61850Level: 'ld' as const,
          name: item,
          deviceName: deviceName,
          type: cat.label,
          linkTo: makeLinkTo('/reports'),
        }));
      } else {
        // 其他分类: 仍然为扁平列表
        categoryChildren = items.map((item: string, itemIndex: number) => ({
          nodeKey: `${keyPrefix}-${deviceName}-${cat.key}-${itemIndex}`,
          label: item,
          isGroup: false,
          id: 0,
          isIec61850Child: true,
          iec61850Level: 'ld' as const,
          name: item,
          deviceName: deviceName,
          type: cat.label,
        }));
      }

      children.push({
        nodeKey: `${keyPrefix}-${deviceName}-${cat.key}`,
        label: cat.label,
        isGroup: true,
        id: 0,
        isIec61850Child: true,
        iec61850Level: 'category' as const,
        name: cat.label,
        deviceName: deviceName,
        type: cat.label,
        linkTo: cat.key === 'GOOSE' ? makeLinkTo('/goose') : cat.key === 'Reports' ? makeLinkTo('/reports') : undefined,
        children: categoryChildren,
      });
    } else {
      children.push({
        nodeKey: `${keyPrefix}-${deviceName}-${cat.key}`,
        label: cat.label,
        isGroup: false,
        id: 0,
        isIec61850Child: true,
        iec61850Level: 'category' as const,
        name: cat.label,
        deviceName: deviceName,
        type: cat.label,
        linkTo: cat.key === 'GOOSE' ? makeLinkTo('/goose') : cat.key === 'Reports' ? makeLinkTo('/reports') : undefined,
      });
    }
  });
  return children;
}

/**
 * 构建空的 IEC61850 回退节点（获取结构失败时使用）
 */
export function buildFallbackIEC61850Children(deviceName: string, keyPrefix: string): TreeNode[] {
  return IEC61850_CATEGORIES.map(cat => ({
    nodeKey: `${keyPrefix}-${deviceName}-${cat.key}`,
    label: cat.label,
    isGroup: false,
    id: 0,
    isIec61850Child: true,
    name: cat.label,
    deviceName: deviceName,
    type: cat.label,
  }));
}

/**
 * IEC61850 树节点管理 composable
 */
export function useIec61850Tree() {
  const iec61850UngroupedMap = ref<Record<string, TreeNode[]>>({});

  /**
   * 获取分组内设备的 IEC61850 结构并更新树
   */
  let _structureLoadedCallback: (() => void) | null = null;

  // 请求去重：缓存正在进行的 iec61850-structure 请求，防止同一 channel 重复请求
  const _pendingStructureRequests = new Map<number, Promise<any>>();
  // 结果短缓存：避免短时间内多次 loadDeviceGroups 对同一 channel 重复请求后端
  const _structureCache = new Map<number, { data: any; ts: number }>();
  const _STRUCTURE_CACHE_TTL = 3000;

  const setStructureLoadedCallback = (cb: () => void) => {
    _structureLoadedCallback = cb;
  };

  /**
   * 获取 IEC61850 结构（带去重 + 短缓存），同一 channelId 并发或短时间内只发一次请求
   */
  const _fetchStructureDeduped = async (channelId: number): Promise<any> => {
    // 命中短缓存直接返回
    const cached = _structureCache.get(channelId);
    if (cached && Date.now() - cached.ts < _STRUCTURE_CACHE_TTL) {
      return cached.data;
    }
    // 如果已有正在进行的请求，复用该 Promise
    const pending = _pendingStructureRequests.get(channelId);
    if (pending) {
      return pending;
    }
    // 发起新请求并缓存
    const promise = getIEC61850Structure(channelId)
      .then((data) => {
        _structureCache.set(channelId, { data, ts: Date.now() });
        return data;
      })
      .finally(() => {
        _pendingStructureRequests.delete(channelId);
      });
    _pendingStructureRequests.set(channelId, promise);
    return promise;
  };

  const fetchIEC61850Structure = async (channelId: number, deviceName: string, treeData: Ref<TreeNode[]>) => {
    const updateTreeNode = (nodes: TreeNode[], iec61850Children: TreeNode[]): TreeNode[] => {
      return nodes.map(node => {
        if (node.name === deviceName && node.isIec61850) {
          return { ...node, children: iec61850Children };
        }
        if (node.children && node.children.length > 0) {
          return { ...node, children: updateTreeNode(node.children, iec61850Children) };
        }
        return node;
      });
    };

    try {
      const structure = await _fetchStructureDeduped(channelId);
      const iec61850Children = buildIEC61850Children(structure, deviceName, 'device', channelId);

      try {
        treeData.value = updateTreeNode(treeData.value, iec61850Children);
      } catch (mapErr: any) {
        console.error(`[TreeUpdate ERROR] updateTreeNode failed:`, mapErr, `deviceName=${deviceName}`);
        treeData.value = updateTreeNode(treeData.value, iec61850Children);
      }

      _structureLoadedCallback?.();
    } catch (error) {
      console.error(`[TreeUpdate ERROR] fetchIEC61850Structure outer catch:`, error);
      const fallback = buildFallbackIEC61850Children(deviceName, 'device');
      treeData.value = updateTreeNode(treeData.value, fallback);
      _structureLoadedCallback?.();
    }
  };

  /**
   * 标记分组内的 IEC61850 设备并异步获取结构
   */
  const markIEC61850Devices = async (nodes: TreeNode[], treeData: Ref<TreeNode[]>) => {
    try {
      const channels = await getChannelList();
      for (const node of nodes) {
        if (!node.isGroup && node.name) {
          const channel = channels.find(c => c.name === node.name);
          if (channel && channel.protocol_type === 4) {
            node.isIec61850 = true;
            node.iec61850ChannelId = channel.id;
            // 预设空 children 数组，让 el-tree 初始时就知道该节点"可展开"显示箭头
            if (!node.children) {
              node.children = [];
            }
            fetchIEC61850Structure(channel.id, node.name, treeData);
            // IEC61850 设备节点已处理完毕，跳过对其 children 的递归
            // （设备节点没有有意义的子节点，空 children 数组无需遍历）
            continue;
          }
        }
        if (node.children) {
          await markIEC61850Devices(node.children, treeData);
        }
      }
    } catch (error) {
      console.error('标记 IEC61850 设备失败:', error);
    }
  };

  /**
   * 标记并获取未分组设备的 IEC61850 结构
   */
  const markUngroupedIEC61850Devices = async (devices: DeviceInfo[]) => {
    try {
      const channels = await getChannelList();
      for (const device of devices) {
        const channel = channels.find(c => c.name === device.name);
        if (channel && channel.protocol_type === 4) {
          (async () => {
            try {
              const structure = await _fetchStructureDeduped(channel.id);
              iec61850UngroupedMap.value = {
                ...iec61850UngroupedMap.value,
                [device.name]: buildIEC61850Children(structure, device.name, 'ungrouped', channel.id),
              };
            } catch (error) {
              console.warn(`获取未分组 IEC61850 结构失败 (设备: ${device.name}):`, error);
              iec61850UngroupedMap.value = {
                ...iec61850UngroupedMap.value,
                [device.name]: buildFallbackIEC61850Children(device.name, 'ungrouped'),
              };
            }
          })();
        }
      }
    } catch (error) {
      console.error('标记未分组 IEC61850 设备失败:', error);
    }
  };

  return {
    iec61850UngroupedMap,
    fetchIEC61850Structure,
    markIEC61850Devices,
    markUngroupedIEC61850Devices,
    setStructureLoadedCallback,
  };
}

import type { Ref } from 'vue';
