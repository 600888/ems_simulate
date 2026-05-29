"""IEC 61850 LinkedList 工具函数

从 iec61850_client.py 的 _get_list_from_linked_list 提取，
供 Client/Server/ModelExporter 共用。
"""

from ..defs.constants import HAS_IEC61850
from ..log import log


def get_list_from_linked_list(linked_list) -> list[str]:
    """从 LinkedList 中提取字符串列表

    LinkedList 结构: linked_list 本身是头节点, LinkedList_getNext 返回下一个节点。
    正确做法: 先读取头节点数据, 再遍历后续节点。

    Args:
        linked_list: pyiec61850 LinkedList 对象

    Returns:
        字符串列表
    """
    if not HAS_IEC61850 or linked_list is None:
        return []

    from pyiec61850 import pyiec61850 as iec61850

    items = []
    # 先读取头节点的数据
    try:
        head_data = iec61850.toCharP(linked_list.data)
        if head_data:
            items.append(head_data)
    except Exception:
        pass
    # 再遍历后续节点
    item = iec61850.LinkedList_getNext(linked_list)
    while item:
        try:
            items.append(iec61850.toCharP(item.data))
        except Exception:
            pass
        item = iec61850.LinkedList_getNext(item)
    iec61850.LinkedList_destroy(linked_list)
    return items
