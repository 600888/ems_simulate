/**
 * 设备组管理 API
 */

import { instance, requestApi } from './deviceApi';

// ========== 类型定义 ==========

/** 设备组信息 */
export interface DeviceGroupInfo {
    id: number;
    code: string;
    name: string;
    parent_id: number | null;
    description: string | null;
    status: number;
    enable: boolean;
    created_at: string | null;
    updated_at: string | null;
}

/** 设备信息（简化版） */
export interface DeviceInfo {
    id: number;
    code: string;
    name: string;
    device_type: number;
    group_id: number | null;
    enable: boolean;
}

/** 设备组树节点 */
export interface DeviceGroupTreeNode extends DeviceGroupInfo {
    children: DeviceGroupTreeNode[];
    devices: DeviceInfo[];
}

/** 设备组树响应 */
export interface DeviceGroupTreeResponse {
    groups: DeviceGroupTreeNode[];
    ungrouped: DeviceInfo[];
}

/** 创建设备组请求 */
export interface DeviceGroupCreateRequest {
    code: string;
    name: string;
    parent_id?: number | null;
    description?: string | null;
}

/** 更新设备组请求 */
export interface DeviceGroupUpdateRequest {
    name?: string;
    parent_id?: number | null;
    description?: string | null;
    status?: number;
}

/** 批量移动设备请求 */
export interface MoveDevicesRequest {
    device_ids: number[];
    group_id: number | null;
}

/** 批量操作请求 */
export interface BatchOperationRequest {
    group_id: number;
    operation: 'start' | 'stop' | 'reset';
}

// ========== API 函数 ==========

/**
 * 获取设备组树形结构（包含未分组设备）
 */
export async function getDeviceGroupTree(): Promise<DeviceGroupTreeResponse> {
    try {
        const data = await requestApi('/api/device-groups/tree', 'get', null);
        return data;
    } catch (error) {
        console.error('Error fetching device group tree:', error);
        throw error;
    }
}

/**
 * 获取所有设备组（扁平列表）
 */
export async function getAllDeviceGroups(): Promise<DeviceGroupInfo[]> {
    try {
        const data = await requestApi('/api/device-groups/', 'get', null);
        return data;
    } catch (error) {
        console.error('Error fetching device groups:', error);
        throw error;
    }
}

/**
 * 获取顶级设备组
 */
export async function getRootDeviceGroups(): Promise<DeviceGroupInfo[]> {
    try {
        const data = await requestApi('/api/device-groups/root', 'get', null);
        return data;
    } catch (error) {
        console.error('Error fetching root device groups:', error);
        throw error;
    }
}

/**
 * 获取未分组设备
 */
export async function getUngroupedDevices(): Promise<DeviceInfo[]> {
    try {
        const data = await requestApi('/api/device-groups/ungrouped', 'get', null);
        return data;
    } catch (error) {
        console.error('Error fetching ungrouped devices:', error);
        throw error;
    }
}

/**
 * 获取设备组详情
 */
export async function getDeviceGroup(groupId: number): Promise<DeviceGroupInfo> {
    try {
        const data = await requestApi(`/api/device-groups/${groupId}`, 'get', null);
        return data;
    } catch (error) {
        console.error('Error fetching device group:', error);
        throw error;
    }
}

/**
 * 获取设备组内的设备
 */
export async function getDevicesInGroup(groupId: number): Promise<DeviceInfo[]> {
    try {
        const data = await requestApi(`/api/device-groups/${groupId}/devices`, 'get', null);
        return data;
    } catch (error) {
        console.error('Error fetching devices in group:', error);
        throw error;
    }
}

/**
 * 获取子设备组
 */
export async function getChildrenGroups(groupId: number): Promise<DeviceGroupInfo[]> {
    try {
        const data = await requestApi(`/api/device-groups/${groupId}/children`, 'get', null);
        return data;
    } catch (error) {
        console.error('Error fetching children groups:', error);
        throw error;
    }
}

/**
 * 创建设备组
 */
export async function createDeviceGroup(request: DeviceGroupCreateRequest): Promise<{ group_id: number }> {
    try {
        const data = await requestApi('/api/device-groups/', 'post', request);
        return data;
    } catch (error) {
        console.error('Error creating device group:', error);
        throw error;
    }
}

/**
 * 更新设备组
 */
export async function updateDeviceGroup(groupId: number, request: DeviceGroupUpdateRequest): Promise<boolean> {
    try {
        await requestApi(`/api/device-groups/${groupId}`, 'put', request);
        return true;
    } catch (error) {
        console.error('Error updating device group:', error);
        throw error;
    }
}

/**
 * 删除设备组
 * @param groupId 设备组ID
 * @param cascade 是否级联删除，默认false（将子组和设备移至未分组）
 */
export async function deleteDeviceGroup(groupId: number, cascade: boolean = false): Promise<boolean> {
    try {
        await instance.delete(`/api/device-groups/${groupId}`, {
            params: { cascade }
        });
        return true;
    } catch (error) {
        console.error('Error deleting device group:', error);
        throw error;
    }
}

/**
 * 将设备添加到设备组
 */
export async function addDeviceToGroup(deviceId: number, groupId: number): Promise<boolean> {
    try {
        await requestApi('/api/device-groups/add-device', 'post', {
            device_id: deviceId,
            group_id: groupId
        });
        return true;
    } catch (error) {
        console.error('Error adding device to group:', error);
        throw error;
    }
}

/**
 * 将设备从设备组移除
 */
export async function removeDeviceFromGroup(deviceId: number): Promise<boolean> {
    try {
        await requestApi(`/api/device-groups/remove-device/${deviceId}`, 'post', null);
        return true;
    } catch (error) {
        console.error('Error removing device from group:', error);
        throw error;
    }
}

/**
 * 批量移动设备到设备组
 */
export async function moveDevicesToGroup(request: MoveDevicesRequest): Promise<{ moved_count: number }> {
    try {
        const data = await requestApi('/api/device-groups/move-devices', 'post', request);
        return data;
    } catch (error) {
        console.error('Error moving devices:', error);
        throw error;
    }
}

/**
 * 批量操作设备组内设备
 */
export async function batchDeviceOperation(
    groupId: number,
    operation: 'start' | 'stop' | 'reset'
): Promise<{ success_count: number; fail_count: number }> {
    try {
        const data = await requestApi(`/api/device-groups/${groupId}/batch-operation`, 'post', {
            group_id: groupId,
            operation
        });
        return data;
    } catch (error) {
        console.error('Error batch operating devices:', error);
        throw error;
    }
}

/**
 * 更新设备组状态
 */
export async function updateDeviceGroupStatus(groupId: number, status: number): Promise<boolean> {
    try {
        await instance.put(`/api/device-groups/${groupId}/status`, null, {
            params: { status }
        });
        return true;
    } catch (error) {
        console.error('Error updating device group status:', error);
        throw error;
    }
}
