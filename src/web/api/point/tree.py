"""测点树路由"""

from fastapi import APIRouter

from src.data.service.point_tree_service import PointTreeService
from src.web.api.schemas import BaseResponse

point_tree_router = APIRouter(prefix="/api/point-tree", tags=["测点树"])


@point_tree_router.post("/tree", response_model=BaseResponse)
async def get_point_tree():
    """获取系统测点树结构"""
    tree_data = await PointTreeService.get_tree()
    return BaseResponse(message="Success", data=tree_data)
