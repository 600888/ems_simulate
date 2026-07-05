"""IEC 61850 DataSet 发现回归测试。"""

from __future__ import annotations

from types import SimpleNamespace

from src.proto.iec61850.model import discovery as discovery_module
from src.proto.iec61850.model.discovery import ModelDiscoveryService


def test_dataset_discovery_reads_each_directory_once_without_ctypes_bool(monkeypatch):
    """DataSet 成员与属性不应触发两次目录请求或传入 ctypes 指针。"""
    member_node = SimpleNamespace(data="IEDLD0/MMXU1$MX$TotW$mag$f", next=None)
    directory_head = SimpleNamespace(next=member_node)
    directory_calls: list[tuple[object, str, object]] = []

    class FakeNative:
        IED_ERROR_OK = 0

        @staticmethod
        def IedConnection_getLogicalNodeDirectory(conn, ln_ref, acsi_class):
            return object(), 0

        @staticmethod
        def IedConnection_getDataSetDirectory(conn, dataset_ref, is_deletable):
            directory_calls.append((conn, dataset_ref, is_deletable))
            if is_deletable is not None:
                raise TypeError("argument 3 of type 'bool *'")
            return directory_head, 0

        @staticmethod
        def LinkedList_getNext(node):
            return node.next

        @staticmethod
        def LinkedList_getData(node):
            return node.data

        @staticmethod
        def LinkedList_destroy(_linked_list):
            return None

        @staticmethod
        def toCharP(value):
            return value

    conn = object()
    monkeypatch.setattr(discovery_module, "iec61850", FakeNative, raising=False)
    monkeypatch.setattr(discovery_module, "get_list_from_linked_list", lambda _value: ["dsCellTemp"])

    datasets = ModelDiscoveryService()._discover_datasets(conn, "IEDLD0", "IEDLD0/LLN0")

    assert len(datasets) == 1
    assert datasets[0].ref == "IEDLD0/LLN0.dsCellTemp"
    assert datasets[0].is_deletable is False
    assert [member["ref"] for member in datasets[0].members] == ["IEDLD0/MMXU1.TotW.mag.f"]
    assert directory_calls == [(conn, "IEDLD0/LLN0.dsCellTemp", None)]
