/**
 * 设备组管理 API
 */

import { instance, requestApi } from "./http";
import { DEVICE_GROUP_API, HTTP_TIMEOUT_LONG } from "@/constants";

// ========== 类型定义 ==========

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

export interface DeviceInfo {
  id: number;
  code: string;
  name: string;
  device_type: number;
  group_id: number | null;
  enable: boolean;
}

export interface DeviceGroupTreeNode extends DeviceGroupInfo {
  children: DeviceGroupTreeNode[];
  devices: DeviceInfo[];
}

export interface DeviceGroupTreeResponse {
  groups: DeviceGroupTreeNode[];
  ungrouped: DeviceInfo[];
}

export interface DeviceGroupCreateRequest {
  code: string;
  name: string;
  parent_id?: number | null;
  description?: string | null;
}

export interface DeviceGroupUpdateRequest {
  name?: string;
  parent_id?: number | null;
  description?: string | null;
  status?: number;
}

export interface MoveDevicesRequest {
  device_ids: number[];
  group_id: number | null;
}

export interface BatchOperationRequest {
  group_id: number;
  operation: "start" | "stop" | "reset";
}

// ========== API 函数 ==========

export async function getDeviceGroupTree(): Promise<DeviceGroupTreeResponse> {
  try {
    return await requestApi(DEVICE_GROUP_API.TREE, "post", null);
  } catch (error) {
    console.error("Error fetching device group tree:", error);
    throw error;
  }
}

export async function getAllDeviceGroups(): Promise<DeviceGroupInfo[]> {
  try {
    return await requestApi(DEVICE_GROUP_API.LIST, "post", null);
  } catch (error) {
    console.error("Error fetching device groups:", error);
    throw error;
  }
}

export async function getRootDeviceGroups(): Promise<DeviceGroupInfo[]> {
  try {
    return await requestApi(DEVICE_GROUP_API.ROOT, "post", null);
  } catch (error) {
    console.error("Error fetching root device groups:", error);
    throw error;
  }
}

export async function getUngroupedDevices(): Promise<DeviceInfo[]> {
  try {
    return await requestApi(DEVICE_GROUP_API.UNGROUPED, "post", null);
  } catch (error) {
    console.error("Error fetching ungrouped devices:", error);
    throw error;
  }
}

export async function getDeviceGroup(
  groupId: number,
): Promise<DeviceGroupInfo> {
  try {
    return await requestApi(DEVICE_GROUP_API.DETAIL, "post", {
      group_id: groupId,
    });
  } catch (error) {
    console.error("Error fetching device group:", error);
    throw error;
  }
}

export async function getDevicesInGroup(
  groupId: number,
): Promise<DeviceInfo[]> {
  try {
    return await requestApi(DEVICE_GROUP_API.DEVICES_IN_GROUP, "post", {
      group_id: groupId,
    });
  } catch (error) {
    console.error("Error fetching devices in group:", error);
    throw error;
  }
}

export async function getChildrenGroups(
  groupId: number,
): Promise<DeviceGroupInfo[]> {
  try {
    return await requestApi(DEVICE_GROUP_API.CHILDREN, "post", {
      group_id: groupId,
    });
  } catch (error) {
    console.error("Error fetching children groups:", error);
    throw error;
  }
}

export async function createDeviceGroup(
  request: DeviceGroupCreateRequest,
): Promise<{ group_id: number }> {
  try {
    return await requestApi(DEVICE_GROUP_API.CREATE, "post", request);
  } catch (error) {
    console.error("Error creating device group:", error);
    throw error;
  }
}

export async function updateDeviceGroup(
  groupId: number,
  request: DeviceGroupUpdateRequest,
): Promise<boolean> {
  try {
    await requestApi(DEVICE_GROUP_API.UPDATE, "post", {
      group_id: groupId,
      ...request,
    });
    return true;
  } catch (error) {
    console.error("Error updating device group:", error);
    throw error;
  }
}

export async function deleteDeviceGroup(
  groupId: number,
  cascade: boolean = false,
): Promise<boolean> {
  try {
    await requestApi(DEVICE_GROUP_API.DELETE, "post", {
      group_id: groupId,
      cascade,
    });
    return true;
  } catch (error) {
    console.error("Error deleting device group:", error);
    throw error;
  }
}

export async function addDeviceToGroup(
  deviceId: number,
  groupId: number,
): Promise<boolean> {
  try {
    await requestApi(DEVICE_GROUP_API.ADD_DEVICE, "post", {
      device_id: deviceId,
      group_id: groupId,
    });
    return true;
  } catch (error) {
    console.error("Error adding device to group:", error);
    throw error;
  }
}

export async function removeDeviceFromGroup(
  deviceId: number,
): Promise<boolean> {
  try {
    await requestApi(DEVICE_GROUP_API.REMOVE_DEVICE, "post", {
      device_id: deviceId,
    });
    return true;
  } catch (error) {
    console.error("Error removing device from group:", error);
    throw error;
  }
}

export async function moveDevicesToGroup(
  request: MoveDevicesRequest,
): Promise<{ moved_count: number }> {
  try {
    return await requestApi(DEVICE_GROUP_API.MOVE_DEVICES, "post", request);
  } catch (error) {
    console.error("Error moving devices:", error);
    throw error;
  }
}

export async function batchDeviceOperation(
  groupId: number,
  operation: "start" | "stop" | "reset",
): Promise<{ success_count: number; fail_count: number }> {
  try {
    return await requestApi(
      DEVICE_GROUP_API.BATCH_OPERATION,
      "post",
      { group_id: groupId, operation },
      HTTP_TIMEOUT_LONG,
    );
  } catch (error) {
    console.error("Error batch operating devices:", error);
    throw error;
  }
}

export async function updateDeviceGroupStatus(
  groupId: number,
  status: number,
): Promise<boolean> {
  try {
    await requestApi(DEVICE_GROUP_API.UPDATE_STATUS, "post", {
      group_id: groupId,
      status,
    });
    return true;
  } catch (error) {
    console.error("Error updating device group status:", error);
    throw error;
  }
}
