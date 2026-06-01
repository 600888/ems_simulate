"""IEC 61850 LinkedList 工具函数

从 iec61850_client.py 的 _get_list_from_linked_list 提取，
供 Client/Server/ModelExporter 共用。
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

    items = []
    # 跳过 dummy head 节点，直接从第一个实际数据节点开始
    item = iec61850.LinkedList_getNext(linked_list)
    while item:
        try:
            data_ptr = iec61850.LinkedList_getData(item)
            if data_ptr is not None:
                name = iec61850.toCharP(data_ptr)
                if name:
                    items.append(name)
        except Exception:
            pass
        item = iec61850.LinkedList_getNext(item)
    iec61850.LinkedList_destroy(linked_list)
    return items
