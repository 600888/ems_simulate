# -*- coding: utf-8 -
import uvicorn
import asyncio
import os
from fastapi.staticfiles import StaticFiles
from src.web.app import app
from src.device_controller import get_device_controller
from src.enums.modbus_def import ProtocolType
from src.config.config import Config

async def init_device_controller():
    """初始化设备控制器，在有事件循环的环境下启动Modbus TCP服务器"""
    device_controller = await get_device_controller()

async def main():
    # 获取当前脚本的绝对路径目录
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
    await server.serve()


if __name__ == "__main__":
    # 使用asyncio.run运行主协程
    asyncio.run(main())
