"""Debug script: test IEC61850 server with ICD-style points and client discovery"""

import time

from pyiec61850 import pyiec61850 as iec61850

from src.proto.iec61850.iec61850_server import IEC61850Server

# 模拟 ICD 导入的测点地址格式
server = IEC61850Server(port=10103, model_name="EMS", ld_name="GenericLD")

# 添加 ICD 模式的测点 (完整引用路径)
server.add_point(address="MET/METMMXU1.TotW.mag.f", frame_type=0)  # 遥测
server.add_point(address="MET/METMMXU1.TotVAr.mag.f", frame_type=0)  # 遥测
server.add_point(address="CFG/LLN0.Beh.stVal", frame_type=1)  # 遥信 (但 LLN0)
server.add_point(address="PRO/BK1XCBR1.Pos.ctlVal", frame_type=2)  # 遥控
server.add_point(address="CON/RBGGIO1.SPCSO01.ctlVal", frame_type=2)  # 遥控

server.start()
time.sleep(0.5)

# 用客户端连接测试
conn = iec61850.IedConnection_create()
result = iec61850.IedConnection_connect(conn, "127.0.0.1", 10103)
error = result if not isinstance(result, (list, tuple)) else result[1]
print(f"Connect: error={error}")

if error == 0:
    # 1. 获取 LD 列表
    result = iec61850.IedConnection_getLogicalDeviceList(conn)
    ld_list = result[0] if isinstance(result, (list, tuple)) else result
    err = result[1] if isinstance(result, (list, tuple)) else 0
    lds = []
    it = iec61850.LinkedList_getNext(ld_list)
    while it:
        lds.append(iec61850.toCharP(it.data))
        it = iec61850.LinkedList_getNext(it)
    iec61850.LinkedList_destroy(ld_list)
    print(f"LDs: {lds}, err={err}")

    for ld in lds:
        # 2. 获取 LN 列表
        result = iec61850.IedConnection_getLogicalDeviceDirectory(conn, ld)
        ln_list = result[0] if isinstance(result, (list, tuple)) else result
        err = result[1] if isinstance(result, (list, tuple)) else 0
        lns = []
        it = iec61850.LinkedList_getNext(ln_list)
        while it:
            lns.append(iec61850.toCharP(it.data))
            it = iec61850.LinkedList_getNext(it)
        iec61850.LinkedList_destroy(ln_list)
        print(f"  LD {ld} LNs: {lns}, err={err}")

        for ln in lns:
            ln_ref = f"{ld}/{ln}"
            # 3. 获取 DO 列表
            result = iec61850.IedConnection_getLogicalNodeDirectory(conn, ln_ref, 0)
            do_list = result[0] if isinstance(result, (list, tuple)) else result
            err = result[1] if isinstance(result, (list, tuple)) else 0
            dos = []
            if err == 0 and do_list:
                it = iec61850.LinkedList_getNext(do_list)
                while it:
                    dos.append(iec61850.toCharP(it.data))
                    it = iec61850.LinkedList_getNext(it)
                iec61850.LinkedList_destroy(do_list)
            print(f"    LN {ln_ref} DOs: {dos}, err={err}")

iec61850.IedConnection_destroy(conn)
server.stop()
server.destroy()
print("Done")
