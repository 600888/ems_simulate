import asyncio
import socket
from unittest.mock import Mock

from src.proto.iec104.iec104client import IEC104Client
from src.proto.iec104.iec104server import IEC104Server


def test_peer_closing_before_startdt_fails_without_native_retry_loop(monkeypatch):
    protocol_log = Mock()
    monkeypatch.setattr("src.proto.iec104.iec104client.log", protocol_log)

    async def scenario():
        accepted = []

        async def reject(reader, writer):
            accepted.append(writer)
            try:
                await reader.read(6)
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(reject, "127.0.0.1", 0)
        client = IEC104Client(port=server.sockets[0].getsockname()[1])
        try:
            assert await client.connect(timeout=3) is False
            assert "STARTDT" in client.last_error
            assert client.client.is_running is False
            await asyncio.sleep(1.1)
            assert len(accepted) == 1
            protocol_log.error.assert_called_once()
            protocol_log.info.assert_not_called()
        finally:
            await asyncio.to_thread(client.disconnect)
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_tcp_without_startdt_confirmation_times_out_and_cleans_up(monkeypatch):
    protocol_log = Mock()
    monkeypatch.setattr("src.proto.iec104.iec104client.log", protocol_log)

    async def scenario():
        writers = []

        def accept(_reader, writer):
            writers.append(writer)

        server = await asyncio.start_server(accept, "127.0.0.1", 0)
        client = IEC104Client(port=server.sockets[0].getsockname()[1])
        try:
            assert await client.connect(timeout=0.3) is False
            assert "连接超时" in client.last_error
            assert client.client.is_running is False
            protocol_log.error.assert_called_once()
            protocol_log.info.assert_not_called()
        finally:
            await asyncio.to_thread(client.disconnect)
            for writer in writers:
                writer.close()
                await writer.wait_closed()
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_established_connection_loss_stops_native_retry_and_allows_manual_restart(monkeypatch):
    protocol_log = Mock()
    monkeypatch.setattr("src.proto.iec104.iec104client.log", protocol_log)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = IEC104Server(ip="127.0.0.1", port=port)
    server.get_station(1)
    client = IEC104Client(port=port)
    client.get_station(1)

    async def scenario():
        try:
            server.start()
            assert await client.connect(timeout=3) is True
            await asyncio.to_thread(server.stop)

            async def wait_for_cleanup():
                while client._transport_stop_task is None:
                    await asyncio.sleep(0.02)
                await client._transport_stop_task

            await asyncio.wait_for(wait_for_cleanup(), timeout=3)
            assert client.client.is_running is False
            protocol_log.error.assert_called_once()
            server.start()
            assert await client.connect(timeout=3) is True, (client.last_error, protocol_log.mock_calls)
            assert client.last_error == ""
        finally:
            await asyncio.to_thread(client.disconnect)
            await asyncio.to_thread(server.stop)

    asyncio.run(scenario())
