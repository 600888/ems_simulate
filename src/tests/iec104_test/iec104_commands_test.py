"""
IEC104 命令类型端到端测试
测试客户端发送 → 服务端接收的完整链路，验证每种命令类型支持。
使用真实 c104 库，不 mock。
"""

import asyncio
import unittest
import c104

from src.proto.iec104.iec104server import IEC104Server
from src.proto.iec104.iec104client import IEC104Client


SERVER_PORT = 14204
COMMON_ADDR = 1


class _ServerCtx:
    """管理 IEC104 服务端的生命周期"""
    def __init__(self, port: int = SERVER_PORT):
        self.server = IEC104Server(ip="127.0.0.1", port=port, common_address=COMMON_ADDR)
        self.server.start()

    def add_cmd_point(self, io_address: int, point_type: c104.Type):
        self.server.add_command_point(io_address=io_address, point_type=point_type)

    def get_point_value(self, io_address: int, frame_type: int):
        return self.server.get_point_value(io_address=io_address, frame_type=frame_type)

    def stop(self):
        self.server.stop()


class _ClientCtx:
    """管理 IEC104 客户端的生命周期"""
    def __init__(self, port: int = SERVER_PORT):
        self.client = IEC104Client(ip="127.0.0.1", port=port, common_address=COMMON_ADDR)

    async def connect(self):
        return await self.client.connect()

    def add_point(self, io_address: int, point_type: c104.Type):
        return self.client.add_point(io_address=io_address, point_type=point_type)

    def write_point(self, io_address: int, value, frame_type: int = 0) -> bool:
        return self.client.write_point(io_address=io_address, value=value, frame_type=frame_type)

    def disconnect(self):
        self.client.disconnect()


