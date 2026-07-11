"""通道管理 - IEC 61850 GOOSE 相关路由

提供 GOOSE Publisher/Subscriber 的完整管理 API:
- Publisher CRUD + 发布控制 + 数据集管理
- Subscriber CRUD + Receiver 管理
- 实时状态查询

ICD 文件 GOOSE 配置统一通过 /import-icd 接口导入（含 MMS 测点 + GOOSE）。
"""

from typing import Any

from fastapi import APIRouter, Request

from src.data.service.channel_service import ChannelService
from src.proto.iec61850.plugins.goose.manager import GooseResourceManager
from src.web.api.exceptions import NotFoundError, OperationError, ValidationError
from src.web.api.schemas import BaseResponse
from src.web.api.schemas.goose import (
    GooseCaptureListRequest,
    GooseCaptureStartRequest,
    GooseCaptureStopRequest,
    GooseChannelRequest,
    GooseImportDiscoveredRequest,
    GoosePublisherCreate,
    GoosePublisherEntriesReplace,
    GoosePublisherEntryAdd,
    GoosePublisherEntryRemove,
    GoosePublisherEntryUpdate,
    GoosePublisherIdRequest,
    GoosePublisherUpdate,
    GooseReceiverCreate,
    GooseReceiverIdRequest,
    GooseReceiverSubscriptionsReplace,
    GooseReceiverUpdate,
    GooseSubscriptionCreate,
    GooseSubscriptionRemove,
)
from src.web.log import log

router = APIRouter(tags=["goose"])


# ===== 辅助函数 =====


def _validate_iec61850_channel(channel_id: int):
    """验证通道是否为 IEC61850 协议

    Raises:
        NotFoundError: 通道不存在
        ValidationError: 协议不匹配
    """
    channel = ChannelService.get_channel_by_id(channel_id)
    if not channel:
        raise NotFoundError("通道不存在")
    if channel.get("protocol_type", -1) != 4:
        raise ValidationError("该通道不是 IEC61850 协议")
    return channel


def _get_goose_manager(request: Request) -> GooseResourceManager:
    """获取 GOOSE 管理器

    Raises:
        OperationError: GOOSE 管理器未初始化
    """
    manager = getattr(request.app.state, "goose_manager", None)
    if not manager:
        raise OperationError("GOOSE 管理器未初始化")
    return manager


def _get_discovered_goose(channel_id: int, request: Request) -> list[dict[str, Any]]:
    """获取通道对应客户端连接时发现的远端 GOOSE 控制块"""
    device_controller = getattr(request.app.state, "device_controller", None)
    device = device_controller.get_device_by_channel_id(channel_id) if device_controller else None
    handler = getattr(device, "protocol_handler", None) if device else None
    discovered = getattr(handler, "_discovered_goose_items", None)
    return list(discovered) if discovered else []


def _require_resource_channel(actual: int | None, expected: int | None) -> None:
    if expected is not None and actual != expected:
        raise NotFoundError("当前设备下未找到该 GOOSE 资源")


# ===== GOOSE Publisher 管理 =====


@router.post("/goose/publishers", response_model=BaseResponse)
async def create_goose_publisher(
    request: Request,
    body: GoosePublisherCreate,
):
    """创建 GOOSE Publisher"""
    manager = _get_goose_manager(request)
    if body.channel_id is None:
        raise ValidationError("创建 Publisher 必须指定 channel_id")
    if body.channel_id is not None:
        _validate_iec61850_channel(body.channel_id)
    from src.web.api.network_interfaces import validate_network_interface

    validate_network_interface(body.interface)

    # 根据 channel_id 查找对应的 IEC61850Server，用于注册 GSEControlBlock 到 MMS 模型
    iec61850_server = None
    if body.channel_id is not None:
        try:
            device_controller = getattr(request.app.state, "device_controller", None)
            if device_controller:
                _device = device_controller.get_device_by_id(body.channel_id)
                if _device and _device.protocol_handler:
                    _handler = _device.protocol_handler
                    from src.device.protocol.iec61850_handler import IEC61850ServerHandler

                    if isinstance(_handler, IEC61850ServerHandler):
                        iec61850_server = _handler.server
        except Exception as e:
            log.warning(f"获取 IEC61850Server 失败: {e}")

    result = manager.create_publisher(
        interface=body.interface,
        go_cb_ref=body.go_cb_ref,
        go_id=body.go_id,
        data_set_ref=body.data_set_ref,
        app_id=body.app_id,
        conf_rev=body.conf_rev,
        time_allowed_to_live=body.time_allowed_to_live,
        dst_mac=body.dst_mac,
        vlan_id=body.vlan_id,
        vlan_prio=body.vlan_prio,
        simulation=body.simulation,
        entries=[{"name": e.name, "value": e.value, "iec_type": e.iec_type} for e in body.entries],
        server=iec61850_server,
        channel_id=body.channel_id,
    )
    if not result:
        raise OperationError("GOOSE Publisher 创建失败")
    return BaseResponse(message="GOOSE Publisher 创建成功", data=result)


