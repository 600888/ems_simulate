/**
 * 通道/设备相关类型定义
 */

// 连接类型
export enum ConnType {
    Serial = 0,      // 串口
    TcpClient = 1,   // TCP客户端
    TcpServer = 2,   // TCP服务端
}

// 协议类型
export enum ProtocolType {
    ModbusRtu = 0,
    ModbusTcp = 1,
    Iec104 = 2,
    Dlt645 = 3,
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
}

// 点表导入结果
export interface PointImportResult {
    yc_count: number;
    yx_count: number;
    yk_count: number;
    yt_count: number;
    total: number;
}
