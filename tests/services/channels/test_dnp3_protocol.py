"""DNP3 协议接入单元测试。

覆盖：
- 通道 protocol_type=5 在 get_protocol_type 中正确映射为 Dnp3Server / Dnp3Client
- 前端协议常量 DISABLED（后端不依赖前端，仅测后端映射）
- Dnp3Server 封装：测点注册、读写、统一接口
- DNP3 报文解析器：解析 pydnp3_pure 生成的真实链路帧
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.data.service.channel_service import ChannelService
from src.device.core.message.parsers.dnp3 import parse_dnp3
from src.enums.modbus_def import ProtocolType
from src.proto.dnp3.dnp3_server import Dnp3Server


def _channel(protocol_type: int, conn_type: int) -> dict:
    return {
        "id": 1,
        "device_id": 10,
        "code": "DNP3",
        "name": "DNP3设备",
        "protocol_type": protocol_type,
        "conn_type": conn_type,
        "ip": "0.0.0.0",
        "port": 20000,
    }


def test_dnp3_protocol_type_mapping():
    # 客户端（Master）：conn_type=1
    assert ChannelService.get_protocol_type(_channel(5, 1)) == ProtocolType.Dnp3Client
    # 服务端（Outstation）：conn_type=2
    assert ChannelService.get_protocol_type(_channel(5, 2)) == ProtocolType.Dnp3Server


def test_dnp3_server_point_registration_and_rw():
    srv = Dnp3Server()
    # 注册四类测点
    srv.add_analog_input(0, deadband=0.1)
    srv.add_binary_input(1)
    srv.add_binary_output(2)
    srv.add_analog_output(3)

    # 写入 / 读取遥测、遥信
    srv.update_analog_input(0, 72.5)
    srv.update_binary_input(1, True)
    assert srv.get_analog_input(0) == 72.5
    assert srv.get_binary_input(1) is True

    # 统一读写接口（frame_type: 0=遥测,1=遥信,2=遥控,3=遥调）
    assert srv.get_point_value(0, 0) == 72.5
    assert srv.get_point_value(1, 1) is True
    srv.set_point_value(3, 99.9, 3)
    assert srv.get_point_value(3, 3) == 99.9


def test_dnp3_server_command_callback():
    srv = Dnp3Server()
    srv.add_binary_output(2)
    received: list = []

    def on_cmd(index, value, frame_type):
        received.append((index, value, frame_type))

    srv.set_on_command_callback(on_cmd)
    # 直接调用封装的通知逻辑（内部 _notify_command 供回调用）
    srv._notify_command(2, 2, 1)
    assert received == [(2, 1, 2)]


def test_dnp3_parser_real_frame():
    """用 pydnp3_pure 生成的真实 DNP3 链路帧验证解析器。"""
    from pydnp3_pure.link.frame import LinkFrame

    frame = LinkFrame.create(destination=1, source=10, primary=True, function=3, user_data=b"\xc0\x01")
    raw = frame.serialize()
    result = parse_dnp3(raw)
    assert result["protocol"] == "DNP3"
    assert result["valid"] is True  # CRC 校验通过
    # 头 CRC 与数据块 CRC 均通过
    validation = {v["name"]: v["passed"] for v in result["validation"]}
    assert validation.get("链路头CRC") is True
    assert validation.get("数据块CRC") is True
    # 应用层解析出 Read 请求（功能码 01）
    fc_field = next((f for f in result["fields"] if f["key"] == "function_code"), None)
    assert fc_field is not None and "Read" in str(fc_field["display_value"])
    assert "Read" in result["summary"]


@pytest.mark.parametrize(
    "protocol_type",
    [ProtocolType.Dnp3Server, ProtocolType.Dnp3Client],
)
def test_dnp3_device_builds(protocol_type):
    """DNP3 设备可通过 makeGeneralDevice 成功构建（回归：防止 abstract class 实例化错误）。"""
    from src.device.factory.general_device_builder import GeneralDeviceBuilder
    from src.device.types.general_device import GeneralDevice

    builder = GeneralDeviceBuilder(channel_id=1, device=GeneralDevice())
    builder.setDeviceName(name="dnp3-build")
    builder.setDeviceId(1)
    device = builder.makeGeneralDevice(
        device_id=1,
        device_name="dnp3-build",
        protocol_type=protocol_type,
        is_start=False,
    )
    assert device is not None
    assert device.protocol_type == protocol_type
    # handler 必须是 DNP3 对应子类且可实例化
    from src.device.protocol.dnp3_handler import DNP3ClientHandler, DNP3ServerHandler

    expected = DNP3ServerHandler if protocol_type == ProtocolType.Dnp3Server else DNP3ClientHandler
    assert isinstance(device.protocol_handler, expected)


def _dnp3_item(reg_addr="9"):
    return {
        "rtu_addr": 1,
        "reg_addr": reg_addr,
        "name": "T",
        "code": "X",
        "func_code": 3,
        "decode_code": "0x41",
        "max_limit": 100,
        "min_limit": 0,
        "add_coe": 0.0,
        "mul_coe": 0.1,
        "command_type": 0,
        "bit": 0,
    }


@pytest.mark.parametrize("protocol_type", [ProtocolType.Dnp3Server, ProtocolType.Dnp3Client])
def test_dnp3_service_create_points(protocol_type):
    """DNP3 测点经 4 个 Service 创建正确（回归：防止导入后测点不加载）。"""
    from src.data.service.yc_service import YcService
    from src.data.service.yk_service import YkService
    from src.data.service.yt_service import YtService
    from src.data.service.yx_service import YxService

    yc = YcService._create_point(_dnp3_item(), protocol_type)
    yx = YxService._create_point(_dnp3_item(), protocol_type)
    yk = YkService._create_point(_dnp3_item(), protocol_type)
    yt = YtService._create_point(_dnp3_item(), protocol_type)
    assert yc is not None and int(yc.address) == 9
    assert yx is not None and int(yx.address) == 9
    assert yk is not None and int(yk.address) == 9
    assert yt is not None and int(yt.address) == 9
    # 十进制 index 无歧义
    yc10 = YcService._create_point(_dnp3_item("10"), protocol_type)
    assert yc10 is not None and int(yc10.address) == 10


@pytest.mark.asyncio
async def test_dnp3_handler_batch_read_uses_one_integrity_refresh_for_all_points():
    """DNP3 批量读取不能退化成每个测点各发一次完整性轮询。"""
    from src.device.protocol.dnp3_handler import DNP3ClientHandler

    client = SimpleNamespace(
        read_points_active=AsyncMock(
            return_value={
                (3, 30): 12.5,
                (7, 1): True,
            }
        )
    )
    handler = DNP3ClientHandler()
    handler._client = client
    analog = SimpleNamespace(code="AI-3", address=3, frame_type=0)
    binary = SimpleNamespace(code="BI-7", address=7, frame_type=1)

    values = await handler.read_points_batch_async([analog, binary])

    client.read_points_active.assert_awaited_once_with([(3, 30), (7, 1)])
    assert values == {"AI-3": 12.5, "BI-7": True}


@pytest.mark.asyncio
async def test_dnp3_client_batch_read_sends_one_addressed_request():
    from src.proto.dnp3.dnp3_client import Dnp3Client

    client = Dnp3Client()
    client._request = AsyncMock(return_value=SimpleNamespace(header=SimpleNamespace(iin=None)))
    client.read_point = Mock(side_effect=lambda index, group: f"{group}:{index}")

    values = await client.read_points_active([(3, 30), (7, 1)])

    client._request.assert_awaited_once()
    function, objects = client._request.await_args.args
    assert function.name == "READ"
    assert [(obj.header.group, obj.header.start, obj.header.stop) for obj in objects] == [
        (30, 3, 3),
        (1, 7, 7),
    ]
    assert values == {(3, 30): "30:3", (7, 1): "1:7"}