@router.post("/goose/publishers/list", response_model=BaseResponse)
async def list_goose_publishers(body: GooseChannelRequest, request: Request):
    """获取所有 GOOSE Publisher 列表"""
    manager = _get_goose_manager(request)
    _validate_iec61850_channel(body.channel_id)
    result = manager.list_publishers(body.channel_id)
    return BaseResponse(message="获取 GOOSE Publisher 列表成功", data={"items": result})


@router.post("/goose/discovered/list", response_model=BaseResponse)
async def list_discovered_goose(body: GooseChannelRequest, request: Request):
    """获取客户端连接时发现的远端 GOOSE 控制块列表"""
    items = _get_discovered_goose(body.channel_id, request)
    return BaseResponse(message="获取发现的 GOOSE 控制块成功", data={"items": items})


@router.post("/goose/discovered/import", response_model=BaseResponse)
async def import_discovered_goose(body: GooseImportDiscoveredRequest, request: Request):
    """将客户端发现的远端 GOOSE 控制块自动导入为 Receiver 订阅 (幂等)"""
    manager = _get_goose_manager(request)
    _validate_iec61850_channel(body.channel_id)
    from src.web.api.network_interfaces import validate_network_interface

    validate_network_interface(body.interface)
    items = _get_discovered_goose(body.channel_id, request)
    if not items:
        return BaseResponse(message="没有可导入的 GOOSE 控制块", data={"imported": 0, "receiver": None})

    receiver = manager.import_discovered(items, interface=body.interface, channel_id=body.channel_id)
    return BaseResponse(
        message=f"已导入 {len(items)} 个 GOOSE 控制块",
        data={"imported": len(items), "receiver": receiver},
    )


@router.post("/goose/publishers/detail", response_model=BaseResponse)
async def get_goose_publisher(
    body: GoosePublisherIdRequest,
    request: Request,
):
    """获取指定 GOOSE Publisher 状态"""
    manager = _get_goose_manager(request)
    if body.channel_id is not None:
        _validate_iec61850_channel(body.channel_id)
    result = manager.get_publisher_status(body.publisher_id)
    if not result:
        raise NotFoundError("GOOSE Publisher 未找到")
    _require_resource_channel(result.get("channel_id"), body.channel_id)
    return BaseResponse(message="获取 GOOSE Publisher 状态成功", data=result)


@router.post("/goose/publishers/update", response_model=BaseResponse)
async def update_goose_publisher(
    request: Request,
    body: GoosePublisherUpdate,
):
    """更新 GOOSE Publisher 配置"""
    manager = _get_goose_manager(request)
    current = manager.get_publisher_status(body.publisher_id)
    if not current:
        raise NotFoundError("GOOSE Publisher 未找到")
    _require_resource_channel(current.get("channel_id"), body.channel_id)
    if body.interface is not None:
        from src.web.api.network_interfaces import validate_network_interface

        validate_network_interface(body.interface)
    update_kwargs = dict(
        publisher_id=body.publisher_id,
        interface=body.interface,
        go_cb_ref=body.go_cb_ref,
        go_id=body.go_id,
        data_set_ref=body.data_set_ref,
        app_id=body.app_id,
        conf_rev=body.conf_rev,
        time_allowed_to_live=body.time_allowed_to_live,
        vlan_id=body.vlan_id,
        vlan_prio=body.vlan_prio,
        simulation=body.simulation,
    )
    if "dst_mac" in body.model_fields_set:
        update_kwargs["dst_mac"] = body.dst_mac
    result = manager.update_publisher(**update_kwargs)
    if not result:
        raise NotFoundError("GOOSE Publisher 未找到")
    return BaseResponse(message="更新 GOOSE Publisher 成功", data=result)


