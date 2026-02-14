"""
报文解析模块
将原始协议报文字节解析为人类可读的描述信息。
支持 Modbus、DLT645 和 IEC104 协议。
"""

from typing import Optional, Dict        
from dlt645.protocol.frame import Frame
from dlt645.protocol.protocol import DLT645Protocol

# Modbus 异常码名称映射
MODBUS_EXCEPTION_CODES: Dict[int, str] = {
    0x01: "非法功能码",
    0x02: "非法数据地址",
    0x03: "非法数据值",
    0x04: "从站设备故障",
    0x05: "确认(Acknowledge)",
    0x06: "从站设备忙",
    0x08: "存储奇偶校验错误",
    0x0A: "网关路径不可用",
    0x0B: "网关目标设备未响应",
}

# 功能码名称映射
FUNC_CODE_NAMES: Dict[int, str] = {
    0x01: "读线圈",
    0x02: "读离散输入",
    0x03: "读保持寄存器",
    0x04: "读输入寄存器",
    0x05: "写单个线圈",
    0x06: "写单个寄存器",
    0x0F: "写多个线圈",
    0x10: "写多个寄存器",
}


class ModbusMessageParser:
    """Modbus 报文解析器
    
    纯静态方法实现，不依赖设备状态。
    支持 Modbus TCP (含 MBAP 头) 和 Modbus RTU 帧格式。
    """

    @staticmethod
    def parse_tcp(raw_hex: str, last_request_info: Optional[dict] = None) -> str:
        """解析 Modbus TCP 报文
        
        Args:
            raw_hex: 不带空格的十六进制字符串 (e.g. "000100000006010300000009")
            last_request_info: 上一条请求的解析信息，用于关联响应
                               格式: {"func_code": int, "slave_id": int, "start_addr": int, "end_addr": int}
        
        Returns:
            人类可读的描述字符串
        """
        try:
            data = bytes.fromhex(raw_hex)
        except (ValueError, TypeError):
            return ""

        # Modbus TCP: MBAP Header (7 bytes) + PDU
        # MBAP: Transaction ID (2) + Protocol ID (2) + Length (2) + Unit ID (1)
        if len(data) < 8:
            return ""

        slave_id = data[6]  # Unit ID
        pdu = data[7:]      # PDU 部分

        return ModbusMessageParser._parse_pdu(pdu, slave_id, last_request_info)

    @staticmethod
    def parse_rtu(raw_hex: str, last_request_info: Optional[dict] = None) -> str:
        """解析 Modbus RTU 报文
        
        Args:
            raw_hex: 不带空格的十六进制字符串
            last_request_info: 上一条请求的解析信息
        
        Returns:
            人类可读的描述字符串
        """
        try:
            data = bytes.fromhex(raw_hex)
        except (ValueError, TypeError):
            return ""

        # Modbus RTU: Slave ID (1) + PDU + CRC (2)
        if len(data) < 4:
            return ""

        slave_id = data[0]
        pdu = data[1:-2]  # 去掉首字节从站地址和尾部2字节CRC

        return ModbusMessageParser._parse_pdu(pdu, slave_id, last_request_info)

    @staticmethod
    def _parse_pdu(pdu: bytes, slave_id: int, last_request_info: Optional[dict] = None) -> str:
        """解析 Modbus PDU（协议数据单元）
        
        Args:
            pdu: PDU 字节数据（功能码 + 数据）
            slave_id: 从站地址
            last_request_info: 上一条请求的解析结果，用于为响应补充地址信息
        
        Returns:
            解析描述字符串
        """
        if not pdu:
            return ""

        func_code = pdu[0]

        # 异常响应: 功能码 >= 0x80
        if func_code >= 0x80:
            original_fc = func_code - 0x80
            fc_name = FUNC_CODE_NAMES.get(original_fc, f"功能码0x{original_fc:02X}")
            if len(pdu) >= 2:
                exc_code = pdu[1]
                exc_name = MODBUS_EXCEPTION_CODES.get(exc_code, f"未知异常(0x{exc_code:02X})")
                return f"{fc_name} 异常响应: {exc_name} (从站 {slave_id})"
            return f"{fc_name} 异常响应 (从站 {slave_id})"

        fc_name = FUNC_CODE_NAMES.get(func_code, None)
        if fc_name is None:
            return f"未知功能码 0x{func_code:02X} (从站 {slave_id})"

        # 读类功能码请求: FC(1) + StartAddr(2) + Quantity(2) = 5 bytes
        if func_code in (0x01, 0x02, 0x03, 0x04):
            if len(pdu) == 5:
                # 这是一个请求
                start_addr = (pdu[1] << 8) | pdu[2]
                quantity = (pdu[3] << 8) | pdu[4]
                end_addr = start_addr + quantity - 1
                return f"{fc_name} 0x{start_addr:04X}-0x{end_addr:04X} (从站 {slave_id})"
            else:
                # 这是一个响应: FC(1) + ByteCount(1) + Data(N)
                # 需要关联请求来获取地址范围
                if last_request_info and last_request_info.get("func_code") == func_code:
                    start = last_request_info["start_addr"]
                    end = last_request_info["end_addr"]
                    return f"{fc_name} 0x{start:04X}-0x{end:04X} 响应 (从站 {slave_id})"
                else:
                    # 无法关联请求，使用字节数描述
                    if len(pdu) >= 2:
                        byte_count = pdu[1]
                        if func_code in (0x03, 0x04):
                            reg_count = byte_count // 2
                            return f"{fc_name} 响应: {reg_count}个寄存器 (从站 {slave_id})"
                        else:
                            return f"{fc_name} 响应: {byte_count}字节 (从站 {slave_id})"
                    return f"{fc_name} 响应 (从站 {slave_id})"

        # 写单个线圈/寄存器请求和响应格式相同: FC(1) + Addr(2) + Value(2) = 5 bytes
        if func_code in (0x05, 0x06):
            if len(pdu) >= 5:
                addr = (pdu[1] << 8) | pdu[2]
                value = (pdu[3] << 8) | pdu[4]
                if func_code == 0x05:
                    val_desc = "ON" if value == 0xFF00 else "OFF"
                else:
                    val_desc = str(value)
                
                # 区分请求和响应：通过 last_request_info 判断
                # 如果上一条请求的 func_code 和当前相同，说明这是响应
                if last_request_info and last_request_info.get("func_code") == func_code:
                    return f"{fc_name} 0x{addr:04X} 响应 (从站 {slave_id})"
                else:
                    return f"{fc_name} 0x{addr:04X}={val_desc} (从站 {slave_id})"
            return f"{fc_name} (从站 {slave_id})"

        # 写多个线圈: FC(1) + StartAddr(2) + Quantity(2) + ByteCount(1) + Data(N)
        # 写多个寄存器: FC(1) + StartAddr(2) + Quantity(2) + ByteCount(1) + Data(N)
        if func_code in (0x0F, 0x10):
            if len(pdu) >= 5:
                start_addr = (pdu[1] << 8) | pdu[2]
                quantity = (pdu[3] << 8) | pdu[4]
                end_addr = start_addr + quantity - 1

                # 请求: 有 ByteCount + Data (len > 5)
                # 响应: 只有 StartAddr + Quantity (len == 5)
                if len(pdu) == 5:
                    # 这是响应
                    return f"{fc_name} 0x{start_addr:04X}-0x{end_addr:04X} 响应 (从站 {slave_id})"
                else:
                    # 这是请求
                    return f"{fc_name} 0x{start_addr:04X}-0x{end_addr:04X} (从站 {slave_id})"
            return f"{fc_name} (从站 {slave_id})"

        return f"{fc_name} (从站 {slave_id})"

    @staticmethod
    def extract_request_info(raw_hex: str, is_tcp: bool = True) -> Optional[dict]:
        """从请求报文中提取关键信息，用于关联后续响应
        
        Args:
            raw_hex: 不带空格的十六进制字符串
            is_tcp: True 表示 TCP 格式，False 表示 RTU 格式
        
        Returns:
            解析信息字典，包含 func_code, slave_id, start_addr, end_addr
            如果不是可识别的请求，返回 None
        """
        try:
            data = bytes.fromhex(raw_hex)
        except (ValueError, TypeError):
            return None

        if is_tcp:
            if len(data) < 8:
                return None
            slave_id = data[6]
            pdu = data[7:]
        else:
            if len(data) < 4:
                return None
            slave_id = data[0]
            pdu = data[1:-2]

        if not pdu:
            return None

        func_code = pdu[0]

        # 读类请求
        if func_code in (0x01, 0x02, 0x03, 0x04) and len(pdu) == 5:
            start_addr = (pdu[1] << 8) | pdu[2]
            quantity = (pdu[3] << 8) | pdu[4]
            return {
                "func_code": func_code,
                "slave_id": slave_id,
                "start_addr": start_addr,
                "end_addr": start_addr + quantity - 1,
            }

        # 写单个请求
        if func_code in (0x05, 0x06) and len(pdu) >= 5:
            addr = (pdu[1] << 8) | pdu[2]
            return {
                "func_code": func_code,
                "slave_id": slave_id,
                "start_addr": addr,
                "end_addr": addr,
            }

        # 写多个请求 (len > 5 表示请求，== 5 表示响应)
        if func_code in (0x0F, 0x10) and len(pdu) > 5:
            start_addr = (pdu[1] << 8) | pdu[2]
            quantity = (pdu[3] << 8) | pdu[4]
            return {
                "func_code": func_code,
                "slave_id": slave_id,
                "start_addr": start_addr,
                "end_addr": start_addr + quantity - 1,
            }

        return None


