/**
 * 测点管理 API
 */

import { requestApi } from "./http";
import { POINT_API } from "@/constants";
import type { PointLimit } from "@/types/point";

// ===== 类型定义 =====

export interface PointCreateData {
  frame_type: number;
  code: string;
  name: string;
  rtu_addr: number;
  reg_addr: string;
  func_code: number;
  decode_code: string;
  bit?: number | null;
  mul_coe: number;
  add_coe: number;
  iec_type_id?: string | null;
  iec_quality?: number;
}

export interface ChangeRecord {
  source: string;
  source_label: string;
  old_value: any;
  new_value: any;
  old_real_value: any;
  new_real_value: any;
  timestamp: number;
  time: string;
  detail: string;
  client_info?: string;
}

export interface PointChangeHistoryResponse {
  point_code: string;
  tracking_enabled: boolean;
  maxlen: number;
  history: ChangeRecord[];
  count: number;
}

// ===== API 函数 =====

export async function editPointData(
  deviceName: string,
  pointCode: string,
  pointValue: number,
  slaveId?: number,
): Promise<boolean> {
  return await requestApi(POINT_API.EDIT_DATA, "post", {
    device_name: deviceName,
    point_code: pointCode,
    point_value: pointValue,
    slave_id: slaveId,
  });
}

export async function editPointLimit(
  deviceName: string,
  pointCode: string,
  minValueLimit: number,
  maxValueLimit: number,
): Promise<boolean> {
  try {
    return await requestApi(POINT_API.EDIT_LIMIT, "post", {
      device_name: deviceName,
      point_code: pointCode,
      min_value_limit: minValueLimit,
      max_value_limit: maxValueLimit,
    });
  } catch (error) {
    console.error("Error editing point limit:", error);
    throw error;
  }
}

export async function getPointLimit(
  deviceName: string,
  pointCode: string,
): Promise<PointLimit> {
  const pointLimit: PointLimit = { minValueLimit: 0, maxValueLimit: 0 };
  try {
    const data = await requestApi(POINT_API.GET_LIMIT, "post", {
      device_name: deviceName,
      point_code: pointCode,
    });
    pointLimit.minValueLimit = data.min_value_limit;
    pointLimit.maxValueLimit = data.max_value_limit;
    return pointLimit;
  } catch (error) {
    console.error("Error getting point limit:", error);
    return pointLimit;
  }
}

export async function getPointInfo(
  deviceName: string,
  pointCode: string,
): Promise<any> {
  try {
    return await requestApi(POINT_API.INFO, "post", {
      device_name: deviceName,
      point_code: pointCode,
    });
  } catch (error) {
    console.error("Error getting point info:", error);
    throw error;
  }
}

export async function setSinglePointSimulateMethod(
  deviceName: string,
  pointCode: string,
  simulateMethod: string,
  fixedValue?: number,
): Promise<boolean> {
  try {
    return await requestApi(POINT_API.SET_SIMULATE_METHOD, "post", {
      device_name: deviceName,
      point_code: pointCode,
      simulate_method: simulateMethod,
      fixed_value: fixedValue,
    });
  } catch (error) {
    console.error("Error setting single point simulate method:", error);
    throw error;
  }
}

export async function setSinglePointStep(
  deviceName: string,
  pointCode: string,
  step: number,
): Promise<boolean> {
  try {
    return await requestApi(POINT_API.SET_SIMULATE_STEP, "post", {
      device_name: deviceName,
      point_code: pointCode,
      step: step,
    });
  } catch (error) {
    console.error("Error setting single point step:", error);
    throw error;
  }
}

/** 批量获取测点当前值（轻量，供模拟数据自动刷新） */
export async function batchPointValues(
  deviceName: string,
  pointCodes: string[],
): Promise<Record<string, number | string | null>> {
  try {
    return await requestApi(POINT_API.BATCH_VALUES, "post", {
      device_name: deviceName,
      point_codes: pointCodes,
    });
  } catch (error) {
    console.error("Error fetching batch point values:", error);
    throw error;
  }
}

export async function setPointSimulationRange(
  deviceName: string,
  pointCode: string,
  minValue: number,
  maxValue: number,
): Promise<boolean> {
  try {
    return await requestApi(POINT_API.SET_SIMULATION_RANGE, "post", {
      device_name: deviceName,
      point_code: pointCode,
      min_value: minValue,
      max_value: maxValue,
    });
  } catch (error) {
    console.error("Error setting point simulation range:", error);
    throw error;
  }
}