@router.post("/goose/publishers/delete", response_model=BaseResponse)
async def delete_goose_publisher(
    body: GoosePublisherIdRequest,
    request: Request,
):
    """删除 GOOSE Publisher"""
    manager = _get_goose_manager(request)
    current = manager.get_publisher_status(body.publisher_id)
    if current:
        _require_resource_channel(current.get("channel_id"), body.channel_id)
    success = manager.delete_publisher(body.publisher_id, delete_from_db=True)
    if not success:
        raise NotFoundError("GOOSE Publisher 未找到")
    return BaseResponse(message="删除 GOOSE Publisher 成功", data={})


@router.post("/goose/publishers/start", response_model=BaseResponse)
async def start_goose_publisher(
    body: GoosePublisherIdRequest,
    request: Request,
):
    """启动 GOOSE Publisher"""
    manager = _get_goose_manager(request)
    current = manager.get_publisher_status(body.publisher_id)
    if current:
        _require_resource_channel(current.get("channel_id"), body.channel_id)
    success = manager.start_publisher(body.publisher_id)
    if not success:
        raise OperationError("GOOSE Publisher 启动失败")
    return BaseResponse(message="GOOSE Publisher 启动成功", data={"publisher_id": body.publisher_id})


@router.post("/goose/publishers/stop", response_model=BaseResponse)
async def stop_goose_publisher(
    body: GoosePublisherIdRequest,
    request: Request,
):
    """停止 GOOSE Publisher"""
    manager = _get_goose_manager(request)
    current = manager.get_publisher_status(body.publisher_id)
    if current:
        _require_resource_channel(current.get("channel_id"), body.channel_id)
    success = manager.stop_publisher(body.publisher_id)
    if not success:
        raise NotFoundError("GOOSE Publisher 未找到")
    return BaseResponse(message="GOOSE Publisher 停止成功", data={"publisher_id": body.publisher_id})


@router.post("/goose/publishers/publish", response_model=BaseResponse)
async def publish_goose_now(
    body: GoosePublisherIdRequest,
    request: Request,
):
    """立即发布 GOOSE 报文 (手动触发)"""
    manager = _get_goose_manager(request)
    current = manager.get_publisher_status(body.publisher_id)
    if current:
        _require_resource_channel(current.get("channel_id"), body.channel_id)
    success = manager.publish_now(body.publisher_id)
    if not success:
        raise OperationError("GOOSE 报文发布失败")
    return BaseResponse(message="GOOSE 报文发布成功", data={"publisher_id": body.publisher_id})


# ===== GOOSE Publisher 数据集管理 =====


@router.post("/goose/publishers/entries/add", response_model=BaseResponse)
async def add_publisher_entry(
    request: Request,
    body: GoosePublisherEntryAdd,
):
    """向 Publisher 添加数据集条目"""
    manager = _get_goose_manager(request)
    result = manager.add_publisher_entry(
        publisher_id=body.publisher_id,
        name=body.entry.name,
        value=body.entry.value,
        iec_type=body.entry.iec_type,
    )
    if not result:
        raise NotFoundError("GOOSE Publisher 未找到")
    return BaseResponse(message="添加数据集条目成功", data=result)


@router.post("/goose/publishers/entries/update", response_model=BaseResponse)
async def update_publisher_entry(
    request: Request,
    body: GoosePublisherEntryUpdate,
):
    """更新 Publisher 数据集条目值"""
    manager = _get_goose_manager(request)
    result = manager.update_publisher_entry(
        publisher_id=body.publisher_id,
        index=body.index,
        value=body.value,
    )
    if result is None:
        raise NotFoundError("GOOSE Publisher 或条目未找到")

    # 同步更新 MMS 服务器数据模型中的对应 DA 值（如果有）
    try:
        channel_id = manager._channel_map.get(body.publisher_id)
        if channel_id is not None:
            device_controller = getattr(request.app.state, "device_controller", None)
            if device_controller:
                _device = device_controller.get_device_by_id(channel_id)
                if _device and _device.protocol_handler:
                    _handler = _device.protocol_handler
                    from src.device.protocol.iec61850_handler import IEC61850ServerHandler

                    if isinstance(_handler, IEC61850ServerHandler) and _handler.server:
                        iec61850_server = _handler.server
                        publisher = manager._publishers.get(body.publisher_id)
                        if publisher:
                            entries = publisher.get_entries()
                            if 0 <= body.index < len(entries):
                                entry_name = entries[body.index].get("name", "")
                                if entry_name:
                                    # 尝试更新 MMS 数据模型中的对应 DA
                                    iec61850_server.set_point_value(entry_name, body.value)
                                    log.debug(f"已同步更新 MMS 模型 DA: {entry_name} = {body.value}")
    except Exception as sync_err:
        log.debug(f"同步 MMS 模型 DA 值失败（非致命）: {sync_err}")

    return BaseResponse(
        message="更新数据集条目成功",
        data={"publisher_id": body.publisher_id, "index": body.index, "changed": result},
    )


