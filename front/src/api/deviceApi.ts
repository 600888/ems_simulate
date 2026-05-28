/**
 * 设备管理 API
 */

import { instance, requestApi } from './http';
import { DEVICE_API } from '@/constants';

// ===== 类型导出（供外部使用） =====

export interface MessageRecord {
  timestamp: number;
  formatted_time: string;
  direction: string;
  hex_data: string;
  raw_hex: string;
  description: string;
  length: number;
}

export interface AvgTimeStats {
  tx_count: number;
  rx_count: number;
  total_count: number;
  pair_count: number;
  avg_latency_ms: number;
}

// ===== 设备基础操作 =====

export async function getDeviceList(): Promise<Array<string>> {
  try {
    const data = await requestApi(DEVICE_API.LIST, 'post', null);
    return data;
  } catch (error) {
    console.error('Error fetching device list:', error);
    throw error;
  }
}

export async function getDeviceInfo(deviceName: string): Promise<Map<string, any>> {
  try {
    const data = await requestApi(DEVICE_API.INFO, 'post', { device_name: deviceName });
    return new Map<string, any>(Object.entries(data));
  } catch (error) {
    console.error('Error fetching device info:', error);
    throw error;
  }
}

export async function startSimulation(deviceName: string, simulateMethod: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.START_SIMULATION, 'post', {
      device_name: deviceName,
      simulate_method: simulateMethod,
    });
    return data;
  } catch (error) {
    console.error('Error start simulation:', error);
    throw error;
  }
}

export async function stopSimulation(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.STOP_SIMULATION, 'post', {
      device_name: deviceName,
    });
    return data;
  } catch (error) {
    console.error('Error stop simulation:', error);
    throw error;
  }
}

export async function startDevice(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.START, 'post', { device_name: deviceName });
    return data;
  } catch (error) {
    console.error('Error starting device:', error);
    throw error;
  }
}

export async function stopDevice(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.STOP, 'post', { device_name: deviceName });
    return data;
  } catch (error) {
    console.error('Error stopping device:', error);
    throw error;
  }
}

// ===== 从机管理 =====

export async function getSlaveIdList(deviceName: string): Promise<Array<number>> {
  try {
    const data = await requestApi(DEVICE_API.SLAVE_ID_LIST, 'post', { device_name: deviceName });
    return data;
  } catch (error) {
    console.error('Error get slave id list:', error);
    throw error;
  }
}

export async function getDeviceTable(
  deviceName: string, slaveId: number, pointName: string | null, pageIndex: number,
  pageSize: number, pointTypes: number[], orderBy: string | null = null, orderDirection: string | null = null,
): Promise<Map<string, any>> {
  try {
    const data = await requestApi(DEVICE_API.TABLE, 'post', {
      device_name: deviceName,
      slave_id: slaveId,
      point_name: pointName,
      page_index: pageIndex,
      page_size: pageSize,
      point_types: pointTypes,
      order_by: orderBy,
      order_direction: orderDirection,
    });
    return new Map<string, any>(Object.entries(data));
  } catch (error) {
    console.error('Error get device table:', error);
    throw error;
  }
}

// ===== 自动读取控制 =====

export async function getAutoReadStatus(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.AUTO_READ_STATUS, 'post', { device_name: deviceName });
    return data;
  } catch (error) {
    console.error('Error getting auto read status:', error);
    return false;
  }
}

export async function startAutoRead(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.START_AUTO_READ, 'post', { device_name: deviceName });
    return data;
  } catch (error) {
    console.error('Error starting auto read:', error);
    throw error;
  }
}

export async function stopAutoRead(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.STOP_AUTO_READ, 'post', { device_name: deviceName });
    return data;
  } catch (error) {
    console.error('Error stopping auto read:', error);
    throw error;
  }
}

export async function manualRead(deviceName: string, interval: number = 0): Promise<any> {
  try {
    const data = await requestApi(DEVICE_API.MANUAL_READ, 'post', {
      device_name: deviceName,
      interval: interval,
    });
    return data;
  } catch (error) {
    console.error('Error performing manual read:', error);
    throw error;
  }
}

