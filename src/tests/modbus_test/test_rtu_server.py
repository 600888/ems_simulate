"""
简化测试 Modbus RTU 服务器的数据更新行为
"""
import asyncio
import sys
import logging

# 禁用所有日志
logging.disable(logging.CRITICAL)

sys.path.insert(0, '.')

from src.proto.pyModbus.server import ModbusServer
from src.enums.modbus_def import ProtocolType

# 创建一个简单的 logger 替代品
class NullLogger:
    def info(self, msg): pass
    def debug(self, msg): pass
    def error(self, msg): print(f"ERROR: {msg}")
    def warning(self, msg): pass

async def test_rtu_datastore():
    server = ModbusServer(
        logger=NullLogger(),
        slave_id_list=[1, 2],
        port=502,
        protocol_type=ProtocolType.ModbusRtu,
        serial_port="COM6",
        baudrate=9600,
        bytesize=8,
        parity="E",
        stopbits=1,
    )
    
    print(f"slaves: {list(server.slaves.keys())}")
    
    # 启动前设置值
    server.setValueByAddress(3, 1, 0, 100, "0x41")
    value1 = server.getValueByAddress(3, 1, 0, "0x41")
    print(f"启动前: 设置100, 读取={value1}")
    
    # 启动服务器
    task = asyncio.create_task(server.start())
    await asyncio.sleep(2)
    
    print(f"server.is_running = {server.is_running}")
    print(f"server.server 存在 = {server.server is not None}")
    
    # 运行中设置值
    server.setValueByAddress(3, 1, 0, 200, "0x41")
    value2 = server.getValueByAddress(3, 1, 0, "0x41")
    print(f"运行中: 设置200, 读取={value2}")
    
    # 检查 context 是否共享
    if server.server:
        is_same = server.context is server.server.context
        print(f"context 是否共享: {is_same}")
        
        server_val = server.server.context[1].getValues(3, 0, 2)
        print(f"server.server.context 值: {server_val}")
    
    # 停止
    try:
        await asyncio.wait_for(server.stopAsync(), timeout=2)
    except:
        pass
    
    print("测试完成")

if __name__ == "__main__":
    asyncio.run(test_rtu_datastore())
