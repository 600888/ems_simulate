"""
报文解析模块
将原始 Modbus 报文字节解析为人类可读的描述信息。
后续可扩展支持 DLT645 和 IEC104。
"""

from typing import Optional, Dict


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
