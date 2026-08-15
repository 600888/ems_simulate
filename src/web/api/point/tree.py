"""测点树路由"""

from fastapi import APIRouter
from pydantic import BaseModel

from src.data.service.point_tree_service import PointTreeService
from src.web.api.schemas import BaseResponse

point_tree_router = APIRouter(prefix="/api/point-tree", tags=["测点树"])


class PointTreeRequest(BaseModel):
    """测点树请求；device_name 为空时返回全部设备"""

    device_name: str | None = None


@point_tree_router.post("/tree", response_model=BaseResponse)
async def get_point_tree(req: PointTreeRequest | None = None):
    """获取系统测点树结构（可只返回指定设备）"""
    tree_data = await PointTreeService.get_tree(device_name=req.device_name if req else None)
    return BaseResponse(message="Success", data=tree_data)
