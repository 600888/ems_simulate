"""
DLT645 和 IEC104 报文解析器单元测试
"""

import pytest
from unittest.mock import patch, MagicMock
from src.device.core.message.message_parser import (
    DLT645MessageParser,
    IEC104MessageParser,
)


# =============================================================================
# DLT645MessageParser 测试
# =============================================================================


class TestDLT645MessageParser:
    """DLT645 报文解析器测试"""

    def _build_dlt645_frame(self, addr_bytes, ctrl, data_bytes):
        """构建 DLT645 帧
        
        Args:
            addr_bytes: 地址字段（6字节，低字节在前）
            ctrl: 控制码
            data_bytes: 数据域（已加 0x33）
        """
        frame = bytearray()
        frame.append(0x68)                      # 帧头
        frame.extend(addr_bytes)                 # 地址
        frame.append(0x68)                       # 帧头2
        frame.append(ctrl)                       # 控制码
        frame.append(len(data_bytes))            # 数据域长度
        frame.extend(data_bytes)                 # 数据域
        cs = sum(frame) & 0xFF                   # 校验和
        frame.append(cs)
        frame.append(0x16)                       # 帧尾
        return frame.hex()

    def _di_to_data_bytes(self, di_hex_str):
        """将 DI 十六进制字符串转换为 DLT645 数据域格式（加 0x33，低字节在前）"""
        # di_hex_str 如 "02010100" → 字节 [02, 01, 01, 00]，反转后 [00, 01, 01, 02]，加0x33
        di_bytes = bytes.fromhex(di_hex_str)
        reversed_bytes = bytes(reversed(di_bytes))
        return bytes([(b + 0x33) & 0xFF for b in reversed_bytes])

    def test_read_request(self):
        """测试读数据请求帧解析"""
        addr = bytes([0x12, 0x34, 0x56, 0x78, 0x90, 0x12])
        di_data = self._di_to_data_bytes("02010100")  # A相电压
        raw_hex = self._build_dlt645_frame(addr, 0x11, di_data)

        with patch.object(DLT645MessageParser, '_get_di_name', return_value="A相电压"):
            result = DLT645MessageParser.parse(raw_hex)

        assert "读数据" in result
        assert "A相电压" in result
        assert "02010100" in result.upper()
        assert "129078563412" in result  # 地址反转

    def test_read_response_normal(self):
        """测试读数据正常响应帧解析"""
        addr = bytes([0x12, 0x34, 0x56, 0x78, 0x90, 0x12])
        # 响应数据域: DI(4字节) + 数据值
        di_data = self._di_to_data_bytes("02010100")
        # 数据值 220.1V → BCD 002201 加 0x33
        value_data = bytes([0x34, 0x55, 0x35, 0x33])  # 示例值
        data_field = di_data + value_data
        raw_hex = self._build_dlt645_frame(addr, 0x91, data_field)

        with patch.object(DLT645MessageParser, '_get_di_name', return_value="A相电压"):
            result = DLT645MessageParser.parse(raw_hex)

        assert "正常响应" in result
        assert "A相电压" in result

    def test_read_response_error(self):
        """测试读数据异常响应帧解析"""
        addr = bytes([0x12, 0x34, 0x56, 0x78, 0x90, 0x12])
        # 异常响应: 错误码 0x02(无请求数据) 加 0x33 = 0x35
        error_data = bytes([0x35])
        raw_hex = self._build_dlt645_frame(addr, 0xD1, error_data)

        result = DLT645MessageParser.parse(raw_hex)

        assert "异常响应" in result
        assert "无请求数据" in result

    def test_write_request(self):
        """测试写数据请求帧解析"""
        addr = bytes([0x12, 0x34, 0x56, 0x78, 0x90, 0x12])
        di_data = self._di_to_data_bytes("04000101")
        # 写入数据还包含密码和值
        extra = bytes([0x33, 0x33, 0x33, 0x33])  # 密码占位
        data_field = di_data + extra
        raw_hex = self._build_dlt645_frame(addr, 0x14, data_field)

        with patch.object(DLT645MessageParser, '_get_di_name', return_value=""):
            result = DLT645MessageParser.parse(raw_hex)

        assert "写数据" in result
        assert "04000101" in result.upper()

    def test_write_response_normal(self):
        """测试写数据正常响应"""
        addr = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])
        di_data = self._di_to_data_bytes("04000101")
        raw_hex = self._build_dlt645_frame(addr, 0x94, di_data)

        with patch.object(DLT645MessageParser, '_get_di_name', return_value=""):
            result = DLT645MessageParser.parse(raw_hex)

        assert "写数据 正常响应" in result

    def test_empty_data(self):
        """测试空数据"""
        assert DLT645MessageParser.parse("") == ""
        assert DLT645MessageParser.parse("  ") == ""

    def test_too_short_frame(self):
        """测试过短的帧"""
        assert DLT645MessageParser.parse("6800000000") == ""

    def test_invalid_hex(self):
        """测试无效十六进制"""
        assert DLT645MessageParser.parse("ZZZZ") == ""

    def test_invalid_frame_header(self):
        """测试无效帧头"""
        # 不以 0x68 开始
        assert DLT645MessageParser.parse("AA" * 20) == ""

    def test_di_name_lookup_with_library(self):
        """测试通过 dlt645 库查找 DI 名称"""
        mock_item = MagicMock()
        mock_item.name = "B相电压"
        
        with patch('dlt645.model.data.data_handler.get_data_item', return_value=mock_item):
            result = DLT645MessageParser._get_di_name(0x02010200)
            assert result == "B相电压"

    def test_di_name_lookup_not_found(self):
        """测试 DI 查找失败"""
        with patch('dlt645.model.data.data_handler.get_data_item', return_value=None):
            result = DLT645MessageParser._get_di_name(0xFFFFFFFF)
            assert result == ""

    def test_di_name_lookup_exception(self):
        """测试 DI 查找异常"""
        with patch('dlt645.model.data.data_handler.get_data_item', side_effect=Exception("import error")):
            result = DLT645MessageParser._get_di_name(0x02010100)
            assert result == ""

    def test_di_name_lookup_list_result(self):
        """测试 DI 返回列表"""
        mock_item1 = MagicMock()
        mock_item1.name = "组合有功总电能"
        mock_item2 = MagicMock()
        mock_item2.name = "组合有功费率1电能"
        
        with patch('dlt645.model.data.data_handler.get_data_item', return_value=[mock_item1, mock_item2]):
            result = DLT645MessageParser._get_di_name(0x00010000)
            assert result == "组合有功总电能"


