import pymodbus

print(f"Pymodbus version: {pymodbus.__version__}")

try:
    from pymodbus.bit_read_message import ReadCoilsRequest

    print("Found in pymodbus.bit_read_message")
except ImportError:
    print("Not found in pymodbus.bit_read_message")

try:
    from pymodbus.pdu import ReadCoilsRequest

    print("Found in pymodbus.pdu")
except ImportError:
    print("Not found in pymodbus.pdu")

# Search recursively? No, just check likely spots
import importlib
import inspect

likely_modules = [
    "pymodbus.bit_read_message",
    "pymodbus.bit_write_message",
    "pymodbus.register_read_message",
    "pymodbus.register_write_message",
    "pymodbus.pdu",
    "pymodbus.message.bit_read_message",  # maybe?
]

target_classes = [
    "ReadCoilsRequest",
    "ReadDiscreteInputsRequest",
    "WriteSingleCoilRequest",
    "WriteMultipleCoilsRequest",
    "ReadHoldingRegistersRequest",
    "ReadInputRegistersRequest",
    "WriteSingleRegisterRequest",
    "WriteMultipleRegistersRequest",
    "ModbusRequest",
    "ModbusResponse",
]

found_locations = {}


def check_module(mod_name):
    try:
        mod = importlib.import_module(mod_name)
        for cls_name in target_classes:
            if hasattr(mod, cls_name) and cls_name not in found_locations:
                found_locations[cls_name] = mod_name
                # print(f"Found {cls_name} in {mod_name}")
    except ImportError:
        pass


for m in likely_modules:
    check_module(m)

# Check top level
check_module("pymodbus")

print("\nFound locations:")
for cls, loc in found_locations.items():
    print(f"{cls}: {loc}")
