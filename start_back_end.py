# -*- coding: utf-8 -
import sys
import os
import logging

# ⭐ Windows 打包环境下将 stdout/stderr 重定向到日志文件，避免控制台闪现
if sys.platform.startswith('win') and getattr(sys, 'frozen', False):
    _log_dir = os.path.join(os.path.dirname(sys.executable), 'logs')
    os.makedirs(_log_dir, exist_ok=True)
    sys.stdout = open(os.path.join(_log_dir, 'backend.log'), 'a', encoding='utf-8')
    sys.stderr = sys.stdout
    logging.basicConfig(
        filename=os.path.join(_log_dir, 'app_error.log'),
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)s: %(message)s',
    )

import uvicorn
import asyncio
from fastapi.staticfiles import StaticFiles
from src.web.app import app
from src.device_controller import get_device_controller
from src.config.config import Config

async def init_device_controller():
    """初始化设备控制器，在有事件循环的环境下启动Modbus TCP服务器"""
    device_controller = await get_device_controller()

async def main():
    # 获取静态文件目录（兼容开发 / PyInstaller 打包模式）
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(base_dir, "www")

    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    # 先初始化设备控制器，确保设备都已创建
    await init_device_controller()

    # 启动后端服务器
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=Config.web_port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    print(f"\nAPI Documentation (Swagger UI): http://127.0.0.1:{Config.web_port}/docs")
    print(f"Redoc Documentation: http://127.0.0.1:{Config.web_port}/redoc\n")

    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logging.exception("程序发生异常:")
