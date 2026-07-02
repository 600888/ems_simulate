/**
 * 设备管理 API
 */

import { instance, requestApi } from "./http";
import { DEVICE_API } from "@/constants";

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
    const data = await requestApi(DEVICE_API.LIST, "post", null);
    return data;
  } catch (error) {
    console.error("Error fetching device list:", error);
    throw error;
  }
}

export async function getDeviceInfo(deviceName: string): Promise<Map<string, any>> {
  try {
    const data = await requestApi(DEVICE_API.INFO, "post", { device_name: deviceName });
    return new Map<string, any>(Object.entries(data));
  } catch (error) {
    console.error("Error fetching device info:", error);
    throw error;
  }
}

export async function startSimulation(
  deviceName: string,
  simulateMethod: string
): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.START_SIMULATION, "post", {
      device_name: deviceName,
      simulate_method: simulateMethod,
    });
    return data;
  } catch (error) {
    console.error("Error start simulation:", error);
    throw error;
  }
}

export async function stopSimulation(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.STOP_SIMULATION, "post", {
      device_name: deviceName,
    });
    return data;
  } catch (error) {
    console.error("Error stop simulation:", error);
    throw error;
  }
}

export async function startDevice(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.START, "post", { device_name: deviceName });
    return data;
  } catch (error) {
    console.error("Error starting device:", error);
    throw error;
  }
}

export async function stopDevice(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.STOP, "post", { device_name: deviceName });
    return data;
  } catch (error) {
    console.error("Error stopping device:", error);
    throw error;
  }
}

// ===== 从机管理 =====

export async function getSlaveIdList(deviceName: string): Promise<Array<number>> {
  try {
    const data = await requestApi(DEVICE_API.SLAVE_ID_LIST, "post", {
      device_name: deviceName,
    });
    return data;
  } catch (error) {
    console.error("Error get slave id list:", error);
    throw error;
  }
}

export async function getDeviceTable(
  deviceName: string,
  slaveId: number,
  pointName: string | null,
  pageIndex: number,
  pageSize: number,
  pointTypes: number[],
  orderBy: string | null = null,
  orderDirection: string | null = null
): Promise<Map<string, any>> {
  try {
    const data = await requestApi(DEVICE_API.TABLE, "post", {
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
    console.error("Error get device table:", error);
    throw error;
  }
}

// ===== 自动读取控制 =====

export async function getAutoReadStatus(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.AUTO_READ_STATUS, "post", {
      device_name: deviceName,
    });
    return data;
  } catch (error) {
    console.error("Error getting auto read status:", error);
    return false;
  }
}

export async function startAutoRead(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.START_AUTO_READ, "post", {
      device_name: deviceName,
    });
    return data;
  } catch (error) {
    console.error("Error starting auto read:", error);
    throw error;
  }
}

export async function stopAutoRead(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.STOP_AUTO_READ, "post", {
      device_name: deviceName,
    });
    return data;
  } catch (error) {
    console.error("Error stopping auto read:", error);
    throw error;
  }
}

export async function manualRead(deviceName: string, interval: number = 0): Promise<any> {
  try {
    const data = await requestApi(DEVICE_API.MANUAL_READ, "post", {
      device_name: deviceName,
      interval: interval,
    });
    return data;
  } catch (error) {
    console.error("Error performing manual read:", error);
    throw error;
  }
}

// ===== 报文捕获 =====
export async function getMessages(
  deviceName: string,
  limit: number = 100
): Promise<MessageRecord[]> {
  try {
    const data = await requestApi(DEVICE_API.MESSAGES, "post", {
      device_name: deviceName,
      limit: limit,
    });
    return data?.messages ?? [];
  } catch (error) {
    console.error("Error getting messages:", error);
    return [];
  }
}

export async function clearMessages(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.CLEAR_MESSAGES, "post", {
      device_name: deviceName,
    });
    return data;
  } catch (error) {
    console.error("Error clearing messages:", error);
    throw error;
  }
}

export async function getAvgTime(deviceName: string): Promise<AvgTimeStats | null> {
  try {
    const data = await requestApi(DEVICE_API.AVG_TIME, "post", {
      device_name: deviceName,
    });
    return data;
  } catch (error) {
    console.error("Error getting avg time:", error);
    return null;
  }
}

// ===== IEC61850 任务进度（兼容原连接进度接口） =====

export interface IEC61850ConnectProgress {
  phase: "idle" | "connecting" | "discovering" | "reading" | "done" | "failed";
  progress: number;
  connecting: boolean;
  active?: boolean;
  operation?: "idle" | "connect" | "discover" | "read";
  operation_id?: number;
  elapsed_seconds?: number;
  message?: string;
}

export async function getIEC61850ConnectProgress(
  deviceName: string
): Promise<IEC61850ConnectProgress | null> {
  try {
    const data = await requestApi(DEVICE_API.IEC61850_CONNECT_PROGRESS, "post", {
      device_name: deviceName,
    });
    return data;
  } catch (error) {
    console.error("Error getting IEC61850 connect progress:", error);
    return null;
  }
}

