"""
简化诊断脚本
"""
import asyncio
import sys
import logging

# 禁用所有日志
logging.disable(logging.CRITICAL)

sys.path.insert(0, '.')

# 避免 loguru 输出
import loguru
loguru.logger.disable("")

from src.device.factory.general_device_builder import GeneralDeviceBuilder
from src.device.types.general_device import GeneralDevice
from src.enums.modbus_def import ProtocolType

class NullLog:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): print(f"ERROR: {a}")

async def test():
    builder = GeneralDeviceBuilder(channel_id=1, device=GeneralDevice())
    builder.setDeviceSerialConfig("COM6", 9600, 8, 1, "E")
    
    device = builder.makeGeneralDevice(
        device_id=1,
        device_name="测试",
        protocol_type=ProtocolType.ModbusRtu,
        is_start=False
    )
    device.log = NullLog()
    
    print(f"slave_id_list: {device.slave_id_list}")
    print(f"测点数: {len(device.point_manager.code_map)}")
    
    if len(device.point_manager.code_map) == 0:
        print("没有测点!")
        return
    
    first_code = list(device.point_manager.code_map.keys())[0]
    point = device.point_manager.code_map[first_code]
    
    print(f"测点: {first_code}, rtu_addr={point.rtu_addr}, addr={point.address}")
    print(f"初始值: {point.value}")
    
    # 启动
    await device.start()
    await asyncio.sleep(1)
    
    print(f"服务运行: {device.is_protocol_running}")
    
    # 编辑
    result = device.editPointData(first_code, 999.0)
    print(f"编辑结果: {result}")
    print(f"编辑后 point.value: {point.value}")
    
    # 从 server 读取
    if device.protocol_handler and hasattr(device.protocol_handler, '_server'):
        s = device.protocol_handler._server
        print(f"server.slaves: {list(s.slaves.keys())}")
        
        if point.rtu_addr in s.slaves:
            v = s.getValueByAddress(point.func_code, point.rtu_addr, point.address, point.decode)
            print(f"server 读取值: {v}")
        else:
            print(f"rtu_addr {point.rtu_addr} 不在 slaves 中!")
    
    await device.stop()
    print("完成")

if __name__ == "__main__":
    asyncio.run(test())