# =============================================================================
# IEC104MessageParser 测试
# =============================================================================


class TestIEC104MessageParser:
    """IEC104 报文解析器测试"""

    def test_u_frame_startdt_act(self):
        """测试 U 帧 STARTDT_ACT"""
        # 68 04 07 00 00 00
        raw_hex = "680407000000"
        result = IEC104MessageParser.parse(raw_hex)
        assert "U帧" in result
        assert "STARTDT_ACT" in result

    def test_u_frame_startdt_con(self):
        """测试 U 帧 STARTDT_CON"""
        # 68 04 0B 00 00 00
        raw_hex = "68040B000000"
        result = IEC104MessageParser.parse(raw_hex)
        assert "U帧" in result
        assert "STARTDT_CON" in result

    def test_u_frame_stopdt_act(self):
        """测试 U 帧 STOPDT_ACT"""
        # 68 04 13 00 00 00
        raw_hex = "680413000000"
        result = IEC104MessageParser.parse(raw_hex)
        assert "U帧" in result
        assert "STOPDT_ACT" in result

    def test_u_frame_stopdt_con(self):
        """测试 U 帧 STOPDT_CON"""
        # 68 04 23 00 00 00
        raw_hex = "680423000000"
        result = IEC104MessageParser.parse(raw_hex)
        assert "U帧" in result
        assert "STOPDT_CON" in result

    def test_u_frame_testfr_act(self):
        """测试 U 帧 TESTFR_ACT"""
        # 68 04 43 00 00 00
        raw_hex = "680443000000"
        result = IEC104MessageParser.parse(raw_hex)
        assert "U帧" in result
        assert "TESTFR_ACT" in result

    def test_u_frame_testfr_con(self):
        """测试 U 帧 TESTFR_CON"""
        # 68 04 83 00 00 00
        raw_hex = "680483000000"
        result = IEC104MessageParser.parse(raw_hex)
        assert "U帧" in result
        assert "TESTFR_CON" in result

    def test_s_frame(self):
        """测试 S 帧"""
        # 68 04 01 00 02 00  → recv_seq = (0x02 | 0x00<<8) >> 1 = 1
        raw_hex = "680401000200"
        result = IEC104MessageParser.parse(raw_hex)
        assert "S帧" in result
        assert "确认接收序号" in result

    def test_i_frame_short_float(self):
        """测试 I 帧 - 短浮点遥测 M_ME_NC_1 (TypeID=13)"""
        # I帧: 68 LEN 00 00 00 00 + ASDU
        # ASDU: TypeID=0D, VSQ=01, COT=03 00, CommonAddr=01 00, IOA=0B 00 00, Value...
        raw_hex = "68" + "12" + "00000000" + "0D" + "01" + "0300" + "0100" + "0B0000" + "00004842" + "00"
        result = IEC104MessageParser.parse(raw_hex)
        assert "I帧" in result
        assert "短浮点遥测" in result
        assert "IOA:11" in result
        assert "突发" in result

    def test_i_frame_general_interrogation(self):
        """测试 I 帧 - 总召唤 C_IC_NA_1 (TypeID=100)"""
        # ASDU: TypeID=64, VSQ=01, COT=06 00, CommonAddr=01 00, IOA=00 00 00, QOI=14
        raw_hex = "68" + "0E" + "00000000" + "64" + "01" + "0600" + "0100" + "000000" + "14"
        result = IEC104MessageParser.parse(raw_hex)
        assert "I帧" in result
        assert "总召唤" in result
        assert "激活" in result

    def test_i_frame_single_point(self):
        """测试 I 帧 - 单点遥信 M_SP_NA_1 (TypeID=1)"""
        # ASDU: TypeID=01, VSQ=03(3个信息体), COT=14 00(响应总召唤), CommonAddr=01 00
        raw_hex = "68" + "12" + "02000200" + "01" + "03" + "1400" + "0100" + "010000" + "01" + "020000" + "00"
        result = IEC104MessageParser.parse(raw_hex)
        assert "I帧" in result
        assert "单点遥信" in result
        assert "3个" in result
        assert "响应总召唤" in result

    def test_i_frame_double_command(self):
        """测试 I 帧 - 双点遥控 C_DC_NA_1 (TypeID=46)"""
        # ASDU: TypeID=2E, VSQ=01, COT=06 00, CommonAddr=01 00, IOA=01 00 00, QQ
        raw_hex = "68" + "0E" + "04000200" + "2E" + "01" + "0600" + "0100" + "010000" + "02"
        result = IEC104MessageParser.parse(raw_hex)
        assert "I帧" in result
        assert "双点遥控" in result

    def test_i_frame_negative_confirm(self):
        """测试 I 帧 - 否定确认"""
        # COT 第7位 (D6) = 1 表示否定
        # ASDU: TypeID=2E, VSQ=01, COT=47 00(激活确认+否定), CommonAddr=01 00
        raw_hex = "68" + "0E" + "04000200" + "2E" + "01" + "4700" + "0100" + "010000" + "02"
        result = IEC104MessageParser.parse(raw_hex)
        assert "否定" in result

    def test_empty_data(self):
        """测试空数据"""
        assert IEC104MessageParser.parse("") == ""

    def test_too_short(self):
        """测试过短的帧"""
        assert IEC104MessageParser.parse("6804") == ""

    def test_invalid_hex(self):
        """测试无效十六进制"""
        assert IEC104MessageParser.parse("ZZZZ") == ""

    def test_invalid_start_byte(self):
        """测试无效启动字节"""
        assert IEC104MessageParser.parse("AA0407000000") == ""

    def test_i_frame_clock_sync(self):
        """测试 I 帧 - 时钟同步 C_CS_NA_1 (TypeID=103)"""
        # ASDU: TypeID=67, VSQ=01, COT=06 00, CommonAddr=01 00, IOA=00 00 00, CP56...
        raw_hex = "68" + "14" + "06000400" + "67" + "01" + "0600" + "0100" + "000000" + "00000000000000"
        result = IEC104MessageParser.parse(raw_hex)
        assert "I帧" in result
        assert "时钟同步" in result

    def test_hex_with_spaces(self):
        """测试带空格的十六进制字符串"""
        raw_hex = "68 04 07 00 00 00"
        result = IEC104MessageParser.parse(raw_hex)
        assert "U帧" in result
        assert "STARTDT_ACT" in result