export async function editPointMetadata(
  deviceName: string,
  pointCode: string,
  metadata: any,
): Promise<boolean> {
  try {
    return await requestApi(POINT_API.EDIT_METADATA, "post", {
      device_name: deviceName,
      point_code: pointCode,
      metadata: metadata,
    });
  } catch (error) {
    console.error("Error editing point metadata:", error);
    throw error;
  }
}

export async function editIec104Metadata(
  deviceName: string,
  pointCode: string,
  iec104Data: { iec_type_id: string | null; iec_quality: number },
): Promise<boolean> {
  try {
    return await requestApi(POINT_API.EDIT_IEC104_METADATA, "post", {
      device_name: deviceName,
      point_code: pointCode,
      ...iec104Data,
    });
  } catch (error) {
    console.error("Error editing IEC104 metadata:", error);
    throw error;
  }
}

export async function readSinglePoint(
  deviceName: string,
  pointCode: string,
  slaveId?: number,
  activeRead: boolean = false,
): Promise<number | string | null> {
  try {
    const data = await requestApi(POINT_API.READ_SINGLE, "post", {
      device_name: deviceName,
      point_code: pointCode,
      ...(slaveId === undefined ? {} : { slave_id: slaveId }),
      active_read: activeRead,
    });
    return data?.value ?? null;
  } catch (error) {
    console.error("Error reading single point:", error);
    return null;
  }
}

export async function addPoint(
  deviceName: string,
  pointData: PointCreateData,
): Promise<boolean> {
  try {
    return await requestApi(POINT_API.ADD, "post", {
      device_name: deviceName,
      ...pointData,
    });
  } catch (error) {
    console.error("Error adding point:", error);
    throw error;
  }
}

export async function addPointsBatch(
  deviceName: string,
  frameType: number,
  points: PointCreateData[],
): Promise<boolean> {
  try {
    return await requestApi(POINT_API.ADD_BATCH, "post", {
      device_name: deviceName,
      frame_type: frameType,
      points: points,
    });
  } catch (error) {
    console.error("Error adding points batch:", error);
    throw error;
  }
}

export async function deletePoint(
  deviceName: string,
  pointCode: string,
): Promise<boolean> {
  try {
    return await requestApi(POINT_API.DELETE, "post", {
      device_name: deviceName,
      point_code: pointCode,
    });
  } catch (error) {
    console.error("Error deleting point:", error);
    throw error;
  }
}

// ===== 变更追溯 =====

export async function getPointChangeHistory(
  deviceName: string,
  pointCode: string,
  slaveId?: number,
): Promise<PointChangeHistoryResponse | null> {
  try {
    return await requestApi(POINT_API.CHANGE_HISTORY, "post", {
      device_name: deviceName,
      point_code: pointCode,
      slave_id: slaveId,
    });
  } catch (error) {
    console.error("Error getting point change history:", error);
    return null;
  }
}

export async function setChangeTrackingConfig(
  deviceName: string,
  pointCode: string,
  enabled: boolean,
  maxlen?: number,
  slaveId?: number,
): Promise<boolean> {
  try {
    return await requestApi(POINT_API.SET_CHANGE_TRACKING, "post", {
      device_name: deviceName,
      point_code: pointCode,
      enabled: enabled,
      maxlen: maxlen,
      slave_id: slaveId,
    });
  } catch (error) {
    console.error("Error setting change tracking config:", error);
    throw error;
  }
}

export async function clearPointChangeHistory(
  deviceName: string,
  pointCode: string,
  slaveId?: number,
): Promise<boolean> {
  try {
    return await requestApi(POINT_API.CLEAR_CHANGE_HISTORY, "post", {
      device_name: deviceName,
      point_code: pointCode,
      slave_id: slaveId,
    });
  } catch (error) {
    console.error("Error clearing point change history:", error);
    return false;
  }
}

export async function clearPoints(
  deviceName: string,
  slaveId: number,
): Promise<number> {
  try {
    return await requestApi(POINT_API.CLEAR_BY_SLAVE, "post", {
      device_name: deviceName,
      slave_id: slaveId,
    });
  } catch (error) {
    console.error("Error clearing points:", error);
    throw error;
  }
}

export async function resetPointData(deviceName: string): Promise<boolean> {
  try {
    return await requestApi(POINT_API.RESET_DATA, "post", {
      device_name: deviceName,
    });
  } catch (error) {
    console.error("Error resetting point data:", error);
    throw error;
  }
}
