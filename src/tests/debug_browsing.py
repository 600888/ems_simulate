import asyncio
import time

from src.proto.iec61850 import pyiec61850 as iec61850
from src.proto.iec61850.iec61850_server import IEC61850Server


async def debug_browsing():
    server = IEC61850Server(port=10103, model_name="DEBUG", ld_name="LD0")
    server.add_point(address=1, frame_type=0)
    server.start()
    time.sleep(1)

    conn = iec61850.IedConnection_create()
    iec61850.IedConnection_connect(conn, "127.0.0.1", 10103)

    try:
        ld = "DEBUGLD0"
        ln = "MMXU1"
        ln_ref = f"{ld}/{ln}"

        print(f"Testing browsing for {ln_ref}")
        for i in range(0, 5):
            result = iec61850.IedConnection_getLogicalNodeDirectory(conn, ln_ref, i)
            items = []
            if isinstance(result, tuple):
                lst, err = result
                if err == 0:
                    it = iec61850.LinkedList_getNext(lst)
                    while it:
                        items.append(iec61850.toCharP(it.data))
                        it = iec61850.LinkedList_getNext(it)
                    iec61850.LinkedList_destroy(lst)
            print(f"Class {i}: {items}")

        # Try with dot
        ln_ref_dot = f"{ld}.{ln}"
        print(f"Testing browsing for {ln_ref_dot}")
        result = iec61850.IedConnection_getLogicalNodeDirectory(conn, ln_ref_dot, 1)
        print(f"Class 1 (dot): {result}")

    finally:
        iec61850.IedConnection_destroy(conn)
        server.stop()
        server.destroy()


if __name__ == "__main__":
    asyncio.run(debug_browsing())