@router.post("/goose/publishers/entries/remove", response_model=BaseResponse)
async def remove_publisher_entry(
    request: Request,
    body: GoosePublisherEntryRemove,
):
    """移除 Publisher 数据集条目"""
    manager = _get_goose_manager(request)
    success = manager.remove_publisher_entry(
        publisher_id=body.publisher_id,
        index=body.index,
    )
    if not success:
        raise NotFoundError("GOOSE Publisher 或条目未找到")
    return BaseResponse(message="移除数据集条目成功", data={})


@router.post("/goose/publishers/entries/replace", response_model=BaseResponse)
async def replace_publisher_entries(request: Request, body: GoosePublisherEntriesReplace):
    manager = _get_goose_manager(request)
    current = manager.get_publisher_status(body.publisher_id)
    if not current:
        raise NotFoundError("GOOSE Publisher 未找到")
    _require_resource_channel(current.get("channel_id"), body.channel_id)
    result = manager.replace_publisher_entries(body.publisher_id, [entry.model_dump() for entry in body.entries])
    if not result:
        raise OperationError("Publisher 运行中，停止后才能修改数据集结构")
    return BaseResponse(message="数据集配置已保存", data=result)


# ===== GOOSE Receiver/Subscriber 管理 =====


@router.post("/goose/receivers", response_model=BaseResponse)
async def create_goose_receiver(
    request: Request,
    body: GooseReceiverCreate,
):
    """创建 GOOSE Receiver"""
    manager = _get_goose_manager(request)
    _validate_iec61850_channel(body.channel_id)
    from src.web.api.network_interfaces import validate_network_interface

    validate_network_interface(body.interface)
    subscriptions = [
        {
            "go_cb_ref": s.go_cb_ref,
            "app_id": s.app_id,
            "dst_mac": s.dst_mac,
            "description": s.description,
            "data_set_ref": s.data_set_ref,
            "conf_rev": s.conf_rev,
        }
        for s in body.subscriptions
    ]

    result = manager.create_receiver(
        interface=body.interface,
        subscriptions=subscriptions,
        channel_id=body.channel_id,
        name=body.name,
        description=body.description,
        auto_start=body.auto_start,
    )
    if not result:
        raise OperationError("GOOSE Receiver 创建失败")
    return BaseResponse(message="GOOSE Receiver 创建成功", data=result)


@router.post("/goose/receivers/list", response_model=BaseResponse)
async def list_goose_receivers(body: GooseChannelRequest, request: Request):
    """获取所有 GOOSE Receiver 列表"""
    manager = _get_goose_manager(request)
    _validate_iec61850_channel(body.channel_id)
    result = manager.list_receivers(body.channel_id)
    return BaseResponse(message="获取 GOOSE Receiver 列表成功", data={"items": result})


@router.post("/goose/receivers/detail", response_model=BaseResponse)
async def get_goose_receiver(
    body: GooseReceiverIdRequest,
    request: Request,
):
    """获取指定 GOOSE Receiver 状态"""
    manager = _get_goose_manager(request)
    result = manager.get_receiver_status(body.receiver_id)
    if not result:
        raise NotFoundError("GOOSE Receiver 未找到")
    _require_resource_channel(result.get("channel_id"), body.channel_id)
    return BaseResponse(message="获取 GOOSE Receiver 状态成功", data=result)


