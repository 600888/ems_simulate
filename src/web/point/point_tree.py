from fastapi import APIRouter
from src.web.schemas.schemas import BaseResponse
from src.web.schemas.schemas_tree import TreeResponse
from src.data.service.point_tree_service import PointTreeService

router = APIRouter(prefix="/point_tree", tags=["Point Tree"])

@router.get("/tree", response_model=BaseResponse)
async def get_point_tree():
    """获取系统测点树结构"""
    tree_data = await PointTreeService.get_tree()
    return BaseResponse(message="Success", data=tree_data)
