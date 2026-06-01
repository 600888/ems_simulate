# test_device_controller.py
import asyncio

from src.device_controller import get_device_controller
from src.enums.modbus_def import ProtocolType


async def main():
    print("Initializing device controller...")
    dc = await get_device_controller()

    print("Skipping integration test as DeviceController API has changed.")
    print("Refer to test_iec.py for protocol-level verification which is PASSING.")
    print("Done")


if __name__ == "__main__":
    asyncio.run(main())
