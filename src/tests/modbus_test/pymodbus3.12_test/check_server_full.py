import sys

with open("server_check_output.txt", "w") as f:
    try:
        from pymodbus.framer import FramerRTU

        print("FramerRTU found in pymodbus.framer", file=f)
    except ImportError as e:
        print(f"Error importing FramerRTU: {e}", file=f)

    try:
        from pymodbus.server import ModbusTcpServer

        print("Found ModbusTcpServer", file=f)
    except ImportError as e:
        print(f"Error importing ModbusTcpServer: {e}", file=f)

    try:
        from pymodbus.server import StartAsyncTcpServer

        print("Found StartAsyncTcpServer", file=f)
    except ImportError as e:
        print(f"Error importing StartAsyncTcpServer: {e}", file=f)

    import pymodbus.server

    print(f"pymodbus.server contents: {dir(pymodbus.server)}", file=f)
