try:
    from pymodbus.framer.socket_framer import ModbusSocketFramer

    print("Found ModbusSocketFramer in pymodbus.framer.socket_framer")
except ImportError as e:
    print(f"Error importing ModbusSocketFramer from submodule: {e}")

try:
    from pymodbus.framer.rtu_framer import ModbusRtuFramer

    print("Found ModbusRtuFramer in pymodbus.framer.rtu_framer")
except ImportError as e:
    print(f"Error importing ModbusRtuFramer from submodule: {e}")

try:
    from pymodbus.server import ModbusTcpServer

    print("Found ModbusTcpServer")
except ImportError as e:
    print(f"Error importing ModbusTcpServer: {e}")

try:
    from pymodbus.server import StartAsyncTcpServer

    print("Found StartAsyncTcpServer")
except ImportError as e:
    print(f"Error importing StartAsyncTcpServer: {e}")

import pymodbus.server

print("pymodbus.server dir:", dir(pymodbus.server))
