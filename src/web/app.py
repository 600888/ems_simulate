import asyncio
from datetime import UTC

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.web.api import (
    channel_router,
    device_group_router,
    device_router,
    point_mapping_router,
    point_router,
    point_tree_router,
)
from src.web.api.schemas import BaseResponse
from src.web.log import log


def create_app():
    app = FastAPI(
        title="EMS Simulator API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # 配置CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(channel_router)
    app.include_router(device_router)
    app.include_router(point_router)
    app.include_router(point_mapping_router)
    app.include_router(point_tree_router)
    app.include_router(device_group_router)

    # 初始化就绪状态
    app.state.initialized = False

    return app


app = create_app()


@app.get("/api/health")
async def health_check():
    """
    健康检查端点 - 供 Tauri 桌面客户端检测后端服务是否就绪
    返回后端服务状态、版本信息和数据库连接状态

    状态区分:
    - initialized=False: 服务已启动但设备初始化尚未完成（返回 503）
    - initialized=True: 服务完全就绪（返回 200）
    """
    initialized = getattr(app.state, "initialized", False)

    health_data = {
        "status": "ok" if initialized else "initializing",
        "version": "1.0.0",
        "service": "EMS Simulate Backend",
        "timestamp": None,
    }
    try:
        from datetime import datetime

        health_data["timestamp"] = datetime.now(UTC).isoformat()
    except Exception:
        pass

    # 检查数据库连接（可选）
    try:
        from src.config.config import Config

        health_data["database"] = Config.db_type
    except Exception:
        health_data["database"] = "unknown"

    if not initialized:
        return JSONResponse(
            status_code=503,
            content=BaseResponse(code=503, message="服务初始化中，请稍后", data=health_data).model_dump(),
        )

    return BaseResponse(code=0, message="服务正常", data=health_data).model_dump()


async def _init_device_controller():
    """后台初始化设备控制器"""
    from src.device_controller import get_device_controller

    return await get_device_controller()


async def _init_goose_manager(device_controller):
    """后台初始化 GOOSE 管理器"""
    try:
        from src.proto.iec61850.plugins.goose.manager import GooseResourceManager

        goose_manager = GooseResourceManager()
        log.info("GOOSE 管理器初始化成功")

        # 从数据库加载已持久化的 GOOSE Publisher 配置
        try:
            from src.proto.iec61850.iec61850_server import IEC61850Server

            server_map = {}
            for device in device_controller.device_list:
                device_id = getattr(device, "device_id", None) or getattr(device, "id", None)
                if device_id and hasattr(device, "protocol_handler") and device.protocol_handler:
                    handler = device.protocol_handler
                    if hasattr(handler, "server") and handler.server:
                        if isinstance(handler.server, IEC61850Server):
                            server_map[device_id] = handler.server

            loaded_count = goose_manager.load_from_db(server_map=server_map)
            if server_map:
                log.info(f"已将 {len(server_map)} 个 IEC61850 服务器关联到 GOOSE DataSet 注册")
            log.info(f"从数据库加载 {loaded_count} 个已持久化的 GOOSE Publisher")
        except Exception as load_err:
            log.warning(f"从数据库加载 GOOSE Publisher 失败: {load_err}")

        return goose_manager
    except Exception as e:
        log.warning(f"GOOSE 管理器初始化失败 (GOOSE 功能不可用): {e}")
        return None


async def _background_init():
    """后台初始化：设备控制器 + GOOSE 管理器

    不阻塞 uvicorn 端口监听，Tauri 通过 /api/health 检测初始化状态
    """
    import time

    t0 = time.perf_counter()
    log.info("开始后台初始化...")

    try:
        # 1. 初始化设备控制器
        device_controller = await _init_device_controller()
        app.state.device_controller = device_controller
        log.info(
            f"设备控制器初始化完成 ({len(device_controller.device_list)} 个设备), 耗时 {time.perf_counter() - t0:.2f}s"
        )

        # 2. 初始化 GOOSE 管理器
        app.state.goose_manager = await _init_goose_manager(device_controller)

        # 3. 标记初始化完成
        app.state.initialized = True
        log.info(f"后台初始化全部完成, 总耗时 {time.perf_counter() - t0:.2f}s")

    except Exception as e:
        log.error(f"后台初始化失败: {e}")
        # 即使初始化失败也标记完成，避免前端无限等待
        app.state.initialized = True


@app.on_event("startup")
async def startup_event():
    """FastAPI启动事件：在后台异步初始化设备，不阻塞端口监听"""
    asyncio.create_task(_background_init())


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"服务器内部错误: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content=BaseResponse(code=500, message=f"服务器内部错误: {str(exc)}", data={}).dict(),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="info")
