"""Debug: simulate the full device initialization flow for IEC61850_SERVER"""

import time

from pyiec61850 import pyiec61850 as iec61850

from src.device.factory.general_device_builder import GeneralDeviceBuilder
from src.device.types.general_device import GeneralDevice
from src.enums.modbus_def import ProtocolType

# 模拟 builder 创建 IEC61850 服务端设备
channel_id = 22
builder = GeneralDeviceBuilder(channel_id=channel_id, device=GeneralDevice())
builder.setDeviceNetConfig(port=10103, ip="0.0.0.0")

# 模拟 makeGeneralDevice
device = builder.makeGeneralDevice(
    device_id=channel_id,
    device_name="IEC61850_SERVER",
    protocol_type=ProtocolType.Iec61850Server,
    is_start=True,
)

print(f"Device: {device.name}")
print(f"Protocol type: {device.protocol_type}")
print(f"Point count: {device.point_manager.get_point_count()}")
print(f"All points: {len(device.point_manager.get_all_points())}")

# 检查 server handler 中的 points
if device.protocol_handler and device.protocol_handler._server:
    server = device.protocol_handler._server
    print(f"Server point_refs count: {len(server._point_refs)}")
    print(f"Server point_attrs count: {len(server._point_attrs)}")
    # 打印前5个 ref
    for i, (key, ref) in enumerate(server._point_refs.items()):
        if i >= 5:
            break
        print(f"  ref[{i}]: address={key[0]}, frame_type={key[1]}, ref={ref}")

# 用客户端连接测试
time.sleep(0.5)
conn = iec61850.IedConnection_create()
result = iec61850.IedConnection_connect(conn, "127.0.0.1", 10103)
error = result if not isinstance(result, (list, tuple)) else result[1]

if error == 0:
    result = iec61850.IedConnection_getLogicalDeviceList(conn)
    ld_list = result[0] if isinstance(result, (list, tuple)) else result
    lds = []
    it = iec61850.LinkedList_getNext(ld_list)
    while it:
        lds.append(iec61850.toCharP(it.data))
        it = iec61850.LinkedList_getNext(it)
    iec61850.LinkedList_destroy(ld_list)
    print(f"LDs: {lds}")

iec61850.IedConnection_destroy(conn)

# 停止设备
import asyncio

asyncio.run(device.stop())
print("Done")
