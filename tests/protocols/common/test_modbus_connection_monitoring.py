import asyncio
import socket

from loguru import logger

from src.device.core.connection import connection_registry
from src.device.protocol.modbus_handler import ModbusServerHandler
from src.enums.modbus_def import ProtocolType


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_modbus_tcp_request_handler_reports_connect_and_disconnect():
    async def scenario():
        closed = []
        connection_registry.set_event_sink(
            lambda event, snapshot: closed.append(snapshot) if event == "closed" else None
        )
        handler = ModbusServerHandler(logger)
        port = _free_port()
        handler.initialize(
            {
                "channel_id": 1502,
                "protocol_type": ProtocolType.ModbusTcpServer,
                "ip": "127.0.0.1",
                "port": port,
                "slave_id_list": [1],
                "runtime": {},
                "security": {},
            }
        )
        try:
            assert await handler.start()
            for _ in range(50):
                try:
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    break
                except OSError:
                    await asyncio.sleep(0.01)
            else:
                raise AssertionError("Modbus server did not start listening")
            for _ in range(50):
                current = handler.get_current_connections()
                if current:
                    break
                await asyncio.sleep(0.01)
            assert current[0]["remote_ip"] == "127.0.0.1"
            writer.close()
            await writer.wait_closed()
            for _ in range(50):
                if not handler.get_current_connections():
                    break
                await asyncio.sleep(0.01)
            assert handler.get_current_connections() == []
            assert closed[-1].disconnect_reason.value == "remote_closed"
            del reader
        finally:
            await handler.stop()
            connection_registry.set_event_sink(None)

    asyncio.run(scenario())
