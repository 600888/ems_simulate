"""测点映射路由"""

import asyncio

from fastapi import APIRouter, Request
from pydantic import BaseModel

from src.data.service.point_mapping_service import PointMappingService
from src.web.api.exceptions import ValidationError
from src.web.api.schemas import BaseResponse, SourcePointItem
from src.web.log import log

point_mapping_router = APIRouter(prefix="/api/point-mappings", tags=["测点映射"])


class PointMappingCreateRequest(BaseModel):
    device_name: str
    target_point_code: str
    source_point_codes: list[SourcePointItem]
    formula: str
    enable: bool = True


class PointMappingUpdateRequest(BaseModel):
    id: int
    device_name: str | None = None
    target_point_code: str | None = None
    source_point_codes: list[SourcePointItem] | None = None
    formula: str | None = None
    enable: bool | None = None


class PointMappingDeleteRequest(BaseModel):
    mapping_id: int


def _validate_dlt698_mapping(controller, data):
    from src.device.protocol.dlt698_handler import Dlt698Handler

    device = controller.device_map.get(data.get("device_name"))
    if device and isinstance(getattr(device, "protocol_handler", None), Dlt698Handler):
        point = device.point_manager.get_point_by_code(data.get("target_point_code"))
        if device.protocol_handler.get_runtime().config.role != "server" or not point or not point.scalar:
            raise ValidationError("DL/T 698 映射目标必须是服务端标量测点")
    for source in data.get("source_point_codes") or []:
        if not isinstance(source, dict):
            continue
        source_device = controller.device_map.get(source.get("device_name"))
        if source_device and isinstance(getattr(source_device, "protocol_handler", None), Dlt698Handler):
            point = source_device.point_manager.get_point_by_code(source.get("point_code"))
            if not point or not point.scalar:
                raise ValidationError("DL/T 698 映射来源必须是标量测点，复合值及 64 位整数请使用精确 Data")


async def _reload_device_mappings(device_controller, device_name: str | None) -> None:
    """重新加载设备的映射配置（失败仅记录日志，不影响主流程）"""
    if not device_name:
        return
    try:
        device = device_controller.device_map.get(device_name)
        if device:
            await asyncio.to_thread(device.reload_mappings)
    except Exception as e:
        log.warning(f"重新加载设备 {device_name} 的映射失败: {e}")


@point_mapping_router.post("/create", response_model=BaseResponse)
async def create_mapping(request: PointMappingCreateRequest, http_request: Request):
    """创建映射"""
    _validate_dlt698_mapping(http_request.app.state.device_controller, request.model_dump())
    result = await asyncio.to_thread(
        PointMappingService.create_mapping,
        device_name=request.device_name,
        target_point_code=request.target_point_code,
        source_point_codes=[item.model_dump() for item in request.source_point_codes],
        formula=request.formula,
        enable=request.enable,
    )
    if not result:
        raise ValidationError("创建映射失败")

    await _reload_device_mappings(http_request.app.state.device_controller, request.device_name)
    return BaseResponse(message="创建映射成功", data=result)


@point_mapping_router.post("/list", response_model=BaseResponse)
async def get_all_mappings():
    """获取映射列表"""
    data = await asyncio.to_thread(PointMappingService.get_all_mappings)
    return BaseResponse(message="获取映射列表成功", data=data)


@point_mapping_router.post("/update", response_model=BaseResponse)
async def update_mapping(request: PointMappingUpdateRequest, http_request: Request):
    """更新映射"""
    device_name = request.device_name
    if not device_name:
        existing = await asyncio.to_thread(PointMappingService.get_mapping_by_id, request.id)
        if existing:
            device_name = existing.get("device_name")

    data = request.model_dump(exclude_unset=True)
    mapping_id = data.pop("id")
    existing = await asyncio.to_thread(PointMappingService.get_mapping_by_id, mapping_id)
    if existing:
        import json

        merged = {**existing, **data}
        if isinstance(merged.get("source_point_codes"), str):
            merged["source_point_codes"] = json.loads(merged["source_point_codes"])
        _validate_dlt698_mapping(http_request.app.state.device_controller, merged)
    success = await asyncio.to_thread(PointMappingService.update_mapping, mapping_id, data)

    if not success:
        raise ValidationError("更新映射失败")

    await _reload_device_mappings(http_request.app.state.device_controller, device_name)
    return BaseResponse(message="更新映射成功", data=True)


@point_mapping_router.post("/delete", response_model=BaseResponse)
async def delete_mapping(request: PointMappingDeleteRequest, http_request: Request):
    """删除映射"""
    device_name = None
    existing = await asyncio.to_thread(PointMappingService.get_mapping_by_id, request.mapping_id)
    if existing:
        device_name = existing.get("device_name")

    success = await asyncio.to_thread(PointMappingService.delete_mapping, request.mapping_id)
    if not success:
        raise ValidationError("删除映射失败")

    await _reload_device_mappings(http_request.app.state.device_controller, device_name)
    return BaseResponse(message="删除映射成功", data=True)
