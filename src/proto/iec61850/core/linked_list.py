"""IEC 61850 LinkedList 工具函数

从 iec61850_client.py 的 _get_list_from_linked_list 提取，
供 Client/Server/ModelExporter 共用。

优化: 两阶段处理（先收集指针，再批量转换字符串），
减少 try/except 进入次数和 C FFI 交错调用开销。
"""

from ..defs.constants import HAS_IEC61850


def get_list_from_linked_list(linked_list) -> list[str]:
    """从 LinkedList 中提取字符串列表

    LinkedList 结构: 头节点是 dummy 节点 (无数据)，
    从 LinkedList_getNext 开始才是实际数据节点。
    必须使用 LinkedList_getData 获取节点数据 (item.data 会返回裸指针)。

    参考 C++ 实现 (Client61850::getLnRcbInstList):
      element = LinkedList_getNext(lln0dir);  // 跳过 dummy head
      while (element) {
          char* name = (char*)LinkedList_getData(element);
          element = LinkedList_getNext(element);
      }
    """
    if not HAS_IEC61850 or linked_list is None:
        return []

    from pyiec61850 import pyiec61850 as iec61850

    # Phase 1: 遍历收集所有数据指针（仅 getNext + getData，无字符串转换）
    pointers = []
    item = iec61850.LinkedList_getNext(linked_list)
    while item is not None:
        try:
            data_ptr = iec61850.LinkedList_getData(item)
            if data_ptr is not None:
                pointers.append(data_ptr)
        except Exception:
            pass
        try:
            item = iec61850.LinkedList_getNext(item)
        except Exception:
            break

    # Phase 2: 批量转换 C 指针 → Python 字符串（预分配列表避免 append 扩容）
    items = [None] * len(pointers)
    valid = 0
    for _i, ptr in enumerate(pointers):
        try:
            name = iec61850.toCharP(ptr)
            if name:
                items[valid] = name
                valid += 1
        except Exception:
            pass

    iec61850.LinkedList_destroy(linked_list)
    # 截断无效槽位
    if valid < len(items):
        del items[valid:]
    return items
