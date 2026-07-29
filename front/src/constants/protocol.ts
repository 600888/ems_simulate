/**
 * 协议与通道相关常量
 */

// 协议类型枚举值（与后端对齐）
export const PROTOCOL_TYPE = {
  MODBUS_RTU: 0,
  MODBUS_TCP: 1,
  IEC104: 2,
  DLT645: 3,
  IEC61850: 4,
} as const;

// 连接类型枚举值
export const CONN_TYPE = {
  SERIAL_MASTER: 0,
  TCP_CLIENT: 1,
  TCP_SERVER: 2,
  SERIAL_SLAVE: 3,
} as const;

// 协议默认端口映射
export const PROTOCOL_DEFAULT_PORTS: Record<number, number> = {
  [PROTOCOL_TYPE.MODBUS_RTU]: 502,
  [PROTOCOL_TYPE.MODBUS_TCP]: 502,
  [PROTOCOL_TYPE.IEC104]: 2404,
  [PROTOCOL_TYPE.DLT645]: 8899,
  [PROTOCOL_TYPE.IEC61850]: 102,
} as const;

// 协议客户端默认 IP 映射（仅 TCP 客户端模式使用）
export const PROTOCOL_DEFAULT_CLIENT_IP: Record<number, string> = {
  [PROTOCOL_TYPE.IEC104]: "127.0.0.1",
  [PROTOCOL_TYPE.DLT645]: "127.0.0.1",
  [PROTOCOL_TYPE.IEC61850]: "127.0.0.1",
} as const;

// 标准波特率列表
export const BAUD_RATES = [
  1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200,
] as const;

// IEC61850 分类列表
export const IEC61850_CATEGORIES: ReadonlyArray<{
  key: string;
  label: string;
}> = [
  { key: "GOOSE", label: "GOOSE" },
  { key: "Reports", label: "Reports" },
  { key: "SettingGroups", label: "SettingGroups" },
  { key: "Files", label: "Files" },
  { key: "DataSets", label: "DataSets" },
  { key: "DataModel", label: "DataModel" },
] as const;

// GOOSE 订阅状态
export const GOOSE_SUB_STATE = {
  INIT: "init",
  CONNECTED: "connected",
  LOST: "lost",
  ERROR: "error",
} as const;

// GOOSE 订阅状态颜色映射
export const GOOSE_STATE_COLOR: Record<string, string> = {
  init: "#909399",
  connected: "#67C23A",
  lost: "#E6A23C",
  error: "#F56C6C",
} as const;

// GOOSE 订阅状态标签映射
export const GOOSE_STATE_LABEL: Record<string, string> = {
  init: "gooseStateLabels.init",
  connected: "gooseStateLabels.connected",
  lost: "gooseStateLabels.lost",
  error: "gooseStateLabels.error",
} as const;

// GOOSE IEC 数据类型选项
export const GOOSE_IEC_TYPE_OPTIONS: ReadonlyArray<{
  value: string;
  label: string;
}> = [
  { value: "boolean", label: "gooseIecTypes.boolean" },
  { value: "integer", label: "gooseIecTypes.integer" },
  { value: "float", label: "gooseIecTypes.float" },
  { value: "string", label: "gooseIecTypes.string" },
  { value: "bitstring", label: "gooseIecTypes.bitstring" },
  { value: "timestamp", label: "gooseIecTypes.timestamp" },
] as const;

// 判断 IEC61850 协议的字符串标识
export const IEC61850_PROTOCOL_NAMES = [
  "Iec61850Client",
  "Iec61850Server",
] as const;

// 判断 IEC104 协议的字符串标识
export const IEC104_PROTOCOL_NAMES = ["Iec104Client", "Iec104Server"] as const;

export const DLT645_PROTOCOL_NAMES = ["Dlt645Client", "Dlt645Server"] as const;

// 判断是否为 IEC61850 协议
export function isIec61850Protocol(protocolStr: string | number): boolean {
  return IEC61850_PROTOCOL_NAMES.includes(protocolStr as any);
}

// 判断是否为 IEC104 协议
export function isIec104Protocol(protocolStr: string | number): boolean {
  return IEC104_PROTOCOL_NAMES.includes(protocolStr as any);
}

export function isDlt645Protocol(protocolStr: string | number): boolean {
  return (
    protocolStr === PROTOCOL_TYPE.DLT645 ||
    DLT645_PROTOCOL_NAMES.includes(protocolStr as any)
  );
}
