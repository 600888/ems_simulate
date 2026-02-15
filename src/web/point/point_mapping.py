from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from src.data.service.point_mapping_service import PointMappingService
from src.web.schemas.schemas import BaseResponse

router = APIRouter(prefix="/point_mapping", tags=["Point Mapping"])


from src.web.schemas.schemas_point_mapping import SourcePointItem

class PointMappingCreateRequest(BaseModel):
    device_name: str
    target_point_code: str
    source_point_codes: List[SourcePointItem]
    formula: str
    enable: bool = True


class PointMappingUpdateRequest(BaseModel):
    id: int
    device_name: Optional[str] = None
    target_point_code: Optional[str] = None
    source_point_codes: Optional[List[SourcePointItem]] = None
    formula: Optional[str] = None
    enable: Optional[bool] = None


class PointMappingDeleteRequest(BaseModel):
    mapping_id: int


class PointMappingResponse(BaseModel):
    id: int
    device_name: str
    target_point_code: str
    source_point_codes: str
    formula: str
    enable: bool


@router.post("/create", response_model=BaseResponse)
async def create_mapping(request: PointMappingCreateRequest):
    result = PointMappingService.create_mapping(
        device_name=request.device_name,
        target_point_code=request.target_point_code,
        source_point_codes=[item.dict() for item in request.source_point_codes],
        formula=request.formula,
        enable=request.enable
    )
    if not result:
        return BaseResponse(code=400, message="创建映射失败", data=None)
    return BaseResponse(message="创建映射成功", data=result)


@router.get("/list", response_model=BaseResponse)
async def get_all_mappings():
    data = PointMappingService.get_all_mappings()
    return BaseResponse(message="获取映射列表成功", data=data)


@router.post("/update", response_model=BaseResponse)
async def update_mapping(request: PointMappingUpdateRequest):
    data = request.dict(exclude_unset=True)
    mapping_id = data.pop("id")
    success = PointMappingService.update_mapping(mapping_id, data)
    if success:
        return BaseResponse(message="更新映射成功", data=True)
    return BaseResponse(code=400, message="更新映射失败", data=False)


@router.post("/delete", response_model=BaseResponse)
async def delete_mapping(request: PointMappingDeleteRequest):
    success = PointMappingService.delete_mapping(request.mapping_id)
    if success:
        return BaseResponse(message="删除映射成功", data=True)
    return BaseResponse(code=400, message="删除映射失败", data=False)
