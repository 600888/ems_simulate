from src.enums.modbus_def import ProtocolType, get_protocol_type_by_value


def test_modbus_tcp_server_uses_explicit_enum_value():
    assert ProtocolType.ModbusTcpServer.value == "ModbusTcpServer"


def test_legacy_modbus_tcp_value_remains_readable():
    assert get_protocol_type_by_value("ModbusTcp") is ProtocolType.ModbusTcpServer