export async function getCurrentTable(deviceName: string, slaveId: number, pointName: string = ''): Promise<Map<string, any>> {
  try {
    const data = await requestApi(DEVICE_API.CURRENT_TABLE, 'post', {
      device_name: deviceName,
      slave_id: slaveId,
      point_name: pointName,
    });
    return new Map<string, any>(Object.entries(data));
  } catch (error) {
    console.error('Error getting current table:', error);
    throw error;
  }
}

// ===== 报文捕获 =====

export async function getMessages(deviceName: string, limit: number = 100): Promise<MessageRecord[]> {
  try {
    const data = await requestApi(DEVICE_API.MESSAGES, 'post', {
      device_name: deviceName,
      limit: limit,
    });
    return data?.messages ?? [];
  } catch (error) {
    console.error('Error getting messages:', error);
    return [];
  }
}

export async function clearMessages(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.CLEAR_MESSAGES, 'post', { device_name: deviceName });
    return data;
  } catch (error) {
    console.error('Error clearing messages:', error);
    throw error;
  }
}

export async function getAvgTime(deviceName: string): Promise<AvgTimeStats | null> {
  try {
    const data = await requestApi(DEVICE_API.AVG_TIME, 'post', { device_name: deviceName });
    return data;
  } catch (error) {
    console.error('Error getting avg time:', error);
    return null;
  }
}

// ===== IEC61850 连接进度 =====

export interface IEC61850ConnectProgress {
  phase: 'idle' | 'connecting' | 'discovering' | 'done' | 'failed';
  progress: number;
  connecting: boolean;
}

export async function getIEC61850ConnectProgress(deviceName: string): Promise<IEC61850ConnectProgress | null> {
  try {
    const data = await requestApi(DEVICE_API.IEC61850_CONNECT_PROGRESS, 'post', { device_name: deviceName });
    return data;
  } catch (error) {
    console.error('Error getting IEC61850 connect progress:', error);
    return null;
  }
}

// ===== IEC 61850 模型导出 =====

export type ExportModelType = 'icd' | 'json' | 'xml' | 'csv' | 'tree';

export async function exportModel(deviceName: string, exportType: ExportModelType, iedName: string = ''): Promise<void> {
  const extMap: Record<ExportModelType, string> = {
    icd: '.icd',
    json: '.json',
    xml: '.xml',
    csv: '.csv',
    tree: '.txt',
  };
  const mimeMap: Record<ExportModelType, string> = {
    icd: 'application/xml',
    json: 'application/json',
    xml: 'application/xml',
    csv: 'text/csv',
    tree: 'text/plain',
  };
  const defaultFilename = `${deviceName}_model${extMap[exportType]}`;

  // 弹出文件保存对话框，让用户选择保存位置
  const fileHandle = await (window as any).showSaveFilePicker({
    suggestedName: defaultFilename,
    types: [{
      description: `${exportType.toUpperCase()} 文件`,
      accept: { [mimeMap[exportType]]: [extMap[exportType]] },
    }],
  });

  // 请求后端获取文件内容
  const baseURL = import.meta.env.VUE_APP_API_BASE || '/';
  const response = await fetch(`${baseURL}${DEVICE_API.EXPORT_MODEL}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      device_name: deviceName,
      export_type: exportType,
      ied_name: iedName,
    }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const errorMsg = errorData?.message || `导出失败 (HTTP ${response.status})`;
    throw new Error(errorMsg);
  }

  // 将响应内容写入用户选择的文件
  const blob = await response.blob();
  const writable = await fileHandle.createWritable();
  await writable.write(blob);
  await writable.close();
}

// ===== 动态测点/从机管理 =====

export async function addSlave(deviceName: string, slaveId: number): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.ADD_SLAVE, 'post', {
      device_name: deviceName,
      slave_id: slaveId,
    });
    return data;
  } catch (error) {
    console.error('Error adding slave:', error);
    throw error;
  }
}

export async function deleteSlave(deviceName: string, slaveId: number): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.DELETE_SLAVE, 'post', {
      device_name: deviceName,
      slave_id: slaveId,
    });
    return data;
  } catch (error) {
    console.error('Error deleting slave:', error);
    throw error;
  }
}

export async function editSlave(deviceName: string, oldSlaveId: number, newSlaveId: number): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.EDIT_SLAVE, 'post', {
      device_name: deviceName,
      old_slave_id: oldSlaveId,
      new_slave_id: newSlaveId,
    });
    return data;
  } catch (error) {
    console.error('Error editing slave:', error);
    throw error;
  }
}