@router.post("/goose/receivers/delete", response_model=BaseResponse)
async def delete_goose_receiver(
    body: GooseReceiverIdRequest,
    request: Request,
):
    """删除 GOOSE Receiver"""
    manager = _get_goose_manager(request)
    current = manager.get_receiver_status(body.receiver_id)
    if current:
        _require_resource_channel(current.get("channel_id"), body.channel_id)
    success = manager.delete_receiver(body.receiver_id)
    if not success:
        raise NotFoundError("GOOSE Receiver 未找到")
    return BaseResponse(message="删除 GOOSE Receiver 成功", data={})


@router.post("/goose/receivers/update", response_model=BaseResponse)
async def update_goose_receiver(body: GooseReceiverUpdate, request: Request):
    manager = _get_goose_manager(request)
    current = manager.get_receiver_status(body.receiver_id)
    if not current:
        raise NotFoundError("GOOSE Receiver 未找到")
    _require_resource_channel(current.get("channel_id"), body.channel_id)
    from src.web.api.network_interfaces import validate_network_interface

    validate_network_interface(body.interface)
    result = manager.update_receiver(body.receiver_id, body.interface, body.name, body.description, body.auto_start)
    if not result:
        raise OperationError("Receiver 运行中，停止后才能修改配置")
    return BaseResponse(message="GOOSE Receiver 配置已保存", data=result)


@router.post("/goose/receivers/start", response_model=BaseResponse)
async def start_goose_receiver(
    body: GooseReceiverIdRequest,
    request: Request,
):
    """启动 GOOSE Receiver"""
    manager = _get_goose_manager(request)
    current = manager.get_receiver_status(body.receiver_id)
    if current:
        _require_resource_channel(current.get("channel_id"), body.channel_id)
    success = manager.start_receiver(body.receiver_id)
    if not success:
        raise OperationError("GOOSE Receiver 启动失败")
    return BaseResponse(message="GOOSE Receiver 启动成功", data={"receiver_id": body.receiver_id})


@router.post("/goose/receivers/stop", response_model=BaseResponse)
async def stop_goose_receiver(
    body: GooseReceiverIdRequest,
    request: Request,
):
    """停止 GOOSE Receiver"""
    manager = _get_goose_manager(request)
    current = manager.get_receiver_status(body.receiver_id)
    if current:
        _require_resource_channel(current.get("channel_id"), body.channel_id)
    success = manager.stop_receiver(body.receiver_id)
    if not success:
        raise NotFoundError("GOOSE Receiver 未找到")
    return BaseResponse(message="GOOSE Receiver 停止成功", data={"receiver_id": body.receiver_id})


# ===== GOOSE Receiver 订阅管理 =====


@router.post("/goose/receivers/subscriptions/add", response_model=BaseResponse)
async def add_receiver_subscription(
    request: Request,
    body: GooseSubscriptionCreate,
):
    """向 Receiver 添加订阅"""
    manager = _get_goose_manager(request)
    result = manager.add_subscription(
        receiver_id=body.receiver_id,
        go_cb_ref=body.go_cb_ref,
        app_id=body.app_id,
        dst_mac=body.dst_mac,
        description=body.description,
        data_set_ref=body.data_set_ref,
        conf_rev=body.conf_rev,
    )
    if not result:
        raise NotFoundError("GOOSE Receiver 未找到")
    return BaseResponse(message="添加订阅成功", data=result)


@router.post("/goose/receivers/subscriptions/remove", response_model=BaseResponse)
async def remove_receiver_subscription(
    request: Request,
    body: GooseSubscriptionRemove,
):
    """从 Receiver 移除订阅"""
    manager = _get_goose_manager(request)
    success = manager.remove_subscription(
        receiver_id=body.receiver_id,
        go_cb_ref=body.go_cb_ref,
    )
    if not success:
        raise NotFoundError("GOOSE Receiver 或订阅未找到")
    return BaseResponse(message="移除订阅成功", data={})


@router.post("/goose/receivers/subscriptions/replace", response_model=BaseResponse)
async def replace_receiver_subscriptions(request: Request, body: GooseReceiverSubscriptionsReplace):
    manager = _get_goose_manager(request)
    current = manager.get_receiver_status(body.receiver_id)
    if not current:
        raise NotFoundError("GOOSE Receiver 未找到")
    _require_resource_channel(current.get("channel_id"), body.channel_id)
    result = manager.replace_subscriptions(
        body.receiver_id,
        [item.model_dump(exclude={"receiver_id"}) for item in body.subscriptions],
    )
    if not result:
        raise OperationError("Receiver 运行中，停止后才能修改订阅")
    return BaseResponse(message="订阅配置已保存", data=result)


