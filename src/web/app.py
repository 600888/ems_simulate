from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.web.device.device_controller import device_router
from src.web.channel.channel_controller import channel_router
from src.web.device_group.device_group_controller import device_group_router
from src.device_controller import get_device_controller
from src.web.schemas import BaseResponse
from src.web.log import log

def create_app():
    app = FastAPI(title="EMS Simulator API")
    
    # 配置CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 在生产环境中应该指定具体的前端域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 注册路由
    app.include_router(device_router, prefix="")
    app.include_router(channel_router, prefix="")
    app.include_router(device_group_router, prefix="")
    return app


app = create_app()


@app.on_event("startup")
async def startup_event():
    """FastAPI启动事件，初始化设备控制器"""
    app.state.device_controller = await get_device_controller()
    return app.state.device_controller


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
