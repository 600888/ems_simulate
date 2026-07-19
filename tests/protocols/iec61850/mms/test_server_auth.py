"""End-to-end IEC 61850 ACSE password authentication tests."""

import socket

from src.proto.iec61850.core.connection import (
    Iec61850AssociationParameters,
    Iec61850Connection,
    Iec61850Timeouts,
)
from src.proto.iec61850.iec61850_server import IEC61850Server
from src.proto.iec61850.plugins.scl.service.import_service import SclImportService

_MINIMAL_SCL = """
<SCL>
  <IED name="IED1"><AccessPoint name="AP1"><Server><LDevice inst="LD0">
    <LN0 lnClass="LLN0" lnType="LLN0Type" />
    <LN lnClass="MMXU" inst="1" lnType="MMXUType"><DOI name="TotW" /></LN>
  </LDevice></Server></AccessPoint></IED>
  <DataTypeTemplates>
    <LNodeType id="LLN0Type" lnClass="LLN0" />
    <LNodeType id="MMXUType" lnClass="MMXU"><DO name="TotW" type="MVType" /></LNodeType>
    <DOType id="MVType" cdc="MV">
      <DA name="mag" fc="MX" bType="Struct" type="AnalogueValue" />
    </DOType>
    <DAType id="AnalogueValue"><BDA name="f" bType="FLOAT32" /></DAType>
  </DataTypeTemplates>
</SCL>
"""


def _available_port() -> int:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def _connect(port: int, password: str | None) -> bool:
    params = Iec61850AssociationParameters(
        authentication_enabled=password is not None,
        authentication_password=password or "",
    )
    connection = Iec61850Connection(
        "127.0.0.1",
        port,
        timeouts=Iec61850Timeouts(connect_ms=1000, request_ms=1000),
        association_parameters=params,
        poll_authentication_callback=True,
    )
    try:
        return connection.connect(auto_discover=False)
    finally:
        connection.disconnect()


def test_server_rejects_missing_and_wrong_password_but_accepts_correct_password():
    port = _available_port()
    result = SclImportService().import_string(_MINIMAL_SCL, validate=False)
    server = IEC61850Server(
        ip="127.0.0.1",
        port=port,
        model_name="IED1",
        ied_name="IED1",
        authentication_enabled=True,
        authentication_password="server-secret",
    )
    try:
        assert server.load_model("unused.icd", scl_result=result)
        server.start()
        assert server.is_running

        assert _connect(port, None) is False
        assert _connect(port, "wrong-secret") is False
        assert _connect(port, "server-secret") is True
    finally:
        server.destroy()
