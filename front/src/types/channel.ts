/**
 * 通道/设备相关类型定义
 */

// 连接类型
export enum ConnType {
  SerialMaster = 0, // 串口主站（主动轮询）
  TcpClient = 1, // TCP客户端
  TcpServer = 2, // TCP服务端
  SerialSlave = 3, // 串口从站（被动响应）
}

// 协议类型
export enum ProtocolType {
  ModbusRtu = 0,
  ModbusTcp = 1,
  Iec104 = 2,
  Dlt645 = 3,
  Iec61850 = 4,
  Dnp3 = 5,
  Iec101 = 6,
}

// 协议选项
export interface ProtocolOption {
  value: number;
  label: string;
  conn_types: number[];
}

// 连接类型选项
export interface ConnTypeOption {
  value: number;
  label: string;
}

// 协议配置响应
export interface ProtocolConfigResponse {
  protocols: ProtocolOption[];
  conn_types: ConnTypeOption[];
}

// 通道创建请求
export interface ChannelCreateRequest {
  code: string;
  name: string;
  protocol_type: number;
  conn_type: number;
  // 网络配置
  ip?: string;
  port?: number;
  // 串口配置
  com_port?: string;
  baud_rate?: number;
  data_bits?: number;
  stop_bits?: number;
  parity?: string;
  // RTU地址/电表地址
  rtu_addr?: string;
  // 设备组ID
  group_id?: number | null;
  protocol_params?: ProtocolParamsConfig;
  dlt645_point_mode?: "standard" | "import";
}

export interface ProtocolParamsConfig {
  schema_version: number;
  values: Record<string, number | boolean | string>;
}

export type TlsVersion = "1.2" | "1.3";

export interface SecurityConfig {
  tls_enabled: boolean;
  tls_mode: "one_way" | "mutual";
  tls_version?: TlsVersion;
  certificate_configured: boolean;
  certificate_filename?: string | null;
  private_key_configured: boolean;
  private_key_filename?: string | null;
  ca_certificate_configured: boolean;
  ca_certificate_filename?: string | null;
}

// 通道信息
export interface ChannelInfo {
  id: number;
  code: string;
  name: string;
  device_id?: number;
  protocol_type: number;
  conn_type: number;
  ip?: string;
  port?: number;
  com_port?: string;
  baud_rate?: number;
  data_bits?: number;
  stop_bits?: number;
  parity?: string;
  rtu_addr: string;
  timeout: number;
  enable: boolean;
  model_name?: string | null;
  icd_path?: string | null;
  icd_file_hash?: string | null;
  protocol_params?: ProtocolParamsConfig;
  security_config?: SecurityConfig;
  dlt645_point_mode?: "standard" | "import";
}

// 点表导入结果
export interface PointImportResult {
  yc_count: number;
  yx_count: number;
  yk_count: number;
  yt_count: number;
  total: number;
  // IEC61850 模型状态
  model_loaded?: boolean;
  // GOOSE 配置 (ICD 导入时可能返回)
  goose?: GooseImportData | null;
}

// GOOSE 导入数据（数据集条目）
export interface DataSetEntry {
  name: string;
  value: boolean | number | string;
  iec_type: string;
  fc?: string;
}

// GOOSE 导入数据（数据集信息）
export interface DataSetImportInfo {
  ld_inst: string;
  ds_name: string;
  ds_ref: string;
  data_set_ref: string;
  member_count: number;
  entries: DataSetEntry[];
}

// GOOSE 导入数据
export interface GooseImportData {
  summary: {
    gse_control_count: number;
    gse_controls: {
      go_cb_ref: string;
      go_id: string;
      app_id: string;
      dat_set: string;
      conf_rev: number;
      mac_address: string;
      dataset_member_count: number;
    }[];
  };
  publishers: any[];
  subscriptions: any[];
  /** 所有数据集列表（纯数据集 + GOOSE 引用的数据集） */
  datasets?: DataSetImportInfo[];
  /** 纯数据集（未被 GSEControl 引用的数据集） */
  pure_datasets?: DataSetImportInfo[];
  created_count: number;
  subscription_created_count?: number;
  import_mode?: "model_only" | "local_publish" | "remote_subscribe" | "both";
  errors: string[];
}