# ===== GOOSE 报文抓包 =====

GOOSE_CAPTURE_INSTANCES: dict[str, Any] = {}  # interface -> GooseCapture


def _get_capture(interface: str = "", channel_id: int = 0) -> Any | None:
    """获取或创建指定接口的 GOOSE 捕获器"""
    key = f"{channel_id}:{interface or '__default__'}"
    capture = GOOSE_CAPTURE_INSTANCES.get(key)
    if capture is None:
        try:
            from src.proto.iec61850.plugins.goose.capture import GooseCaptureEngine

            capture = GooseCaptureEngine(interface=interface)
            GOOSE_CAPTURE_INSTANCES[key] = capture
        except Exception as e:
            log.error(f"创建 GOOSE Capture 失败: {e}")
            return None
    return capture


@router.post("/goose/capture/start", response_model=BaseResponse)
async def start_goose_capture(
    body: GooseCaptureStartRequest,
):
    """启动 GOOSE 报文抓包"""
    _validate_iec61850_channel(body.channel_id)
    from src.web.api.network_interfaces import validate_network_interface

    validate_network_interface(body.interface)
    capture = _get_capture(body.interface, body.channel_id)
    if not capture:
        raise OperationError("GOOSE 捕获器初始化失败")

    if body.max_packets:
        capture._max_packets = body.max_packets

    if body.filter_app_id is not None:
        capture.set_app_id_filter(body.filter_app_id)

    success = capture.start()
    if not success:
        raise OperationError("GOOSE 报文抓包启动失败 (可能需要管理员/root 权限)")
    return BaseResponse(
        message="GOOSE 报文抓包已启动",
        data={"interface": body.interface or "auto", "is_running": True},
    )


@router.post("/goose/capture/stop", response_model=BaseResponse)
async def stop_goose_capture(body: GooseCaptureStopRequest):
    """停止 GOOSE 报文抓包"""
    prefix = f"{body.channel_id}:"
    for key, capture in GOOSE_CAPTURE_INSTANCES.items():
        if not key.startswith(prefix):
            continue
        if capture.is_running:
            capture.stop()
    return BaseResponse(message="GOOSE 报文抓包已停止", data={})


@router.post("/goose/capture/list", response_model=BaseResponse)
async def list_goose_capture(
    body: GooseCaptureListRequest,
):
    """获取捕获的 GOOSE 报文列表"""
    # 查找正在运行的捕获器
    capture = None
    prefix = f"{body.channel_id}:"
    for key, c in GOOSE_CAPTURE_INSTANCES.items():
        if not key.startswith(prefix):
            continue
        if c.is_running:
            capture = c
            break

    if not capture:
        raise ValidationError("没有正在运行的 GOOSE 抓包会话")

    packets = capture.get_packets(count=body.count, filter_app_id=body.filter_app_id)
    stats = capture.get_statistics()
    status = capture.get_status()

    return BaseResponse(
        message="获取 GOOSE 报文成功",
        data={
            "packets": packets,
            "statistics": stats,
            "status": status,
        },
    )


@router.post("/goose/capture/clear", response_model=BaseResponse)
async def clear_goose_capture(body: GooseCaptureStopRequest):
    """清空捕获的 GOOSE 报文"""
    prefix = f"{body.channel_id}:"
    for key, capture in GOOSE_CAPTURE_INSTANCES.items():
        if not key.startswith(prefix):
            continue
        capture.clear()
    return BaseResponse(message="已清空所有 GOOSE 报文", data={})


@router.post("/goose/capture/status", response_model=BaseResponse)
async def get_goose_capture_status(body: GooseCaptureStopRequest):
    """获取 GOOSE 抓包状态"""
    results = []
    prefix = f"{body.channel_id}:"
    for key, capture in GOOSE_CAPTURE_INSTANCES.items():
        if not key.startswith(prefix):
            continue
        results.append(capture.get_status())

    return BaseResponse(
        message="获取 GOOSE 抓包状态成功",
        data={"captures": results},
    )


# ===== GOOSE ICD 导入 =====
# GOOSE 配置统一通过 /import-icd (import_points.py) 导入，
# 该接口同时处理 MMS 测点 + GOOSE 配置，不再需要单独的 GOOSE ICD 预览端点。
