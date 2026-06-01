import pymodbus.server

print("pymodbus.server:", dir(pymodbus.server))

import pymodbus.device

print("pymodbus.device:", dir(pymodbus.device))

try:
    from pymodbus.device import ModbusDeviceIdentification

    print("Found ModbusDeviceIdentification")
except ImportError:
    print("ModbusDeviceIdentification NOT found in pymodbus.device")

try:
    from pymodbus.server import ModbusServerRequestHandler

    print("Found ModbusServerRequestHandler")
except ImportError:
    print("ModbusServerRequestHandler NOT found in pymodbus.server")
