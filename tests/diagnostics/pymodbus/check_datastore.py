import pymodbus.datastore

print("pymodbus.datastore contents:", dir(pymodbus.datastore))
try:
    from pymodbus.datastore import ModbusSequentialDataBlock

    print("Found ModbusSequentialDataBlock")
except ImportError as e:
    print(f"Error importing ModbusSequentialDataBlock: {e}")

try:
    from pymodbus.datastore import ModbusServerContext

    print("Found ModbusServerContext")
except ImportError as e:
    print(f"Error importing ModbusServerContext: {e}")

try:
    from pymodbus.datastore import ModbusSlaveContext

    print("Found ModbusSlaveContext")
except ImportError as e:
    print(f"Error importing ModbusSlaveContext: {e}")
