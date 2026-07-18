import asyncio
import os
import sys

sys.path.append(os.getcwd())

from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.framer import FRAMER_NAME_TO_CLASS
from pymodbus.server import ModbusTcpServer

from src.device.core.message.message_capture import MessageCapture
from src.proto.pyModbus.server.capture import CreateCaptureSocketFramer


async def test_server_init():
    try:
        print("Testing ModbusTcpServer instantiation with custom framer key...")
        capture = MessageCapture()
        framer_cls = CreateCaptureSocketFramer(capture)
        framer_key = "TEST_CAPTURE_FRAMER"
        FRAMER_NAME_TO_CLASS[framer_key] = framer_cls

        server = ModbusTcpServer(
            context=ModbusServerContext(devices=ModbusDeviceContext(di=ModbusSequentialDataBlock(0, [17] * 100))),
            address=("127.0.0.1", 50201),
            framer=framer_key,
        )

        print("ModbusTcpServer instantiated successfully with custom framer key.")
        server.server_close()
    except Exception as e:
        print(f"Failed to instantiate ModbusTcpServer: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_server_init())
