try:
    from src.proto.pyModbus.client.async_client import AsyncModbusClient

    print("Successfully imported AsyncModbusClient")
except ImportError as e:
    print(f"Error importing AsyncModbusClient: {e}")
