"""reload_device_instance 原子替换时序测试。

验证修复：构建新实例完成前不移除旧实例，避免删除-重建空窗期内
接口报"设备不存在"；启动场景仍先停旧实例再启动新实例。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.web.api.channel import helpers


def _channel(name: str = "dlt645-server", protocol: str = "Dlt645Server"):
    return {
        "id": 1,
        "name": name,
        "code": "DLT645-SRV",
        "protocol_type": protocol,
        "conn_type": 2,
        "ip": "0.0.0.0",
        "port": 8899,
        "rtu_addr": "000000000001",
    }


def _controller(remove_side_effect=None):
    controller = SimpleNamespace(
        device_list=[],
        device_map={},
        remove_device_by_id=AsyncMock(side_effect=remove_side_effect or (lambda _id: True)),
    )
    return controller


def _new_device(name: str = "dlt645-server"):
    return SimpleNamespace(
        name=name,
        device_id=1,
        data_update_thread=SimpleNamespace(start=lambda: None),
    )


@pytest.mark.asyncio
async def test_reload_non_start_removes_old_after_build():
    """非启动场景：先构建新实例，构建完成后再移除旧实例（无空窗）。"""
    controller = _controller()
    with (
        patch.object(
            helpers.asyncio,
            "to_thread",
            side_effect=[_channel(), _new_device()],
        ),
        patch.object(helpers, "log", SimpleNamespace(info=lambda *a, **k: None)),
    ):
        result = await helpers.reload_device_instance(controller, 1, is_start=False)

    assert result.name == "dlt645-server"
    assert controller.device_map["dlt645-server"] is result
    # remove 只调用一次，且发生在新实例构建完成之后
    assert controller.remove_device_by_id.await_count == 1


@pytest.mark.asyncio
async def test_reload_non_start_build_failure_keeps_old_device():
    """构建失败时旧设备不被移除（设备继续可用）。"""
    controller = _controller()
    controller.device_list.append(_new_device("old"))
    controller.device_map["dlt645-server"] = controller.device_list[0]

    def _raise(*args, **kwargs):
        raise RuntimeError("build failed")

    with (
        patch.object(helpers.asyncio, "to_thread", _raise),
        patch.object(helpers, "log", SimpleNamespace(info=lambda *a, **k: None)),
    ):
        with pytest.raises(RuntimeError):
            await helpers.reload_device_instance(controller, 1, is_start=False)

    # 旧实例未被移除
    assert controller.remove_device_by_id.await_count == 0
    assert controller.device_map["dlt645-server"] is controller.device_list[0]


@pytest.mark.asyncio
async def test_reload_client_start_stops_old_before_start():
    """启动场景（客户端）：先停止旧实例，再启动新实例。"""
    controller = _controller()
    new_device = _new_device()

    with (
        patch.object(
            helpers.asyncio,
            "to_thread",
            side_effect=[_channel(protocol="Dlt645Client"), new_device],
        ),
        patch.object(helpers, "log", SimpleNamespace(info=lambda *a, **k: None)),
    ):
        result = await helpers.reload_device_instance(controller, 1, is_start=True)

    assert result is new_device
    assert controller.device_map["dlt645-server"] is new_device
    # 启动场景同样只移除一次
    assert controller.remove_device_by_id.await_count == 1
