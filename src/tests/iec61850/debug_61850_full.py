"""Debug: simulate loading Channel 22 (IEC61850_SERVER) points"""

import time

from pyiec61850 import pyiec61850 as iec61850

from src.data.service.yc_service import YcService
from src.data.service.yk_service import YkService
from src.data.service.yt_service import YtService
from src.data.service.yx_service import YxService
from src.enums.modbus_def import ProtocolType
from src.proto.iec61850.iec61850_server import IEC61850Server

channel_id = 22
protocol_type = ProtocolType.Iec61850Server

# 加载测点
yc_list = YcService.get_list(channel_id, protocol_type)
yx_list = YxService.get_list(channel_id, protocol_type)
yk_list = YkService.get_list(channel_id, protocol_type)
yt_list = YtService.get_list(channel_id, protocol_type)

print(f"Loaded: yc={len(yc_list)}, yx={len(yx_list)}, yk={len(yk_list)}, yt={len(yt_list)}")

# 显示前几个点的 address
for i, p in enumerate(yc_list[:5]):
    print(f"  yc[{i}]: address={p.address} (type={type(p.address).__name__}), code={p.code}, frame_type={p.frame_type}")
for i, p in enumerate(yx_list[:5]):
    print(f"  yx[{i}]: address={p.address} (type={type(p.address).__name__}), code={p.code}, frame_type={p.frame_type}")

# 创建服务端并添加测点
server = IEC61850Server(port=10103, model_name="EMS", ld_name="GenericLD")

add_ok = 0
add_fail = 0
for point in yc_list + yx_list + yk_list + yt_list:
    try:
        ref = server.add_point(address=point.address, frame_type=point.frame_type)
        if ref:
            add_ok += 1
        else:
            add_fail += 1
            if add_fail <= 3:
                print(f"  ADD FAIL: address={point.address}, frame_type={point.frame_type}")
    except Exception as e:
        add_fail += 1
        if add_fail <= 3:
            print(f"  ADD ERROR: address={point.address}, frame_type={point.frame_type}, error={e}")

print(f"Add results: ok={add_ok}, fail={add_fail}")

server.start()
time.sleep(0.5)

# 用客户端连接测试发现
conn = iec61850.IedConnection_create()
result = iec61850.IedConnection_connect(conn, "127.0.0.1", 10103)
error = result if not isinstance(result, (list, tuple)) else result[1]

if error == 0:
    result = iec61850.IedConnection_getLogicalDeviceList(conn)
    ld_list = result[0] if isinstance(result, (list, tuple)) else result
    lds = []
    it = iec61850.LinkedList_getNext(ld_list)
    while it:
        lds.append(iec61850.toCharP(it.data))
        it = iec61850.LinkedList_getNext(it)
    iec61850.LinkedList_destroy(ld_list)
    print(f"LDs: {lds}")

    total_dos = 0
    for ld in lds:
        result = iec61850.IedConnection_getLogicalDeviceDirectory(conn, ld)
        ln_list = result[0] if isinstance(result, (list, tuple)) else result
        lns = []
        it = iec61850.LinkedList_getNext(ln_list)
        while it:
            lns.append(iec61850.toCharP(it.data))
            it = iec61850.LinkedList_getNext(it)
        iec61850.LinkedList_destroy(ln_list)

        for ln in lns:
            ln_ref = f"{ld}/{ln}"
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
            if dos:
                total_dos += len(dos)
                if total_dos <= 20:
                    print(f"  {ln_ref}: DOs={dos}")

    print(f"Total discovered DOs: {total_dos}")

iec61850.IedConnection_destroy(conn)
server.stop()
server.destroy()
print("Done")
