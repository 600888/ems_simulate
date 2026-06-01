"""通道管理模块

合并所有子路由为统一的 channel_router
"""

from fastapi import APIRouter

from src.web.api.channel.device_manage import router as device_manage_router
from src.web.api.channel.files import router as files_router
from src.web.api.channel.goose import router as goose_router
from src.web.api.channel.goose_websocket import ws_router as goose_ws_router
from src.web.api.channel.iec61850 import router as iec61850_router
from src.web.api.channel.import_points import router as import_points_router
from src.web.api.channel.report import router as report_router
from src.web.api.channel.router import router as channel_crud_router

channel_router = APIRouter(prefix="/api/channels", tags=["通道管理"])

channel_router.include_router(channel_crud_router)
channel_router.include_router(device_manage_router)
channel_router.include_router(import_points_router)
channel_router.include_router(iec61850_router)
channel_router.include_router(goose_router)
channel_router.include_router(goose_ws_router)
channel_router.include_router(report_router)
channel_router.include_router(files_router)
