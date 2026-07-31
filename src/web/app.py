import asyncio
from contextlib import asynccontextmanager
from datetime import UTC
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src import __version__
from src.proto.iec61850.core.exceptions import Iec61850Error
from src.web.api.channel import channel_router
from src.web.api.device import device_router
from src.web.api.device_group import device_group_router
from src.web.api.exceptions import BizError
from src.web.api.log_router import log_router
from src.web.api.modeling import router as modeling_router
from src.web.api.network_interfaces import router as network_interfaces_router
from src.web.api.point import point_mapping_router, point_router, point_tree_router
from src.web.api.schemas import BaseResponse
from src.web.api.schemas.response_codes import DEFAULT_MESSAGES, Code
from src.web.api.scl.router import router as scl_router
from src.web.api.settings import settings_router
from src.web.log import log


@asynccontextmanager
async def lifespan(application: FastAPI):
    """托管后台初始化，并在应用退出时统一释放资源。"""
    application.state.initialized = False
    application.state.initialization_error = None
    init_task = asyncio.create_task(
        _background_init(application),
        name="backend-initialization",
    )
    application.state.init_task = init_task
    try:
        yield
    finally:
        # 初始化包含在线程中执行的同步设备构建；优先等待它自然结束，
        # 避免取消协程后遗留仍在运行、但已失去所有者的工作线程。
        try:
            if not init_task.done():
                await init_task
        finally:
            await _shutdown_application(application)


