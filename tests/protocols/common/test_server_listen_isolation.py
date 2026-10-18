"""Real TCP listeners on distinct local IPs must not share connections."""

import asyncio
import contextlib
import socket
from types import SimpleNamespace

from loguru import logger
import pytest

from src.device.protocol.dlt645_handler import DLT645ServerHandler
from src.device.protocol.dnp3_handler import DNP3ServerHandler
from src.device.protocol.iec61850_handler import IEC61850ServerHandler
from src.device.protocol.modbus_handler import ModbusServerHandler
from src.enums.modbus_def import ProtocolType
from src.web.api.channel.helpers import configure_builder_network


@pytest.mark.parametrize(
    ("handler_class", "protocol"),
    [
        (ModbusServerHandler, ProtocolType.ModbusTcpServer),
        (DLT645ServerHandler, ProtocolType.Dlt645Server),
        (DNP3ServerHandler, ProtocolType.Dnp3Server),
        (IEC61850ServerHandler, ProtocolType.Iec61850Server),
    ],
)
def test_distinct_server_ips_share_port_without_taking_over_connections(handler_class, protocol):
    async def scenario():
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        handlers = []
        writers = []
        try:
            for index, ip in enumerate(("127.0.0.1", "127.0.0.2")):
                config = {
                    "channel_id": 1950 + index,
                    "protocol_type": protocol,
                    "conn_type": 2,
                    "slave_id_list": [1],
                    "ied_name": "IED1",
                }
                builder = SimpleNamespace(setDeviceNetConfig=config.update)
                configure_builder_network(builder, 2, protocol, ip, port, {})
                handler = handler_class(logger)
                handlers.append(handler)
                handler.initialize(config)
                if protocol == ProtocolType.Iec61850Server:
                    from src.proto.iec61850.plugins.scl.service.import_service import SclImportService

                    result = SclImportService().import_string(
                        """<SCL>
                        <IED name="IED1"><AccessPoint name="AP1"><Server><LDevice inst="LD0">
                          <LN0 lnClass="LLN0" lnType="LLN0Type" />
                          <LN lnClass="MMXU" inst="1" lnType="MMXUType" />
                        </LDevice></Server></AccessPoint></IED>
                        <DataTypeTemplates>
                          <LNodeType id="LLN0Type" lnClass="LLN0" />
                          <LNodeType id="MMXUType" lnClass="MMXU"><DO name="TotW" type="MVType" /></LNodeType>
                          <DOType id="MVType" cdc="MV"><DA name="mag" fc="MX" bType="Struct" type="AV" /></DOType>
                          <DAType id="AV"><BDA name="f" bType="FLOAT32" /></DAType>
                        </DataTypeTemplates></SCL>""",
                        validate=False,
                    )
                    assert handler.load_model("unused.icd", scl_result=result)
                assert await handler.start(), f"Could not listen on {ip}:{port}"

            for ip in ("127.0.0.1", "127.0.0.2"):
                for _ in range(100):
                    try:
                        _, writer = await asyncio.open_connection(ip, port)
                        writers.append(writer)
                        break
                    except OSError:
                        await asyncio.sleep(0.01)
                else:
                    pytest.fail(f"Server did not listen on {ip}:{port}")

            # MMS monitoring starts after association; raw TCP is sufficient
            # here to check that both native listeners can bind the same port.
            if protocol != ProtocolType.Iec61850Server:
                for _ in range(100):
                    connections = [handler.get_current_connections() for handler in handlers]
                    if all(len(items) == 1 for items in connections):
                        break
                    await asyncio.sleep(0.01)
                for index, ip in enumerate(("127.0.0.1", "127.0.0.2")):
                    assert len(connections[index]) == 1
                    assert connections[index][0]["local_ip"] == ip

            await handlers[0].stop()
            try:
                _, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 0.5)
            except (OSError, TimeoutError):
                pass
            else:
                writers.append(writer)
                pytest.fail("Surviving server took over the stopped server's IP")
            _, writer = await asyncio.open_connection("127.0.0.2", port)
            writers.append(writer)
        finally:
            for writer in writers:
                writer.close()
                with contextlib.suppress(OSError):
                    await writer.wait_closed()
            for handler in handlers:
                await handler.stop()
                if protocol == ProtocolType.Iec61850Server:
                    handler.server.destroy()

    asyncio.run(scenario())
