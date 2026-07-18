try:
    from pymodbus.framer import Framer

    print("Found Framer in pymodbus.framer")
except ImportError as e:
    print(f"Error importing Framer: {e}")

try:
    from pymodbus.framer import ModbusSocketFramer

    print("Found ModbusSocketFramer in pymodbus.framer")
except ImportError as e:
    print(f"Error importing ModbusSocketFramer: {e}")

try:
    from pymodbus.framer import ModbusRtuFramer

    print("Found ModbusRtuFramer in pymodbus.framer")
except ImportError as e:
    print(f"Error importing ModbusRtuFramer: {e}")

import pymodbus

print(f"Pymodbus version: {pymodbus.__version__}")
