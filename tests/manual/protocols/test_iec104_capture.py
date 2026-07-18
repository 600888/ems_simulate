import time

import c104

from src.config.log.logger import Log
from src.proto.iec104.iec104client import IEC104Client
from src.proto.iec104.iec104server import IEC104Server

# Configure logger just in case
logger = Log()

import asyncio


async def test_capture():
    print("Starting IEC104 Capture Test...")

    # 1. Start Server
    server = IEC104Server(ip="127.0.0.1", port=2499)
    # Add a point to monitor
    server.add_monitoring_point(io_address=11, common_address=1)
    server.start()
    print("Server started on port 2499")

    # 2. Start Client
    client = IEC104Client(ip="127.0.0.1", port=2499)
    print("Connecting client...")

    if await client.connect():
        print("Client connected!")

        # Give some time for startup sequence (STARTDT etc)
        await asyncio.sleep(2)

        # 3. Check for handshake messages
        client_msgs = client.get_captured_messages()
        server_msgs = server.get_captured_messages()

        print(f"Client captured {len(client_msgs)} messages")
        print(f"Server captured {len(server_msgs)} messages")

        assert len(client_msgs) > 0, "Client should have captured handshake messages"
        assert len(server_msgs) > 0, "Server should have captured handshake messages"

        # 4. Perform Data Transmission (Server sets value -> Client receives)
        print("Setting point value on server...")
        server.set_point_value(io_address=11, value=12.34, frame_type=0)
        await asyncio.sleep(1)

        # Check client capture update
        client_msgs_after = client.get_captured_messages()
        print(f"Client captured total {len(client_msgs_after)} messages after update")

        # Verify last message contains data
        last_msg = client_msgs_after[-1]
        print(f"Last Client Message: {last_msg}")

    else:
        print("Failed to connect client")

    # Clean up
    client.disconnect()
    server.stop()
    print("Test Finished")


if __name__ == "__main__":
    asyncio.run(test_capture())
