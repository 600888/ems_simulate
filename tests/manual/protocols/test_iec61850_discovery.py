import asyncio
import time

from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.iec61850_server import IEC61850Server
from src.proto.iec61850.log import log


async def test_discovery():
    # 1. 启动服务器
    server = IEC61850Server(port=10102, model_name="TEST", ld_name="LD0")

    # 添加一些测点
    server.add_point(address=1, frame_type=0)  # 遥测
    server.add_point(address=2, frame_type=1)  # 遥信
    server.add_point(address=3, frame_type=2)  # 遥控
    server.add_point(address=4, frame_type=3)  # 遥调

    server.start()
    time.sleep(1)

    try:
        # 2. 启动客户端
        client = IEC61850Client(port=10102, model_name="TEST", ld_name="LD0")
        connected = await client.connect()

        if not connected:
            print("Failed to connect to server")
            return

        print(f"Connected. Discovered points: {len(client._point_refs)}")
        for addr, ref in client._point_refs.items():
            fc = client._point_fc.get(addr, "")
            iec_type = client._point_iec_type.get(addr, "")
            print(f"Point {addr}: ref={ref}, fc={fc}, iec_type={iec_type}")

        # 3. 验证映射是否正确
        expected_points = [1, 2, 3, 4]

        for p in expected_points:
            if str(p) in client._point_refs:
                print(f"✓ Point {p} correctly discovered: {client._point_refs[str(p)]}")
            else:
                print(f"✗ Point {p} NOT discovered")

        # 4. 测试读取（使用新的 fc 参数）
        server.set_point_value(address=1, value=123.45, fc="MX")
        val = client.read_point(address=1, fc="MX")
        print(f"Read point 1 value: {val} (expected 123.45)")

    finally:
        server.stop()
        server.destroy()


if __name__ == "__main__":
    asyncio.run(test_discovery())