class DLT645MessageParser:
    """DLT645 报文解析器
    
    解析 DLT645-2007 协议帧格式：
    68 ADDR(6字节) 68 CTRL(1字节) LEN(1字节) DATA(N字节) CS(1字节) 16
    """
    @staticmethod
    def parse(raw_hex: str) -> str:
        """解析 DLT645 报文
        
        Args:
            raw_hex: 不带空格的十六进制字符串
        
        Returns:
            人类可读的描述字符串
        """
        try:
            # 将十六进制字符串转换为字节流
            raw_bytes = bytes.fromhex(raw_hex.replace(" ", ""))
        except ValueError:
            return ""

        # 尝试反序列化
        frame = DLT645Protocol.deserialize(raw_bytes)
        if frame is None:
            return ""
        return frame.description

class IEC104MessageParser:
    """IEC104 报文解析器
    
    解析 IEC 60870-5-104 协议 APCI/APDU 帧格式：
    启动字节(0x68) + 长度(1字节) + 控制域(4字节) + [ASDU]
    """

    # ASDU 类型标识 (TypeID) → 中文名称
    TYPE_IDS: Dict[int, str] = {
        # 监视方向 - 过程信息
        1:  "单点遥信",            # M_SP_NA_1
        2:  "单点遥信(带时标)",     # M_SP_TA_1
        3:  "双点遥信",            # M_DP_NA_1
        4:  "双点遥信(带时标)",     # M_DP_TA_1
        5:  "步位置信息",          # M_ST_NA_1
        7:  "32位串",             # M_BO_NA_1
        9:  "归一化遥测",          # M_ME_NA_1
        11: "标度化遥测",          # M_ME_NB_1
        13: "短浮点遥测",          # M_ME_NC_1
        15: "累计量",             # M_IT_NA_1
        20: "带状态的成组单点遥信",  # M_PS_NA_1
        21: "归一化遥测(不带品质)",  # M_ME_ND_1
        # CP56Time2a 时标版本
        30: "单点遥信(CP56)",      # M_SP_TB_1
        31: "双点遥信(CP56)",      # M_DP_TB_1
        32: "步位置信息(CP56)",     # M_ST_TB_1
        33: "32位串(CP56)",        # M_BO_TB_1
        34: "归一化遥测(CP56)",     # M_ME_TD_1
        35: "标度化遥测(CP56)",     # M_ME_TE_1
        36: "短浮点遥测(CP56)",     # M_ME_TF_1
        37: "累计量(CP56)",        # M_IT_TB_1
        38: "带保护的事件(CP56)",   # M_EP_TD_1
        39: "成组保护事件(CP56)",   # M_EP_TE_1
        40: "成组保护输出(CP56)",   # M_EP_TF_1
        # 控制方向 - 过程命令
        45: "单点遥控",            # C_SC_NA_1
        46: "双点遥控",            # C_DC_NA_1
        47: "步调节命令",          # C_RC_NA_1
        48: "设定值(归一化)",       # C_SE_NA_1
        49: "设定值(标度化)",       # C_SE_NB_1
        50: "设定值(短浮点)",       # C_SE_NC_1
        51: "32位串命令",          # C_BO_NA_1
        58: "单点遥控(CP56)",      # C_SC_TA_1
        59: "双点遥控(CP56)",      # C_DC_TA_1
        60: "步调节命令(CP56)",     # C_RC_TA_1
        61: "设定值归一化(CP56)",   # C_SE_TA_1
        62: "设定值标度化(CP56)",   # C_SE_TB_1
        63: "设定值短浮点(CP56)",   # C_SE_TC_1
        # 系统命令
        100: "总召唤",             # C_IC_NA_1
        101: "电度量召唤",          # C_CI_NA_1
        102: "读命令",             # C_RD_NA_1
        103: "时钟同步",           # C_CS_NA_1
        104: "测试命令",           # C_TS_NA_1
        105: "复位进程",           # C_RP_NA_1
        106: "延时获得",           # C_CD_NA_1
        107: "测试命令(CP56)",     # C_TS_TA_1
        # 文件传输
        110: "初始化结束",          # P_ME_NA_1
        111: "参数激活",            # P_ME_NB_1
        112: "参数定义(标度化)",     # P_ME_NC_1
        113: "参数激活",            # P_AC_NA_1
    }

    # 传送原因 (Cause of Transmission)
    COT_NAMES: Dict[int, str] = {
        1: "周期传送",
        2: "背景扫描",
        3: "突发(自发)",
        4: "初始化",
        5: "请求/被请求",
        6: "激活",
        7: "激活确认",
        8: "停止激活",
        9: "停止激活确认",
        10: "激活终止",
        11: "远程命令引起的返送",
        12: "当地命令引起的返送",
        13: "文件传输",
        20: "响应总召唤",
        37: "响应电度量召唤",
        44: "未知类型标识",
        45: "未知传送原因",
        46: "未知公共地址",
        47: "未知信息对象地址",
    }

    @staticmethod
    def parse(raw_hex: str) -> str:
        """解析 IEC104 报文
        
        Args:
            raw_hex: 不带空格的十六进制字符串
        
        Returns:
            人类可读的描述字符串
        """
        try:
            data = bytes.fromhex(raw_hex.replace(" ", ""))
        except (ValueError, TypeError):
            return ""

        # 最小帧长度: 启动字节(1) + 长度(1) + 控制域(4) = 6
        if len(data) < 6:
            return ""

        # 验证启动字节
        if data[0] != 0x68:
            return ""

        apdu_len = data[1]
        ctrl = data[2:6]

        # 判断帧类型
        if (ctrl[0] & 0x03) == 0x03:
            # U 帧（无编号帧）
            return IEC104MessageParser._parse_u_frame(ctrl)
        elif (ctrl[0] & 0x01) == 0x01:
            # S 帧（监视帧）
            recv_seq = ((ctrl[2] | (ctrl[3] << 8)) >> 1)
            return f"S帧 确认接收序号:{recv_seq}"
        else:
            # I 帧（信息帧）
            send_seq = ((ctrl[0] | (ctrl[1] << 8)) >> 1)
            recv_seq = ((ctrl[2] | (ctrl[3] << 8)) >> 1)
            
            # I 帧包含 ASDU
            if len(data) > 6:
                asdu_desc = IEC104MessageParser._parse_asdu(data[6:])
                return f"I帧 [{send_seq},{recv_seq}] {asdu_desc}"
            return f"I帧 发送:{send_seq} 接收:{recv_seq}"

    @staticmethod
    def _parse_u_frame(ctrl: bytes) -> str:
        """解析 U 帧子类型"""
        u_type = ctrl[0]
        if u_type & 0x04:
            return "U帧 STARTDT_ACT"
        elif u_type & 0x08:
            return "U帧 STARTDT_CON"
        elif u_type & 0x10:
            return "U帧 STOPDT_ACT"
        elif u_type & 0x20:
            return "U帧 STOPDT_CON"
        elif u_type & 0x40:
            return "U帧 TESTFR_ACT"
        elif u_type & 0x80:
            return "U帧 TESTFR_CON"
        return f"U帧 未知(0x{u_type:02X})"

    @staticmethod
    def _parse_asdu(asdu: bytes) -> str:
        """解析 ASDU (应用服务数据单元)
        
        ASDU 结构:
        TypeID(1) + VSQ(1) + COT(2) + CommonAddr(2) + IOA(3) + ...
        """
        if len(asdu) < 6:
            return ""

        type_id = asdu[0]
        vsq = asdu[1]
        num_objects = vsq & 0x7F  # 信息体数量
        sq = (vsq >> 7) & 0x01   # SQ标志

        # 传送原因（2字节，低字节为COT）
        cot = asdu[2] & 0x3F  # 取低6位
        is_test = (asdu[2] >> 7) & 0x01
        is_negative = (asdu[2] >> 6) & 0x01

        # 公共地址（2字节）
        common_addr = asdu[4] | (asdu[5] << 8)

        # 类型标识名称
        type_name = IEC104MessageParser.TYPE_IDS.get(
            type_id, f"TypeID:{type_id}"
        )

        # 传送原因名称
        cot_name = IEC104MessageParser.COT_NAMES.get(
            cot, f"COT:{cot}"
        )

        # 尝试提取第一个 IOA
        ioa_desc = ""
        if len(asdu) >= 9:
            ioa = asdu[6] | (asdu[7] << 8) | (asdu[8] << 16)
            if num_objects == 1:
                ioa_desc = f" IOA:{ioa}"
            else:
                ioa_desc = f" IOA:{ioa} ({num_objects}个)"

        # 构建描述
        extra = ""
        if is_negative:
            extra += " [否定]"
        if is_test:
            extra += " [测试]"

        return f"{type_name}{ioa_desc} ({cot_name}){extra}"

