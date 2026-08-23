import asyncio

from src.proto.dnp3.tracked_tcp_server import TrackedTcpServer


def test_tracked_tcp_server_reports_lifecycle_and_activity():
    async def scenario():
        events = []
        server = TrackedTcpServer(
            host="127.0.0.1",
            port=0,
            on_connect=lambda key, peer, local: events.append(("connect", key, peer, local)),
            on_activity=lambda key, direction, size: events.append(("activity", key, direction, size)),
            on_disconnect=lambda key, reason, detail: events.append(("disconnect", key, reason, detail)),
        )
        await server.open()
        port = server._server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"\x05\x64")
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.close()
        await writer.wait_closed()
        for _ in range(20):
            if any(event[0] == "disconnect" for event in events):
                break
            await asyncio.sleep(0.01)
        await server.close()
        assert reader.at_eof() or any(event[0] == "disconnect" for event in events)
        return events

    events = asyncio.run(scenario())
    assert events[0][0] == "connect"
    assert ("activity", events[0][1], "rx", 2) in events
    assert any(event[0] == "disconnect" and event[2] == "remote_closed" for event in events)
