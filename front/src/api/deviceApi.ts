/**
 * 设备管理 API
 */
import i18n from "@/i18n";

import { instance, requestApi } from "./http";
import { DEVICE_API } from "@/constants";

// ===== 类型导出（供外部使用） =====

export interface MessageRecord {
  sequence_id: number;
  timestamp: number;
  formatted_time: string;
  direction: string;
  hex_data: string;
  raw_hex: string;
  description: string;
  length: number;
  protocol_type: string;
  /** Modbus Unit ID or IEC104 common address; control frames have no slave ID. */
  slave_id: number | null;
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

export async function getDeviceInfo(
  deviceName: string,
): Promise<Map<string, any>> {
  try {
    const data = await requestApi(DEVICE_API.INFO, "post", {
      device_name: deviceName,
    });
    return new Map<string, any>(Object.entries(data));
  } catch (error) {
    console.error("Error fetching device info:", error);
    throw error;
  }
}

export async function startSimulation(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.START_SIMULATION, "post", {
      device_name: deviceName,
      // simulate_method 不传：不覆盖各测点已配置的模拟方式
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

// ===== 测点级模拟配置 =====

export interface SimulationConfigItem {
  point_code: string;
  name?: string;
  frame_type?: number | null;
  simulate_method: string;
  step: number;
  fixed_value: number;
  enabled: boolean;
}

export interface SimulationConfigApplyResult {
  applied: string[];
  failed: { point_code: string; reason: string }[];
}

/** 获取整机测点模拟配置（Dialog 回显用） */
export async function getSimulationConfig(
  deviceName: string,
): Promise<SimulationConfigItem[]> {
  try {
    return await requestApi(DEVICE_API.SIMULATION_CONFIG, "post", {
      device_name: deviceName,
    });
  } catch (error) {
    console.error("Error fetching simulation config:", error);
    throw error;
  }
}

/** 批量应用测点模拟配置（开始模拟前调用） */
export async function applySimulationConfig(
  deviceName: string,
  points: Pick<
    SimulationConfigItem,
    "point_code" | "enabled" | "simulate_method" | "step" | "fixed_value"
  >[],
): Promise<SimulationConfigApplyResult> {
  try {
    return await requestApi(DEVICE_API.APPLY_SIMULATION_CONFIG, "post", {
      device_name: deviceName,
      points,
    });
  } catch (error) {
    console.error("Error applying simulation config:", error);
    throw error;
  }
}

export async function startDevice(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.START, "post", {
      device_name: deviceName,
    });
    return data;
  } catch (error) {
    console.error("Error starting device:", error);
    throw error;
  }
}

export async function stopDevice(deviceName: string): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.STOP, "post", {
      device_name: deviceName,
    });
    return data;
  } catch (error) {
    console.error("Error stopping device:", error);
    throw error;
  }
}

// ===== 从机管理 =====

export async function getSlaveIdList(
  deviceName: string,
): Promise<Array<number>> {
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
  orderDirection: string | null = null,
  iec104Types: string[] = [],
  dlt645Prefix: number | null = null,
  dlt645Settlement: number | null = null,
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
      iec104_types: iec104Types,
      dlt645_prefix: dlt645Prefix,
      dlt645_settlement: dlt645Settlement,
    });
    return new Map<string, any>(Object.entries(data));
  } catch (error) {
    console.error("Error get device table:", error);
    throw error;
  }
}

// ===== 自动读取控制 =====

export type AutoReadMode = "batch" | "single" | "dataset";
export type AutoReadState = "idle" | "running" | "stopping" | "failed";

export interface AutoReadConfig {
  mode: AutoReadMode;
  cycle_interval_ms: number;
  request_interval_ms?: number;
  slave_id?: number;
  channel_id?: number;
  category?: string;
  item?: string;
  point_types?: number[];
  dlt645_prefix?: number | null;
  dlt645_settlement?: number | null;
}

export interface AutoReadStatus {
  state: AutoReadState;
  task_id: string | null;
  mode: AutoReadMode | null;
  config: AutoReadConfig | null;
  started_at: string | null;
  last_cycle_at: string | null;
  cycle_count: number;
  current: number;
  total: number;
  success: number;
  fail: number;
  last_error: string | null;
}

const idleAutoReadStatus = (): AutoReadStatus => ({
  state: "idle",
  task_id: null,
  mode: null,
  config: null,
  started_at: null,
  last_cycle_at: null,
  cycle_count: 0,
  current: 0,
  total: 0,
  success: 0,
  fail: 0,
  last_error: null,
});

