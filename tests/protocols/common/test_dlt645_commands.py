"""DL/T645 特殊命令（send_command）单元测试。

覆盖主站（Dlt645Client）与从站（Dlt645Server）两侧：
- 参数校验（地址 12 位、密码 8 位数字）
- 各命令成功路径与失败路径
- 未初始化 / 未知命令

dlt645 3.0.0 起 send_command 为异步接口，测试通过 asyncio.run() 驱动。
"""

import asyncio
from types import SimpleNamespace

from src.device.protocol.dlt645_handler import DLT645ClientHandler, DLT645ServerHandler


class _FakeClient:
    """模拟 dlt645 库 AsyncMeterClientService 的命令接口（异步）。"""

    def __init__(self):
        self.read_address_called = False
        self.write_address_addr = None
        self.last_password = None

    async def read_address(self):
        self.read_address_called = True
        return SimpleNamespace(di=0, name="通讯地址", value="123456789012", unit="", update_time=None)

    async def write_address(self, addr):
        self.write_address_addr = bytes(addr).hex()
        return SimpleNamespace(di=0, name="写地址", value=None, unit="", update_time=None)

    async def broadcast_time_sync(self, dt):
        return True

    async def freeze(self, **kwargs):
        return SimpleNamespace(di=0, name="广播冻结", value=None, unit="", update_time=None)

    async def change_baud_rate(self, baud):
        return baud

    async def change_password(self, old, new):
        return old != new  # 新旧密码相同视为失败

    async def clear_demand(self, di, password):
        self.last_password = password
        return di

    async def clear_meter(self, password):
        self.last_password = password
        return password

    async def clear_event(self, password, di=None):
        self.last_password = password
        return di


class _FakeServer:
    """模拟 dlt645 库 AsyncMeterServerService 的命令接口（本地状态操作，同步）。"""

    def __init__(self):
        from dlt645.model.data.data_handler import clone_data_map

        self.address = None
        self.time = None
        self.password = None
        self.reset_energy = 0
        self.reset_events = 0
        # 与真实服务端一致：每个实例持有独立的内部数据映射
        self.data_map = clone_data_map()

    def set_address(self, address):
        self.address = address

    def set_time(self, data):
        self.time = bytes(data).hex()

    def set_password(self, password):
        self.password = password

    def _reset_energy_data(self):
        self.reset_energy += 1

    def _reset_event_records(self, di):
        self.reset_events += 1


def _client_handler():
    handler = DLT645ClientHandler()
    handler._client = _FakeClient()
    return handler


def _server_handler():
    handler = DLT645ServerHandler()
    handler._server = _FakeServer()
    return handler


def _run_command(handler, command, params=None) -> dict:
    """在临时事件循环中执行异步 send_command。"""
    return asyncio.run(handler.send_command(command, params))


# ===== 客户端（主站）命令 =====


def test_client_read_address():
    handler = _client_handler()
    result = _run_command(handler, "read_address")
    assert result["ok"] is True
    assert result["detail"]["value"] == "123456789012"
    assert handler._client.read_address_called is True


def test_client_write_address_validates_length():
    handler = _client_handler()
    assert _run_command(handler, "write_address", {"address": "123"})["ok"] is False
    assert _run_command(handler, "write_address", {"address": "abcdefghijkl"})["ok"] is False
    result = _run_command(handler, "write_address", {"address": "123456789012"})
    assert result["ok"] is True
    assert handler._client.write_address_addr is not None


def test_client_broadcast_time_sync():
    handler = _client_handler()
    result = _run_command(handler, "broadcast_time_sync")
    assert result["ok"] is True
    result = _run_command(handler, "broadcast_time_sync", {"datetime": "2026-01-02T03:04:05"})
    assert result["ok"] is True
    assert "2026-01-02 03:04:05" in result["message"]


def test_client_freeze():
    handler = _client_handler()
    result = _run_command(handler, "freeze")
    assert result["ok"] is True
    assert "冻结" in result["message"]


def test_client_change_baud_rate():
    handler = _client_handler()
    assert _run_command(handler, "change_baud_rate", {"baud": 9600})["ok"] is True


def test_client_change_password_validates_format():
    handler = _client_handler()
    assert _run_command(handler, "change_password", {"old_password": "00000000", "new_password": "abc"})["ok"] is False
    result = _run_command(handler, "change_password", {"old_password": "00000000", "new_password": "12345678"})
    assert result["ok"] is True