// ===== IEC61850 模型加载/导入 =====

export async function loadIEC61850Model(
  deviceName: string
): Promise<any> {
  try {
    const data = await requestApi(DEVICE_API.IEC61850_LOAD_MODEL, "post", {
      device_name: deviceName,
    }, 60000);
    return data;
  } catch (error) {
    console.error("Error loading IEC61850 model:", error);
    throw error;
  }
}

export async function importIEC61850Model(
  deviceName: string,
  icdPath: string
): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.IEC61850_IMPORT_MODEL, "post", {
      device_name: deviceName,
      icd_path: icdPath,
    }, 60000);
    return data;
  } catch (error) {
    console.error("Error importing IEC61850 model:", error);
    throw error;
  }
}

export async function discoverIEC61850Model(
  deviceName: string,
  timeout?: number
): Promise<boolean> {
  try {
    const data = await requestApi(
      DEVICE_API.IEC61850_DISCOVER_MODEL,
      "post",
      {
        device_name: deviceName,
      },
      timeout
    );
    return data;
  } catch (error) {
    console.error("Error discovering IEC61850 model:", error);
    throw error;
  }
}

// ===== IEC 61850 模型导出 =====

export type ExportModelType = "icd" | "json" | "xml" | "csv" | "tree";

export async function exportModel(
  deviceName: string,
  exportType: ExportModelType,
  fileHandle: FileSystemFileHandle | null = null,
  defaultFilename: string = "",
  iedName: string = ""
): Promise<void> {
  if (!defaultFilename) {
    const extMap: Record<ExportModelType, string> = {
      icd: ".icd",
      json: ".json",
      xml: ".xml",
      csv: ".csv",
      tree: ".txt",
    };
    defaultFilename = `${deviceName}_model${extMap[exportType]}`;
  }

  // 2. 使用独立 fetch 通道下载文件 — 完全绕过 axios 拦截器和响应式系统
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5 * 60 * 1000);

  let response: Response;
  try {
    const baseURL = (import.meta.env.VUE_APP_API_BASE || "/").replace(/\/+$/, "");
    const apiPath = DEVICE_API.EXPORT_MODEL.replace(/^\/+/, "");
    response = await fetch(`${baseURL}/${apiPath}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        device_name: deviceName,
        export_type: exportType,
        ied_name: iedName,
      }),
      signal: controller.signal,
      cache: "no-store",
    });
  } catch (err: any) {
    clearTimeout(timeoutId);
    if (err?.name === "AbortError") {
      throw new Error("导出超时，模型可能过大，请重试");
    }
    throw new Error(`网络请求失败: ${err.message}`);
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    let errorMsg = `导出失败 (HTTP ${response.status})`;
    try {
      const errorData = await response.json();
      if (errorData?.message) {
        errorMsg = errorData.message;
      }
    } catch {
      // 非 JSON 响应
    }
    throw new Error(errorMsg);
  }

  // 3. 写入文件 — showSaveFilePicker 可用时流式写入，否则 blob + <a> 下载
  try {
    if (fileHandle) {
      // File System Access API: 流式写入，内存友好
      const readable = response.body;
      if (readable) {
        const writable = await fileHandle.createWritable();
        const reader = readable.getReader();
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            await writable.write(value);
          }
        } finally {
          await writable.close();
          reader.releaseLock();
        }
      } else {
        const blob = await response.blob();
        const w = await fileHandle.createWritable();
        await w.write(blob);
        await w.close();
      }
    } else {
      // 回退：没有 showSaveFilePicker（Tauri / Firefox 等），使用 blob 下载
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = defaultFilename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      // 延迟一小段时间确保下载触发（不 await）
      await new Promise((r) => setTimeout(r, 100));
    }
  } catch (err: any) {
    throw new Error(`写入文件失败: ${err.message}`);
  }
}

// ===== 动态测点/从机管理 =====

export async function addSlave(deviceName: string, slaveId: number): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.ADD_SLAVE, "post", {
      device_name: deviceName,
      slave_id: slaveId,
    });
    return data;
  } catch (error) {
    console.error("Error adding slave:", error);
    throw error;
  }
}

export async function deleteSlave(deviceName: string, slaveId: number): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.DELETE_SLAVE, "post", {
      device_name: deviceName,
      slave_id: slaveId,
    });
    return data;
  } catch (error) {
    console.error("Error deleting slave:", error);
    throw error;
  }
}

export async function editSlave(
  deviceName: string,
  oldSlaveId: number,
  newSlaveId: number
): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.EDIT_SLAVE, "post", {
      device_name: deviceName,
      old_slave_id: oldSlaveId,
      new_slave_id: newSlaveId,
    });
    return data;
  } catch (error) {
    console.error("Error editing slave:", error);
    throw error;
  }
}
