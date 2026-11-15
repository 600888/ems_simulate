"""用户启动设备前的模型准备。"""

import asyncio
from pathlib import Path

from src.data.service.channel_service import ChannelService
from src.device.core.device import Device
from src.enums.modbus_def import ProtocolType
from src.web.api.exceptions import OperationError


async def prepare_device_start(device: Device) -> None:
    """IEC61850 优先复用已加载模型，否则恢复远程缓存或已保存的 ICD。"""
    if device.protocol_type not in (ProtocolType.Iec61850Client, ProtocolType.Iec61850Server):
        return
    if device.iec61850_model_loaded:
        return

    if device.protocol_type == ProtocolType.Iec61850Client:
        cache = await asyncio.to_thread(device.check_iec61850_model_cache)
        if cache.get("cache_exists"):
            if not await asyncio.to_thread(device.iec61850_load_model_from_cache):
                raise OperationError("IEC61850 模型缓存不存在或无法读取!", data=False)
            return

    icd_path = await asyncio.to_thread(ChannelService.get_icd_path, device.device_id)
    icd_path = icd_path or device.icd_path
    if not icd_path:
        if device.protocol_type == ProtocolType.Iec61850Server:
            raise OperationError("未找到可用的 IEC61850 模型，请先导入模型!", data=False)
        # 客户端仍可先连接，随后由用户执行在线发现。
        return
    if not Path(icd_path).is_file():
        raise OperationError(f"ICD 文件不存在: {icd_path}，请重新导入模型!", data=False)
    if not await asyncio.to_thread(device.load_iec61850_model, icd_path):
        raise OperationError("IEC61850 模型加载失败!", data=False)