def test_client_clear_commands_validate_password():
    handler = _client_handler()
    for command in ("clear_demand", "clear_meter", "clear_event"):
        assert _run_command(handler, command, {"password": "123"})["ok"] is False
        result = _run_command(handler, command, {"password": "00000000"})
        assert result["ok"] is True, command


def test_client_uninitialized_and_unknown_command():
    handler = DLT645ClientHandler()
    assert _run_command(handler, "read_address")["ok"] is False
    handler._client = _FakeClient()
    assert _run_command(handler, "no_such_command")["ok"] is False


# ===== 服务端（从站）命令 =====


def test_server_write_address_validates_length():
    handler = _server_handler()
    assert _run_command(handler, "write_address", {"address": "abc"})["ok"] is False
    result = _run_command(handler, "write_address", {"address": "123456789012"})
    assert result["ok"] is True
    assert handler._server.address == "123456789012"


def test_server_set_time():
    handler = _server_handler()
    result = _run_command(handler, "set_time", {"datetime": "2026-01-02T03:04:05"})
    assert result["ok"] is True
    assert "2026-01-02 03:04:05" in result["message"]
    assert handler._server.time is not None


def test_server_change_password_validates_format():
    handler = _server_handler()
    assert _run_command(handler, "change_password", {"password": "abc"})["ok"] is False
    assert _run_command(handler, "change_password", {"password": "00000000"})["ok"] is True
    assert handler._server.password is not None


def test_server_clear_commands():
    handler = _server_handler()
    assert _run_command(handler, "clear_meter")["ok"] is True
    assert handler._server.reset_energy == 1
    assert handler._server.reset_events == 1
    assert _run_command(handler, "clear_event")["ok"] is True
    assert handler._server.reset_events == 2
    assert _run_command(handler, "clear_demand")["ok"] is True


def test_server_uninitialized_and_unknown_command():
    handler = DLT645ServerHandler()
    assert _run_command(handler, "write_address", {"address": "123456789012"})["ok"] is False
    handler._server = _FakeServer()
    assert _run_command(handler, "no_such_command")["ok"] is False


# ===== 服务端（从站）写入值 =====


def _restore_di(di: int) -> None:
    """恢复 DIMap 中该数据标识的原值，避免污染其他测试。"""
    from dlt645.model.data.data_handler import get_data_item, set_data_item

    item = get_data_item(di)
    if isinstance(item, list):
        set_data_item(di, [child.value for child in item])
    else:
        set_data_item(di, item.value)


def test_server_write_value_validates_params():
    handler = _server_handler()
    assert _run_command(handler, "write_value", {})["ok"] is False
    assert _run_command(handler, "write_value", {"di": "abc", "value": "1"})["ok"] is False
    assert _run_command(handler, "write_value", {"di": "0xFFFFFFFF", "value": "1"})["ok"] is False
    assert _run_command(handler, "write_value", {"di": "0x00000000", "value": "abc"})["ok"] is False


def test_server_write_value_single_number():
    handler = _server_handler()
    try:
        result = _run_command(handler, "write_value", {"di": "0x00000000", "value": "123.45"})
        assert result["ok"] is True
        assert result["detail"]["di"] == "0x00000000"
        assert result["detail"]["value"] == 123.45
    finally:
        _restore_di(0x00000000)


def test_server_write_value_rejects_out_of_range():
    handler = _server_handler()
    result = _run_command(handler, "write_value", {"di": "0x00000000", "value": "999999999"})
    assert result["ok"] is False


def test_server_write_value_list():
    from dlt645.model.data.define import DIMap

    # 0x04010000 参变量时段表：子项接受数值列表
    item = DIMap.get(0x04010000)
    assert item is not None and isinstance(item, list)
    n = len(item)
    handler = _server_handler()
    values = ", ".join("1.0" for _ in range(n))
    try:
        result = _run_command(handler, "write_value", {"di": "0x04010000", "value": values})
        assert result["ok"] is True
        assert len(result["detail"]["value"]) == n
        assert result["detail"]["value"] == [1.0] * n
    finally:
        _restore_di(0x04010000)


def test_server_write_value_list_bad_number():
    handler = _server_handler()
    result = _run_command(handler, "write_value", {"di": "0x04010000", "value": "1, abc"})
    assert result["ok"] is False
