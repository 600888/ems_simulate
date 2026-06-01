import gc
import threading
import time

from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.iec61850_server import IEC61850Server


def build():
    s = IEC61850Server(port=10102)
    for i in range(100):
        s.add_point(i, 0)
    return s


s = build()
gc.collect()
# Allocate some memory to overwrite freed text
[b"x" * 1000 for _ in range(10000)]
print("Starting server...")
s.start()
print("Server started!")


def client_thread():
    time.sleep(1)
    print("Client connecting...")
    c = IEC61850Client(port=10102)
    try:
        import asyncio

        asyncio.run(c.connect())
        print("Client connected!")
        val = c.read_point(0, 0)
        print(f"Read val: {val}")
    except Exception as e:
        print(f"Client error: {e}")
    finally:
        c.disconnect()


t = threading.Thread(target=client_thread)
t.start()
t.join()

print("DONE")
s.stop()
