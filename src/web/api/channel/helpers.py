"""通道模块 - 公共辅助函数"""

import asyncio
import os
from typing import Any

from src.config.config import Config
from src.data.service.channel_configuration_service import ChannelConfigurationService
from src.data.service.channel_service import ChannelService
from src.device.factory.general_device_builder import GeneralDeviceBuilder
from src.device.types.circuit_breaker import CircuitBreaker
from src.device.types.general_device import GeneralDevice
from src.device.types.pcs import Pcs
from src.enums.modbus_def import ProtocolType
from src.web.api.exceptions import NotFoundError
from src.web.log import log


def get_device_builder(channel_id: int, channel_code: str) -> GeneralDeviceBuilder:
    """根据通道编码选择设备构建器"""
    code_upper = channel_code.upper()
    if "PCS" in code_upper:
        return GeneralDeviceBuilder(channel_id=channel_id, device=Pcs())
    elif "BREAKER" in code_upper:
        return GeneralDeviceBuilder(channel_id=channel_id, device=CircuitBreaker())
    else:
        return GeneralDeviceBuilder(channel_id=channel_id, device=GeneralDevice())


def configure_builder_network(builder, conn_type, protocol_type, ip, port, channel_data):
    """配置构建器的网络/串口参数"""
    if conn_type in [0, 3]:  # 串口
        builder.setDeviceSerialConfig(
            serial_port=channel_data.get("com_port", ""),
            baudrate=channel_data.get("baud_rate", 9600),
            databits=channel_data.get("data_bits", 8),
            stopbits=channel_data.get("stop_bits", 1),
            parity=channel_data.get("parity", "E"),
        )
    elif protocol_type in [
        ProtocolType.Iec104Client,
        ProtocolType.ModbusTcpClient,
        ProtocolType.Dlt645Client,
        ProtocolType.Iec61850Client,
    ]:
        builder.setDeviceNetConfig(port=port, ip=ip)
    else:
        builder.setDeviceNetConfig(port=port, ip=Config.DEFAULT_IP)

    # IEC 61850: 传递 IED 模型名称 (从通道配置的 model_name 字段获取，对应 ICD 文件中的 IED name)
    if protocol_type in (ProtocolType.Iec61850Server, ProtocolType.Iec61850Client):
        model_name = channel_data.get("model_name")
        if model_name:
            builder.setDeviceModelName(model_name)
        # v2.0: 传递 ICD 文件路径
        icd_path = channel_data.get("icd_path")
        if icd_path:
            builder.setDeviceIcdPath(icd_path)

    channel_id = channel_data.get("id")
    if channel_id:
        builder.setDeviceRuntimeConfig(
            ChannelConfigurationService.get_protocol_params(
                channel_id,
                channel_data.get("protocol_type", 1),
                conn_type,
            )["values"]
        )
        builder.setDeviceSecurityConfig(ChannelConfigurationService.get_runtime_security(channel_id))


def is_client_protocol(protocol_type) -> bool:
    """判断是否为客户端协议"""
    return protocol_type in [
        ProtocolType.ModbusTcpClient,
        ProtocolType.Iec104Client,
        ProtocolType.Dlt645Client,
        ProtocolType.Iec61850Client,
    ]


async def reload_device_instance(device_controller, channel_id: int, is_start: bool = True, scl_result: Any = None):
    """重载/重启设备实例

    Args:
        device_controller: 设备控制器
        channel_id: 通道 ID
        is_start: 是否启动设备
        scl_result: 可选，预先解析的 SclImportResult。提供时跳过 ICD 文件重新解析。
    """
    channel = await asyncio.to_thread(ChannelService.get_channel_by_id, channel_id)
    if not channel:
        raise NotFoundError(f"通道 {channel_id} 不存在")

    device_name = channel["name"]
    channel_code = channel["code"]
    channel_protocol_type = ChannelService.get_protocol_type(channel)
    port = channel.get("port", Config.DEFAULT_PORT)
    ip = channel.get("ip", Config.DEFAULT_IP)

    conn_type = channel.get("conn_type", 1)

    log.info(
        f"Preparing to reload device {device_name}. "
        f"Protocol: {channel_protocol_type}, ConnType: {conn_type}, "
        f"IP: {ip}, Port: {port}"
    )

    def build_device():
        """Build and hydrate a device away from the ASGI event loop."""
        builder = get_device_builder(channel_id, channel_code)
        configure_builder_network(builder, conn_type, channel_protocol_type, ip, port, channel)

        device = builder.makeGeneralDevice(
            device_id=channel_id,
            device_name=device_name,
            protocol_type=channel_protocol_type,
            is_start=is_start,
        )
        if device is None:
            raise RuntimeError(f"无法为协议 {channel_protocol_type} 创建设备 {device_name}")
        device.name = device_name

        # 普通重载/程序启动只恢复设备与 ICD 路径，不自动加载模型。
        # scl_result 仅在用户主动执行 ICD 导入时传入，属于显式加载操作。
        if scl_result is not None and channel_protocol_type in (
            ProtocolType.Iec61850Server,
            ProtocolType.Iec61850Client,
        ):
            icd_path = channel.get("icd_path")
            if icd_path and os.path.exists(icd_path):
                try:
                    device.load_iec61850_model(icd_path, scl_result=scl_result)
                    log.info(f"用户导入 ICD 时显式加载模型: {icd_path}")
                except Exception as load_err:
                    log.warning(f"用户导入 ICD 时加载模型失败: {load_err}")
        return device

    new_device = await asyncio.to_thread(build_device)

    # 需要在新实例启动前停止旧实例（释放端口/连接）的场景
    needs_stop_before_start = is_start and (
        is_client_protocol(channel_protocol_type) or channel_protocol_type == ProtocolType.Iec61850Server
    )
    if needs_stop_before_start:
        await device_controller.remove_device_by_id(channel_id)

    if is_start and is_client_protocol(channel_protocol_type):
        if channel_protocol_type == ProtocolType.Iec61850Client:
            # IEC61850 客户端: 使用 start() 后台线程连接，而非仅启动数据更新线程
            await new_device.start()
        else:
            # Modbus/其他客户端：先连接服务器，再启动数据更新线程
            await new_device.start()
        new_device.data_update_thread.start()
    elif is_start and channel_protocol_type == ProtocolType.Iec61850Server:
        # IEC61850 服务端: 需要显式启动 MMS 服务器
        # 注意: IEC61850 服务器不在 is_client_protocol 中，
        # 必须单独处理，否则 reload_device_instance(is_start=True) 不会启动服务器
        await new_device.start()
        log.info(f"IEC 61850 服务端已启动: {device_name}")

    if not needs_stop_before_start:
        # 非启动场景（或无需先停的启动场景）：新实例已构建完成，
        # 此时再替换旧实例，避免删除-重建空窗期内接口报"设备不存在"
        await device_controller.remove_device_by_id(channel_id)

    device_controller.device_list.append(new_device)
    device_controller.device_map[new_device.name] = new_device

    log.info(f"设备 {device_name} 实例已更新 (启动状态: {is_start})")
    return new_device


def increment_ip(ip: str, offset: int) -> str:
    """递增IP地址的最后一个段"""
    if offset <= 0:
        return ip
    try:
        parts = ip.split(".")
        if len(parts) != 4:
            return ip
        last_octet = int(parts[3])
        new_last_octet = last_octet + offset
        if new_last_octet > 255:
            new_last_octet = new_last_octet % 256
        parts[3] = str(new_last_octet)
        return ".".join(parts)
    except Exception:
        return ip
