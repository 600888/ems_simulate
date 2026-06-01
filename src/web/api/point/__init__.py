"""测点管理模块"""

from fastapi import APIRouter

from src.web.api.point.mapping import point_mapping_router
from src.web.api.point.router import point_router
from src.web.api.point.tree import point_tree_router

__all__ = ["point_router", "point_mapping_router", "point_tree_router"]