export async function getAutoReadStatus(
  deviceName: string,
): Promise<AutoReadStatus> {
  try {
    const data = await requestApi(DEVICE_API.AUTO_READ_STATUS, "post", {
      device_name: deviceName,
    });
    return data;
  } catch (error) {
    console.error("Error getting auto read status:", error);
    return idleAutoReadStatus();
  }
}

export async function startAutoRead(
  deviceName: string,
  config: AutoReadConfig,
): Promise<AutoReadStatus> {
  try {
    const data = await requestApi(DEVICE_API.START_AUTO_READ, "post", {
      device_name: deviceName,
      ...config,
    });
    return data;
  } catch (error) {
    console.error("Error starting auto read:", error);
    throw error;
  }
}

export async function stopAutoRead(
  deviceName: string,
): Promise<AutoReadStatus> {
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

export async function manualRead(
  deviceName: string,
  config: AutoReadConfig,
): Promise<AutoReadStatus> {
  try {
    const data = await requestApi(DEVICE_API.MANUAL_READ, "post", {
      device_name: deviceName,
      interval: config.request_interval_ms ?? 0,
      ...config,
    });
    return data;
  } catch (error) {
    console.error("Error performing manual read:", error);
    throw error;
  }
}

export async function getManualReadStatus(
  deviceName: string,
): Promise<AutoReadStatus> {
  return await requestApi(DEVICE_API.MANUAL_READ_STATUS, "post", {
    device_name: deviceName,
  });
}

export async function stopManualRead(
  deviceName: string,
): Promise<AutoReadStatus> {
  return await requestApi(DEVICE_API.STOP_MANUAL_READ, "post", {
    device_name: deviceName,
  });
}

export async function iec104Interrogation(
  deviceName: string,
): Promise<boolean> {
  try {
    const data = await requestApi(DEVICE_API.IEC104_INTERROGATION, "post", {
      device_name: deviceName,
    });
    return data;
  } catch (error) {
    console.error("Error sending IEC104 interrogation:", error);
    throw error;
  }
}

/**
 * 发送 DL/T645 特殊命令（主站/从站功能）
 *
 * @param deviceName 设备名称
 * @param command 命令名（read_address / write_address / broadcast_time_sync /
 *                freeze / change_baud_rate / change_password /
 *                clear_demand / clear_meter / clear_event / set_time）
 * @param params 命令参数（地址 / 速率 / 密码 / 时间等）
 * @returns 后端返回的 detail（成功时），失败抛异常
 */
export async function sendDlt645Command(
  deviceName: string,
  command: string,
  params: Record<string, unknown> = {},
): Promise<any> {
  const data = await requestApi(DEVICE_API.DLT645_COMMAND, "post", {
    device_name: deviceName,
    command,
    params,
  });
  return data;
}

/**
 * 获取 DL/T645 数据标识（DI）的元信息：名称、数据格式、是否列表及子项格式
 *
 * @param deviceName 设备名称
 * @param di 数据标识（十六进制，如 "0x00000000"）
 * @returns { di, name, is_list, data_format, list_formats, min_value, max_value }
 */
export async function getDlt645DiInfo(
  deviceName: string,
  di: string,
): Promise<any> {
  return requestApi(DEVICE_API.DLT645_DI_INFO, "post", {
    device_name: deviceName,
    di,
  });
}

// ===== 报文捕获 =====
export async function getMessages(
  deviceName: string,
  limit: number = 100,
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

export async function getMessageDetail(
  deviceName: string,
  sequenceId: number,
): Promise<MessageDetail> {
  return await requestApi(DEVICE_API.MESSAGE_DETAIL, "post", {
    device_name: deviceName,
    sequence_id: sequenceId,
  });
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

export async function getAvgTime(
  deviceName: string,
): Promise<AvgTimeStats | null> {
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
  error_code?:
    "connection_failed" | "connection_exception" | "model_mismatch" | string;
}

export interface ParsedField {
  key: string;
  name: string;
  offset: number;
  length: number;
  raw_hex: string;
  value: unknown;
  display_value: string;
  description: string;
  level: "normal" | "warning" | "error";
}

export interface ParsedObject {
  index: number;
  offset: number;
  length: number;
  address: number | string | null;
  value: unknown;
  raw_value: unknown;
  quality: Record<string, unknown> | null;
  timestamp: string | null;
  fields: ParsedField[];
  name?: string;
  unit?: string;
  timestamp_detail?: Record<string, unknown> | null;
  decoded_value?: unknown;
  engineering_value?: unknown;
  combined_raw?: string;
  covered_by_point?: string;
  warnings?: string[];
  point?: {
    name: string;
    code: string;
    address: number | string;
    slave_id: number;
    function_code: number;
    frame_type: number;
    decode_code: string;
    iec_type_id: string | null;
    multiplier: number;
    addition: number;
  };
}

export interface MessageDetail {
  sequence_id: number;
  protocol: string;
  frame_kind: string;
  role: string;
  summary: string;
  purpose: string;
  valid: boolean;
  complete: boolean;
  raw_hex: string;
  raw_length: number;
  direction: string;
  msg_type: string;
  formatted_time: string;
  fields: ParsedField[];
  objects: ParsedObject[];
  validation: Array<{ name: string; passed: boolean; detail: string }>;
  correlation: {
    request_sequence_id?: number;
    start_address?: number;
    end_address?: number;
    quantity?: number;
    match_method?: string;
  } | null;
  warnings: string[];
  errors: string[];
}

export async function getIEC61850ConnectProgress(
  deviceName: string,
): Promise<IEC61850ConnectProgress | null> {
  try {
    const data = await requestApi(
      DEVICE_API.IEC61850_CONNECT_PROGRESS,
      "post",
      {
        device_name: deviceName,
      },
    );
    return data;
  } catch (error) {
    console.error("Error getting IEC61850 connect progress:", error);
    return null;
  }
}

// ===== IEC61850 模型加载/导入 =====

export async function loadIEC61850Model(deviceName: string): Promise<any> {
  try {
    const data = await requestApi(
      DEVICE_API.IEC61850_LOAD_MODEL,
      "post",
      {
        device_name: deviceName,
      },
      60000,
    );
    return data;
  } catch (error) {
    console.error("Error loading IEC61850 model:", error);
    throw error;
  }
}

export async function importIEC61850Model(
  deviceName: string,
  icdPath: string,
): Promise<boolean> {
  try {
    const data = await requestApi(
      DEVICE_API.IEC61850_IMPORT_MODEL,
      "post",
      {
        device_name: deviceName,
        icd_path: icdPath,
      },
      60000,
    );
    return data;
  } catch (error) {
    console.error("Error importing IEC61850 model:", error);
    throw error;
  }
}

export async function discoverIEC61850Model(
  deviceName: string,
  timeout?: number,
): Promise<boolean> {
  try {
    const data = await requestApi(
      DEVICE_API.IEC61850_DISCOVER_MODEL,
      "post",
      {
        device_name: deviceName,
      },
      timeout,
    );
    return data;
  } catch (error) {
    console.error("Error discovering IEC61850 model:", error);
    throw error;
  }
}

export async function checkIEC61850ModelCache(
  deviceName: string,
): Promise<{ cache_exists: boolean; cache_key: string }> {
  try {
    const data = await requestApi(
      DEVICE_API.IEC61850_MODEL_CACHE_STATUS,
      "post",
      {
        device_name: deviceName,
      },
    );
    return data;
  } catch (error) {
    console.error("Error checking IEC61850 model cache:", error);
    return { cache_exists: false, cache_key: "" };
  }
}

export async function loadIEC61850ModelFromCache(
  deviceName: string,
): Promise<boolean> {
  try {
    const data = await requestApi(
      DEVICE_API.IEC61850_LOAD_MODEL_FROM_CACHE,
      "post",
      {
        device_name: deviceName,
      },
    );
    return data;
  } catch (error) {
    console.error("Error loading IEC61850 model from cache:", error);
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
  iedName: string = "",
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
    const baseURL = (import.meta.env.VUE_APP_API_BASE || "/").replace(
      /\/+$/,
      "",
    );
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
      throw new Error(i18n.global.t("common.exportTimeout"));
    }
    throw new Error(
      `${i18n.global.t("common.networkRequestFailed")}: ${err.message}`,
    );
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    let errorMsg = i18n.global.t("common.exportFailed", {
      status: response.status,
    });
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
    throw new Error(
      i18n.global.t("device.writeFileFailed", { msg: err.message }),
    );
  }
}

// ===== 动态测点/从机管理 =====

export async function addSlave(
  deviceName: string,
  slaveId: number,
): Promise<boolean> {
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

export async function deleteSlave(
  deviceName: string,
  slaveId: number,
): Promise<boolean> {
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
  newSlaveId: number,
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
