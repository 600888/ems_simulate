from src.device.core.connection import connection_registry
from src.device.protocol.iec61850_handler import IEC61850ServerHandler
from src.enums.modbus_def import ProtocolType


def test_mms_connection_indication_maps_native_endpoint_and_lifecycle():
    handler = IEC61850ServerHandler()
    handler._configure_connection_monitoring(
        {"channel_id": 161850, "protocol_type": ProtocolType.Iec61850Server},
        supported=True,
    )
    closed = []
    connection_registry.set_event_sink(lambda event, snapshot: closed.append(snapshot) if event == "closed" else None)
    try:
        handler._on_connection_state_change("mms:1", True, "192.0.2.4:49152", "10.0.0.1:102")
        current = handler.get_current_connections()
        assert current[0]["remote_ip"] == "192.0.2.4"
        assert current[0]["remote_port"] == 49152
        assert current[0]["local_port"] == 102

        handler._on_connection_state_change("mms:1", False, "192.0.2.4:49152", "10.0.0.1:102")
        assert handler.get_current_connections() == []
        assert closed[-1].disconnect_reason.value == "remote_closed"
    finally:
        handler._close_all_connections()
        connection_registry.set_event_sink(None)
