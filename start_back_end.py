import logging
import os
import sys

# ⭐ Windows 打包环境下将 stdout/stderr 重定向到日志文件，避免控制台闪现
if sys.platform.startswith('win') and getattr(sys, 'frozen', False):
    # MSIX 安装模式下可执行文件目录为只读，需使用 EMS_ROOT_DIR（Tauri 侧设置的可写数据目录）
    _root = os.environ.get('EMS_ROOT_DIR', os.path.dirname(sys.executable))
    _log_dir = os.path.join(_root, 'logs')
    os.makedirs(_log_dir, exist_ok=True)
    sys.stdout = open(os.path.join(_log_dir, 'backend.log'), 'a', encoding='utf-8')
    sys.stderr = sys.stdout
    logging.basicConfig(
        filename=os.path.join(_log_dir, 'app_error.log'),
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)s: %(message)s',
    )

import asyncio

from fastapi.staticfiles import StaticFiles
import uvicorn

from src.config.config import Config
from src.web.app import app


async def main():
    # 获取静态文件目录（兼容开发 / PyInstaller 打包模式）
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(base_dir, "www")

    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    # 设备初始化已移至 FastAPI startup_event 中后台执行，
    # uvicorn 先启动监听端口，Tauri 可更快检测到后端就绪

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
