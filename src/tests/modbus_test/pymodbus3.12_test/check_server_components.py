try:
    from pymodbus.server.async_io import ModbusServerRequestHandler

    print("Found ModbusServerRequestHandler")
except ImportError as e:
    print(f"Error importing ModbusServerRequestHandler: {e}")

try:
    from pymodbus.device import ModbusDeviceIdentification

    print("Found ModbusDeviceIdentification")
except ImportError as e:
    print(f"Error importing ModbusDeviceIdentification: {e}")

try:
    from pymodbus.datastore import ModbusSequentialDataBlock

    print("Found ModbusSequentialDataBlock")
except ImportError as e:
    print(f"Error importing ModbusSequentialDataBlock: {e}")
