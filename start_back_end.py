# -*- coding: utf-8 -
import uvicorn
import asyncio
import os
import sys
from fastapi.staticfiles import StaticFiles
from src.web.app import app
from src.device_controller import get_device_controller
from src.enums.modbus_def import ProtocolType
from src.config.config import Config

# PyInstaller --noconsole 模式下 sys.stdout/stderr 为 None，
# 需要替换为空写入器以避免 print() / logging 报错
class _NullWriter:
    def write(self, *args, **kwargs): pass
    def flush(self, *args, **kwargs): pass
    def fileno(self): return -1

if sys.stdout is None:
    sys.stdout = _NullWriter()
if sys.stderr is None:
    sys.stderr = _NullWriter()

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
        log_level="info"
    )
    server = uvicorn.Server(config)

    # 打印Swagger文档地址
    print(f"\nAPI Documentation (Swagger UI): http://127.0.0.1:{Config.web_port}/docs")
    print(f"Redoc Documentation: http://127.0.0.1:{Config.web_port}/redoc\n")

    await server.serve()


if __name__ == "__main__":
    # 使用asyncio.run运行主协程
    asyncio.run(main())
