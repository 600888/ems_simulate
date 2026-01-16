# -*- coding: utf-8 -
import uvicorn
import asyncio
from fastapi.staticfiles import StaticFiles
from src.web.app import app
from src.device_controller import get_device_controller
from src.enums.modbus_def import ProtocolType


async def init_device_controller():
    """初始化设备控制器，在有事件循环的环境下启动Modbus TCP服务器"""
    device_controller = await get_device_controller()
    
    # 启动所有需要启动的Modbus TCP服务器
    for device in device_controller.device_list:
        if device.protocol_type == ProtocolType.ModbusTcp:
            await device.start()


async def main():
    app.mount("/", StaticFiles(directory="./www/dist", html=True), name="static")
    # 先初始化设备控制器，确保设备都已创建
    await init_device_controller()
    
    # 启动后端服务器
    config = uvicorn.Config(
        app, 
        host="0.0.0.0", 
        port=8888, 
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    # 使用asyncio.run运行主协程
    asyncio.run(main())
