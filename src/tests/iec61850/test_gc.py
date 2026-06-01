import gc
import threading
import time

import pyiec61850.pyiec61850 as pyiec61850

from src.proto.iec61850.iec61850_server import IEC61850Server


def build():
    s = IEC61850Server()
    # Add points to create many DataObjects with dynamic names
    for i in range(1000):
        s.add_point(i, 0)
    return s


s = build()
gc.collect()
# Overwrite small string allocator memory
garbage = [f"GARBAGE_STRING_{i}" for i in range(100000)]

print("Starting server...")
s.start()
print("Server started!")

# Now trigger some MMS actions or just let the background thread process the garbage
time.sleep(2)
print("DONE")
