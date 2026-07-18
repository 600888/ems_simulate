try:
    from src.proto.pyModbus.client.modbus_client import ModbusClient

    print("Successfully imported ModbusClient")
except ImportError as e:
    print(f"Error importing ModbusClient: {e}")

try:
    from src.proto.pyModbus.server.modbus_server import ModbusServer

    print("Successfully imported ModbusServer")
except ImportError as e:
    print(f"Error importing ModbusServer: {e}")
