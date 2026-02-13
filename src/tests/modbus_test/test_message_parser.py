"""
Modbus 报文解析器单元测试
"""
import unittest
from src.device.core.message.message_parser import ModbusMessageParser


class TestModbusTcpParser(unittest.TestCase):
    """测试 Modbus TCP 报文解析"""

    # ===== 读类请求 =====

    def test_read_coils_request(self):
        """功能码 0x01 - 读线圈请求"""
        # MBAP(7) + FC(01) + StartAddr(0000) + Quantity(000A)
        raw = "00010000000601010000000a"
        result = ModbusMessageParser.parse_tcp(raw)
        self.assertIn("读线圈", result)
        self.assertIn("0x0000-0x0009", result)
        self.assertIn("从站 1", result)

    def test_read_discrete_inputs_request(self):
        """功能码 0x02 - 读离散输入请求"""
        raw = "000100000006010200c80032"
        result = ModbusMessageParser.parse_tcp(raw)
        self.assertIn("读离散输入", result)
        self.assertIn("0x00C8-0x00F9", result)
        self.assertIn("从站 1", result)

    def test_read_holding_registers_request(self):
        """功能码 0x03 - 读保持寄存器请求"""
        # MBAP: 0001 0000 0006, UnitID: 01, FC: 03, Start: 006B, Qty: 0003
        raw = "0001000000060103006b0003"
        result = ModbusMessageParser.parse_tcp(raw)
        self.assertIn("读保持寄存器", result)
        self.assertIn("0x006B-0x006D", result)
        self.assertIn("从站 1", result)

    def test_read_input_registers_request(self):
        """功能码 0x04 - 读输入寄存器请求"""
        raw = "000100000006010400080001"
        result = ModbusMessageParser.parse_tcp(raw)
        self.assertIn("读输入寄存器", result)
        self.assertIn("0x0008", result)
        self.assertIn("从站 1", result)

    # ===== 读类响应 =====

    def test_read_holding_registers_response_with_request(self):
        """功能码 0x03 - 读保持寄存器响应（关联请求）"""
        req_raw = "0001000000060103006b0003"
        req_info = ModbusMessageParser.extract_request_info(req_raw, is_tcp=True)

        # 响应: MBAP(7) + FC(03) + ByteCount(06) + Data(6 bytes)
        resp_raw = "0001000000090103060001000200030000"
        result = ModbusMessageParser.parse_tcp(resp_raw, last_request_info=req_info)
        self.assertIn("读保持寄存器", result)
        self.assertIn("0x006B-0x006D", result)
        self.assertIn("响应", result)
        self.assertIn("从站 1", result)

    def test_read_holding_registers_response_without_request(self):
        """功能码 0x03 - 读保持寄存器响应（无关联请求）"""
        resp_raw = "000100000009010306000100020003"
        result = ModbusMessageParser.parse_tcp(resp_raw)
        self.assertIn("读保持寄存器", result)
        self.assertIn("响应", result)
        self.assertIn("3个寄存器", result)

    # ===== 写类请求 =====

    def test_write_single_coil_request(self):
        """功能码 0x05 - 写单个线圈请求"""
        # Write coil at addr 0x00AC, value ON (0xFF00)
        raw = "0001000000060105 00ac ff00".replace(" ", "")
        result = ModbusMessageParser.parse_tcp(raw)
        self.assertIn("写单个线圈", result)
        self.assertIn("0x00AC", result)
        self.assertIn("ON", result)

    def test_write_single_register_request(self):
        """功能码 0x06 - 写单个寄存器请求"""
        raw = "00010000000601060001000a"
        result = ModbusMessageParser.parse_tcp(raw)
        self.assertIn("写单个寄存器", result)
        self.assertIn("0x0001", result)
        self.assertIn("10", result)  # 0x000A = 10

    def test_write_multiple_registers_request(self):
        """功能码 0x10 - 写多个寄存器请求"""
        # Write 2 registers at 0x0001, ByteCount=4, data=[0x000A, 0x0102]
        raw = "00010000000b0110000100020400 0a01 02".replace(" ", "")
        result = ModbusMessageParser.parse_tcp(raw)
        self.assertIn("写多个寄存器", result)
        self.assertIn("0x0001-0x0002", result)
        self.assertNotIn("响应", result)

    def test_write_multiple_registers_response(self):
        """功能码 0x10 - 写多个寄存器响应"""
        # Response: FC(10) + StartAddr(0001) + Quantity(0002) - 5 bytes PDU
        raw = "000100000006011000010002"
        result = ModbusMessageParser.parse_tcp(raw)
        self.assertIn("写多个寄存器", result)
        self.assertIn("0x0001-0x0002", result)
        self.assertIn("响应", result)

    def test_write_multiple_coils_request(self):
        """功能码 0x0F - 写多个线圈请求"""
        # Write 10 coils at 0x0013, ByteCount=2, data=[0xCD, 0x01]
        raw = "00010000000901 0f 0013 000a 02 cd01".replace(" ", "")
        result = ModbusMessageParser.parse_tcp(raw)
        self.assertIn("写多个线圈", result)
        self.assertIn("0x0013-0x001C", result)

    # ===== 异常响应 =====

    def test_exception_response(self):
        """异常响应"""
        # FC 0x83 (read holding registers exception), exception code 0x02 (illegal data address)
        raw = "000100000003018302"
        result = ModbusMessageParser.parse_tcp(raw)
        self.assertIn("异常响应", result)
        self.assertIn("非法数据地址", result)
        self.assertIn("读保持寄存器", result)

    def test_exception_response_unknown_code(self):
        """未知异常码"""
        raw = "00010000000301830f"
        result = ModbusMessageParser.parse_tcp(raw)
        self.assertIn("异常响应", result)
        self.assertIn("0x0F", result)

    # ===== 边界条件 =====

    def test_empty_data(self):
        """空数据"""
        self.assertEqual(ModbusMessageParser.parse_tcp(""), "")

    def test_invalid_hex(self):
        """无效十六进制"""
        self.assertEqual(ModbusMessageParser.parse_tcp("ZZZZ"), "")

    def test_too_short(self):
        """报文过短"""
        self.assertEqual(ModbusMessageParser.parse_tcp("0001"), "")

    def test_unknown_function_code(self):
        """未知功能码"""
        raw = "000100000003017f01"
        result = ModbusMessageParser.parse_tcp(raw)
        self.assertIn("未知功能码", result)
        self.assertIn("0x7F", result)

    def test_slave_id_extraction(self):
        """从站地址识别 - 从站 5"""
        raw = "0001000000060503006b0003"  # Unit ID = 5
        result = ModbusMessageParser.parse_tcp(raw)
        self.assertIn("从站 5", result)