def create_app():
    app = FastAPI(
        title="EMS Simulator API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    # 配置CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 请求日志中间件：记录请求方法、路径、状态码、耗时，并注入 trace_id
    # @app.middleware("http")
    # async def request_logging_middleware(request: Request, call_next):
    #     trace_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    #     request.state.trace_id = trace_id

    #     start = time.perf_counter()
    #     try:
    #         response = await call_next(request)
    #     except Exception:
    #         cost = (time.perf_counter() - start) * 1000
    #         log.error(f"[{trace_id}] {request.method} {request.url.path} -> 500 ({cost:.1f}ms) 未捕获异常")
    #         raise

    #     cost = (time.perf_counter() - start) * 1000
    #     # 将 trace_id 回写到响应头，方便前端/日志关联
    #     response.headers["X-Request-ID"] = trace_id
    #     if response.status_code >= 400:
    #         log.warning(f"[{trace_id}] {request.method} {request.url.path} -> {response.status_code} ({cost:.1f}ms)")
    #     else:
    #         log.debug(f"[{trace_id}] {request.method} {request.url.path} -> {response.status_code} ({cost:.1f}ms)")
    #     return response

    # 注册路由
    app.include_router(channel_router)
    app.include_router(device_router)
    app.include_router(point_router)
    app.include_router(point_mapping_router)
    app.include_router(point_tree_router)
    app.include_router(device_group_router)
    app.include_router(scl_router)
    app.include_router(modeling_router)
    app.include_router(settings_router)
    app.include_router(log_router)
    app.include_router(network_interfaces_router)

    # 初始化应用状态
    app.state.initialized = False
    app.state.initialization_error = None
    app.state.init_task = None
    app.state.device_controller = None
    app.state.goose_manager = None
    app.state.scl_file_manager = None
    app.state.scl_import_service = None

    return app


app = create_app()


@app.get("/api/health")
async def health_check(request: Request):
    """
    健康检查端点 - 供 Tauri 桌面客户端检测后端服务是否就绪
    返回后端服务状态、版本信息和数据库连接状态

    状态区分:
    - initialized=False: 服务已启动但设备初始化尚未完成（返回 503）
    - initialized=True: 服务完全就绪（返回 200）
    """
    application = request.app
    initialized = getattr(application.state, "initialized", False)
    initialization_error = getattr(application.state, "initialization_error", None)

    health_data = {
        "status": "ok" if initialized else ("failed" if initialization_error else "initializing"),
        "version": __version__,
        "service": "EMS Simulate Backend",
        "timestamp": None,
        "busy": False,
        "active_operations": [],
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

    # Busy is a healthy state. Expose long-running IEC61850 work separately so
    # clients and diagnostics do not confuse load with process failure.
    controller = getattr(application.state, "device_controller", None)
    if controller is not None:
        for device in tuple(getattr(controller, "device_list", ())):
            get_progress = getattr(device, "get_iec61850_connect_progress", None)
            if not callable(get_progress):
                continue
            try:
                progress = get_progress()
            except Exception:
                continue
            if progress and progress.get("active"):
                health_data["active_operations"].append(
                    {
                        "device": getattr(device, "name", ""),
                        "operation": progress.get("operation", ""),
                        "elapsed_seconds": progress.get("elapsed_seconds", 0),
                    }
                )
        health_data["busy"] = bool(health_data["active_operations"])
        if health_data["busy"]:
            health_data["status"] = "busy"

    if not initialized:
        message = "服务初始化失败，请查看后端日志" if initialization_error else "服务初始化中，请稍后"
        return JSONResponse(
            status_code=503,
            content=BaseResponse(code=503, message=message, data=health_data).model_dump(),
        )

    return BaseResponse(code=Code.SUCCESS, message="服务正常", data=health_data).model_dump()


async def _init_device_controller():
    """后台初始化设备控制器"""
    from src.device_controller import get_device_controller

    return await get_device_controller()


async def _init_goose_manager():
    """后台初始化 GOOSE 管理器"""
    try:
        from src.proto.iec61850.plugins.goose.manager import GooseResourceManager

        goose_manager = GooseResourceManager()
        log.info("GOOSE 管理器初始化成功")

        return goose_manager
    except Exception as e:
        log.warning(f"GOOSE 管理器初始化失败 (GOOSE 功能不可用): {e}")
        return None


async def _background_init(application: FastAPI):
    """后台初始化：设备控制器 + GOOSE 管理器

    不阻塞 uvicorn 端口监听，Tauri 通过 /api/health 检测初始化状态
    """

    t0 = time.perf_counter()
    log.info("开始后台初始化...")

    try:
        # 1. 初始化设备控制器
        device_controller = await _init_device_controller()
        application.state.device_controller = device_controller
        log.info(
            f"设备控制器初始化完成 ({len(device_controller.device_list)} 个设备), 耗时 {time.perf_counter() - t0:.2f}s"
        )

        # 2. 初始化 GOOSE 管理器
        application.state.goose_manager = await _init_goose_manager()

        # 3. 标记初始化完成
        application.state.initialized = True
        application.state.initialization_error = None
        log.info(f"后台初始化全部完成, 总耗时 {time.perf_counter() - t0:.2f}s")

    except asyncio.CancelledError:
        log.info("后台初始化已取消")
        raise
    except Exception as e:
        log.exception(f"后台初始化失败: {e}")
        application.state.initialized = False
        application.state.initialization_error = e


async def _shutdown_application(application: FastAPI) -> None:
    """按依赖顺序关闭网络资源、设备资源和数据库连接池。"""
    try:
        from src.web.api.channel.goose import GOOSE_CAPTURE_INSTANCES
        from src.web.api.channel.goose_websocket import WebSocketSessionManager

        captures = tuple(GOOSE_CAPTURE_INSTANCES.values())
        GOOSE_CAPTURE_INSTANCES.clear()
        for capture in captures:
            try:
                capture.set_callback(None)
            except Exception:
                pass
        await asyncio.gather(*(asyncio.to_thread(capture.stop) for capture in captures))
        await WebSocketSessionManager().shutdown()
    except Exception as exc:
        log.exception(f"关闭 GOOSE 抓包会话失败: {exc}")

    goose_manager = getattr(application.state, "goose_manager", None)
    if goose_manager is not None:
        try:
            await asyncio.to_thread(goose_manager.stop_all)
        except Exception as exc:
            log.exception(f"关闭 GOOSE 资源失败: {exc}")

    try:
        from src.device_controller import shutdown_device_controller

        await shutdown_device_controller()
    except Exception as exc:
        log.exception(f"关闭设备控制器失败: {exc}")

    try:
        from src.data.controller.db import db_controller

        await asyncio.to_thread(db_controller.close_db)
    except Exception as exc:
        log.exception(f"关闭数据库连接池失败: {exc}")

    application.state.device_controller = None
    application.state.goose_manager = None
    application.state.initialized = False


def _error_response(code: int, message: str, data=None, http_status: int | None = None) -> JSONResponse:
    """构造统一格式的错误 JSONResponse"""
    status = (
        http_status
        if http_status is not None
        else (code if code in (200, 400, 401, 403, 404, 405, 409, 422, 500, 503) else 500)
    )
    return JSONResponse(
        status_code=status,
        content=BaseResponse(code=code, message=message, data=data).model_dump(),
    )


def _trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", "-")


@app.exception_handler(BizError)
async def biz_exception_handler(request: Request, exc: BizError):
    """业务异常：按异常自身声明的 code / http_status 返回"""
    message = f"[{_trace_id(request)}] 业务异常: {exc.message} (code={exc.code})"
    if exc.http_status >= 500:
        log.error(message)
    else:
        log.warning(message)
    return _error_response(exc.code, exc.message, exc.data, exc.http_status)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic 请求参数校验失败：返回 422 + 字段级错误详情"""
    errors = exc.errors()
    # 提取可读的错误摘要
    details = []
    for err in errors:
        loc = ".".join(str(p) for p in err.get("loc", []))
        details.append(f"{loc}: {err.get('msg', '')}")
    summary = "; ".join(details) if details else "参数校验失败"
    log.warning(f"[{_trace_id(request)}] 参数校验失败: {summary}")
    return _error_response(Code.VALIDATION_ERROR, summary, {"errors": errors}, 422)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Starlette/FastAPI HTTP 异常（404 路由不存在、405 方法不允许等）"""
    code = exc.status_code
    message = str(exc.detail) if exc.detail else DEFAULT_MESSAGES.get(Code(code), "请求错误")
    log.warning(f"[{_trace_id(request)}] HTTP {code}: {message}")
    return _error_response(code, message, None, code)


@app.exception_handler(Iec61850Error)
async def iec61850_exception_handler(request: Request, exc: Iec61850Error):
    """IEC 61850 协议层异常：映射为友好提示，不泄露内部堆栈"""
    exc_type = type(exc).__name__
    log.error(f"[{_trace_id(request)}] IEC61850 异常 [{exc_type}]: {exc}")
    return _error_response(
        Code.IEC61850_ERROR,
        f"协议操作失败: {exc}",
        None,
        500,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """兜底异常处理器：仅返回通用提示，完整信息写日志"""
    import traceback

    trace_id = _trace_id(request)
    log.error(f"[{trace_id}] 服务器内部错误: {exc}\n{traceback.format_exc()}")
    return _error_response(
        Code.INTERNAL_ERROR,
        f"服务器内部错误 (trace: {trace_id})",
        None,
        500,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="info")
