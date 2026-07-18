import os
import sys

print(f"CWD: {os.getcwd()}")
print(f"sys.path: {sys.path}")

try:
    import pymodbus

    print(f"pymodbus version: {pymodbus.__version__}")
except ImportError as e:
    print(f"Failed to import pymodbus: {e}")

try:
    from pymodbus.server import ModbusTcpServer

    print("Imported ModbusTcpServer")
except ImportError as e:
    print(f"Failed to import ModbusTcpServer: {e}")

try:
    from pymodbus.framer import FramerSocket

    print("Imported FramerSocket")
except ImportError as e:
    print(f"Failed to import FramerSocket: {e}")

try:
    from src.proto.pyModbus.server.capture import CreateCaptureSocketFramer

    print("Imported CreateCaptureSocketFramer")
except ImportError as e:
    print(f"Failed to import CreateCaptureSocketFramer: {e}")
except Exception as e:
    print(f"Error importing capture: {e}")