class TestModbusRtuParser(unittest.TestCase):
    """测试 Modbus RTU 报文解析"""

    def test_read_holding_registers_request_rtu(self):
        """RTU - 读保持寄存器请求"""
        # SlaveID(01) + FC(03) + StartAddr(006B) + Qty(0003) + CRC(2 bytes)
        raw = "0103006b0003" + "a4b5"  # CRC 是假的，不影响解析
        result = ModbusMessageParser.parse_rtu(raw)
        self.assertIn("读保持寄存器", result)
        self.assertIn("0x006B-0x006D", result)
        self.assertIn("从站 1", result)

    def test_read_holding_registers_response_rtu(self):
        """RTU - 读保持寄存器响应（关联请求）"""
        req_raw = "0103006b0003a4b5"
        req_info = ModbusMessageParser.extract_request_info(req_raw, is_tcp=False)

        resp_raw = "01030600010002000300001234"
        result = ModbusMessageParser.parse_rtu(resp_raw, last_request_info=req_info)
        self.assertIn("读保持寄存器", result)
        self.assertIn("0x006B-0x006D", result)
        self.assertIn("响应", result)

    def test_exception_response_rtu(self):
        """RTU - 异常响应"""
        raw = "018302" + "c0f1"  # CRC 假数据
        result = ModbusMessageParser.parse_rtu(raw)
        self.assertIn("异常响应", result)
        self.assertIn("非法数据地址", result)


class TestExtractRequestInfo(unittest.TestCase):
    """测试请求信息提取"""

    def test_extract_read_request_tcp(self):
        """TCP 读请求提取"""
        raw = "0001000000060103006b0003"
        info = ModbusMessageParser.extract_request_info(raw, is_tcp=True)
        self.assertIsNotNone(info)
        self.assertEqual(info["func_code"], 0x03)
        self.assertEqual(info["slave_id"], 1)
        self.assertEqual(info["start_addr"], 0x006B)
        self.assertEqual(info["end_addr"], 0x006D)

    def test_extract_write_single_request_tcp(self):
        """TCP 写单个寄存器请求提取"""
        raw = "00010000000601060001000a"
        info = ModbusMessageParser.extract_request_info(raw, is_tcp=True)
        self.assertIsNotNone(info)
        self.assertEqual(info["func_code"], 0x06)
        self.assertEqual(info["start_addr"], 0x0001)
        self.assertEqual(info["end_addr"], 0x0001)

    def test_extract_write_multiple_request_tcp(self):
        """TCP 写多个寄存器请求提取"""
        raw = "00010000000b011000010002040a010200"
        info = ModbusMessageParser.extract_request_info(raw, is_tcp=True)
        self.assertIsNotNone(info)
        self.assertEqual(info["func_code"], 0x10)
        self.assertEqual(info["start_addr"], 0x0001)
        self.assertEqual(info["end_addr"], 0x0002)

    def test_extract_write_multiple_response_returns_none(self):
        """TCP 写多个寄存器响应不提取（非请求）"""
        raw = "000100000006011000010002"
        info = ModbusMessageParser.extract_request_info(raw, is_tcp=True)
        self.assertIsNone(info)

    def test_extract_invalid_returns_none(self):
        """无效数据返回 None"""
        self.assertIsNone(ModbusMessageParser.extract_request_info(""))
        self.assertIsNone(ModbusMessageParser.extract_request_info("ZZ"))
        self.assertIsNone(ModbusMessageParser.extract_request_info("0001"))

    def test_extract_rtu_request(self):
        """RTU 读请求提取"""
        raw = "0103006b0003a4b5"
        info = ModbusMessageParser.extract_request_info(raw, is_tcp=False)
        self.assertIsNotNone(info)
        self.assertEqual(info["func_code"], 0x03)
        self.assertEqual(info["start_addr"], 0x006B)


if __name__ == '__main__':
    unittest.main()