class TestIEC104Commands(unittest.TestCase):
    """逐种命令类型测试客户端→服务端收发"""

    @classmethod
    def setUpClass(cls):
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)

    @classmethod
    def tearDownClass(cls):
        cls.loop.close()

    def _run_async(self, coro):
        return self.loop.run_until_complete(coro)

    # ---- 辅助方法 ----

    def _make_pair(self, io_address: int, point_type: c104.Type):
        """建立 服务端+客户端 并添加指定类型的命令点"""
        svr = _ServerCtx()
        svr.add_cmd_point(io_address=io_address, point_type=point_type)
        cli = _ClientCtx()
        ok = self._run_async(cli.connect())
        self.assertTrue(ok, "客户端连接失败")
        cli.add_point(io_address=io_address, point_type=point_type)
        # 等待初始化完成
        self._run_async(asyncio.sleep(0.5))
        return svr, cli

    # ===== 单点遥控 C_SC_NA_1 =====

    def test_single_command(self):
        """C_SC_NA_1: 客户端发送 SingleCmd(ON) → 服务端收到"""
        IOA = 101
        svr, cli = self._make_pair(IOA, c104.Type.C_SC_NA_1)
        try:
            ret = cli.write_point(IOA, True, frame_type=2)
            self.assertTrue(ret, "单点遥控写入失败")
            self._run_async(asyncio.sleep(0.3))
            val = svr.get_point_value(IOA, frame_type=2)
            self.assertEqual(val, True, "服务端未收到单点遥控 ON")
        finally:
            cli.disconnect()
            svr.stop()

    def test_single_command_off(self):
        """C_SC_NA_1: 客户端发送 SingleCmd(OFF) → 服务端收到"""
        IOA = 102
        svr, cli = self._make_pair(IOA, c104.Type.C_SC_NA_1)
        try:
            ret = cli.write_point(IOA, False, frame_type=2)
            self.assertTrue(ret, "单点遥控写入失败")
            self._run_async(asyncio.sleep(0.3))
            val = svr.get_point_value(IOA, frame_type=2)
            self.assertEqual(val, False, "服务端未收到单点遥控 OFF")
        finally:
            cli.disconnect()
            svr.stop()

    # ===== 双点遥控 C_DC_TA_1 =====

    def test_double_command_on(self):
        """C_DC_TA_1: 客户端发送 DoubleCmd(ON) → 服务端收到"""
        IOA = 201
        svr, cli = self._make_pair(IOA, c104.Type.C_DC_TA_1)
        try:
            ret = cli.write_point(IOA, True, frame_type=2)
            self.assertTrue(ret, "双点遥控写入失败")
            self._run_async(asyncio.sleep(0.3))
            val = svr.get_point_value(IOA, frame_type=2)
            self.assertEqual(val, True, "服务端未收到双点遥控 ON")
        finally:
            cli.disconnect()
            svr.stop()

    # ===== 步调节命令 C_RC_NA_1 =====

    def test_step_command_higher(self):
        """C_RC_NA_1: 客户端发送 Step(HIGHER) → 服务端收到"""
        IOA = 301
        svr, cli = self._make_pair(IOA, c104.Type.C_RC_NA_1)
        try:
            ret = cli.client.send_command(IOA, c104.Step.HIGHER)
            self.assertTrue(ret, "步命令发送失败")
            self._run_async(asyncio.sleep(0.3))
            val = svr.get_point_value(IOA, frame_type=2)
            self.assertIsNotNone(val, "服务端步命令值为空")
        finally:
            cli.disconnect()
            svr.stop()

    def test_step_command_lower(self):
        """C_RC_NA_1: 客户端发送 Step(LOWER) → 服务端收到"""
        IOA = 302
        svr, cli = self._make_pair(IOA, c104.Type.C_RC_NA_1)
        try:
            ret = cli.client.send_command(IOA, c104.Step.LOWER)
            self.assertTrue(ret, "步命令发送失败")
            self._run_async(asyncio.sleep(0.3))
            val = svr.get_point_value(IOA, frame_type=2)
            self.assertIsNotNone(val, "服务端步命令值为空")
        finally:
            cli.disconnect()
            svr.stop()

    # ===== 归一化设定值 C_SE_NA_1 =====

    def test_setpoint_normalized(self):
        """C_SE_NA_1: 客户端发送 NormalizedFloat(1.0) → 服务端收到 ≈1.0"""
        IOA = 401
        svr, cli = self._make_pair(IOA, c104.Type.C_SE_NA_1)
        try:
            ret = cli.write_point(IOA, c104.NormalizedFloat(1.0), frame_type=3)
            self.assertTrue(ret, "归一化设定值写入失败")
            self._run_async(asyncio.sleep(0.3))
            val = svr.get_point_value(IOA, frame_type=3)
            self.assertAlmostEqual(float(val), 1.0, places=4,
                                   msg="服务端归一化值偏差过大")
        finally:
            cli.disconnect()
            svr.stop()

    # ===== 标度化设定值 C_SE_NB_1 =====

    def test_setpoint_scaled(self):
        """C_SE_NB_1: 客户端发送 ShortCmd(100) → 服务端收到 ≈100"""
        IOA = 501
        svr, cli = self._make_pair(IOA, c104.Type.C_SE_NB_1)
        try:
            point = cli.client.station.get_point(IOA)
            self.assertIsNotNone(point, "客户端未找到点")
            point.info = c104.ScaledCmd(target=c104.Int16(100), qualifier=c104.UInt7(0))
            ret = point.transmit(cause=c104.Cot.ACTIVATION)
            self.assertTrue(ret, "标度化设定值 transmit 失败")
            self._run_async(asyncio.sleep(0.3))
            val = svr.get_point_value(IOA, frame_type=3)
            self.assertAlmostEqual(float(val), 100.0, delta=1.5,
                                   msg="服务端标度化值偏差过大")
        finally:
            cli.disconnect()
            svr.stop()

    # ===== 短浮点设定值 C_SE_NC_1 =====

    def test_setpoint_short_float(self):
        """C_SE_NC_1: 客户端发送 float(12.34) → 服务端收到 ≈12.34"""
        IOA = 601
        svr, cli = self._make_pair(IOA, c104.Type.C_SE_NC_1)
        try:
            ret = cli.write_point(IOA, 12.34, frame_type=3)
            self.assertTrue(ret, "短浮点设定值写入失败")
            self._run_async(asyncio.sleep(0.3))
            val = svr.get_point_value(IOA, frame_type=3)
            self.assertAlmostEqual(float(val), 12.34, places=4,
                                   msg="服务端短浮点值偏差过大")
        finally:
            cli.disconnect()
            svr.stop()


if __name__ == "__main__":
    unittest.main()
