"""IEC 61850 DataSet 优先批读的纯单元回归测试。"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from src.device.protocol.iec61850_handler import IEC61850ClientHandler
from src.enums.point_data import Yc
from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.model.discovery import ModelDiscoveryService
from src.proto.iec61850.model.ied_model import DARef, DataSetRef, DORef, IedModel, LDModel, LNModel
from src.proto.iec61850.plugins.datasets import DataSetsPlugin
from src.proto.iec61850.plugins.datasets.catalog import (
    DatasetCatalog,
    DatasetReadPlanner,
    normalize_dataset_ref,
    normalize_point_ref,
    strip_fc_suffix,
)
from src.proto.iec61850.plugins.datasets.models import (
    DatasetDescriptor,
    DatasetMember,
    DatasetMemberError,
    DatasetReadResult,
)
from src.proto.iec61850.plugins.datasets.transport import DatasetTransport


def test_normalizes_dataset_and_fcda_reference_forms():
    """点号、美元符号、模型前缀和 FC 后缀应归一到相同目录键。"""
    assert normalize_dataset_ref("LD0/LLN0.dsStatus", "IED") == "IEDLD0/LLN0$dsStatus"
    assert normalize_dataset_ref("IEDLD0/LLN0$dsStatus", "IED") == "IEDLD0/LLN0$dsStatus"
    assert normalize_point_ref("LD0/MMXU1$MX$TotW$mag$f[MX]", "IED") == "IEDLD0/MMXU1.TotW.mag.f"
    assert strip_fc_suffix("LD0/MMXU1.TotW.mag.f[MX]") == ("LD0/MMXU1.TotW.mag.f", "MX")


def test_planner_uses_stable_greedy_selection_for_overlapping_datasets():
    """覆盖数相同时优先选择成员少的 DataSet，并保持引用排序稳定。"""
    refs = {"a": "IEDLD0/X.A", "b": "IEDLD0/X.B", "c": "IEDLD0/X.C"}
    registry = SimpleNamespace(point_refs=refs)
    datasets = [
        {
            "ref": "IEDLD0/LLN0$large",
            "members": [{"ref": refs["a"]}, {"ref": refs["b"]}, {"ref": refs["c"]}],
        },
        {"ref": "IEDLD0/LLN0$small", "members": [{"ref": refs["a"]}, {"ref": refs["b"]}]},
    ]
    catalog = DatasetCatalog.from_sources(datasets, registry=registry, model_name="IED")

    plan = DatasetReadPlanner(catalog).plan(["b", "a", "a"])

    assert plan.requested == ("b", "a")
    assert [dataset.name for dataset in plan.datasets] == ["small"]
    assert plan.uncovered == ()


def test_catalog_projects_do_level_fcda_with_complete_model_order():
    """DO 级 FCDA 应按完整模型顺序包含主值和元数据叶子，不能只猜业务测点。"""
    model = IedModel(
        lds=(
            LDModel(
                name="IEDLD0",
                lns=(
                    LNModel(
                        name="MMXU1",
                        dos=(
                            DORef(
                                name="TotW",
                                ref="IEDLD0/MMXU1.TotW",
                                das=(
                                    DARef(name="mag", path="mag.f", fc="MX", iec_type="float"),
                                    DARef(name="q", path="q", fc="MX", iec_type="integer"),
                                    DARef(name="t", path="t", fc="MX", iec_type="timestamp"),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
    )
    registry = SimpleNamespace(point_refs={"power": "IEDLD0/MMXU1.TotW.mag.f"})
    catalog = DatasetCatalog.from_sources(
        [{"ref": "IEDLD0/LLN0$ds", "members": [{"ref": "IEDLD0/MMXU1.TotW", "fc": "MX"}]}],
        registry=registry,
        model=model,
    )

    assert catalog.datasets[0].members[0].leaf_refs == (
        "IEDLD0/MMXU1.TotW.mag.f",
        "IEDLD0/MMXU1.TotW.q",
        "IEDLD0/MMXU1.TotW.t",
    )
    assert DatasetReadPlanner(catalog).plan(["power"]).uncovered == ()


class _FakeValue:
    """供原生传输测试使用的最小 MMS 值。"""

    def __init__(self, mms_type: int, value=None, children=()):
        self.mms_type = mms_type
        self.value = value
        self.children = list(children)


class _FakeNative:
    """记录资源释放次数的最小 pyiec61850 替身。"""

    MMS_ARRAY = 0
    MMS_STRUCTURE = 1
    MMS_BOOLEAN = 2
    MMS_BIT_STRING = 3
    MMS_INTEGER = 4
    MMS_UNSIGNED = 5
    MMS_FLOAT = 6
    MMS_OCTET_STRING = 7
    MMS_VISIBLE_STRING = 8
    MMS_GENERALIZED_TIME = 9
    MMS_BINARY_TIME = 10
    MMS_BCD = 11
    MMS_OBJ_ID = 12
    MMS_STRING = 13
    MMS_UTC_TIME = 14
    MMS_DATA_ACCESS_ERROR = 15

    def __init__(self, values):
        self.values = _FakeValue(self.MMS_ARRAY, children=values)
        self.deleted_values = 0
        self.destroyed_errors = 0

    @staticmethod
    def IedConnection_getMmsConnection(conn):
        return conn

    @staticmethod
    def MmsError_create():
        return SimpleNamespace(value=0)

    @staticmethod
    def MmsError_getValue(error):
        return error.value

    def MmsConnection_readNamedVariableListValues(self, *_args):
        return self.values

    @staticmethod
    def MmsValue_getArraySize(value):
        return len(value.children)

    @staticmethod
    def MmsValue_getElement(value, index):
        return value.children[index]

    @staticmethod
    def MmsValue_getType(value):
        return value.mms_type

    def MmsValue_delete(self, _value):
        self.deleted_values += 1

    def MmsErrror_destroy(self, _error):
        self.destroyed_errors += 1


class _FakeConnection:
    model_name = "IED"

    @contextmanager
    def native_operation(self):
        yield object()

    @staticmethod
    def build_dataset_ref(ref):
        return ref


def test_transport_keeps_partial_success_and_releases_native_resources(monkeypatch):
    """成员级访问错误不应丢弃成功值，所有原生资源必须准确释放一次。"""
    from src.proto.iec61850.plugins.datasets import transport as transport_module

    native = _FakeNative(
        [
            _FakeValue(_FakeNative.MMS_FLOAT, 12.5),
            _FakeValue(_FakeNative.MMS_DATA_ACCESS_ERROR),
        ]
    )
    monkeypatch.setattr(transport_module, "mms_value_to_python", lambda value, _iec_type: value.value)
    dataset = DatasetDescriptor(
        ref="IEDLD0/LLN0$ds",
        members=(
            DatasetMember(0, "IEDLD0/X.A", "MX", leaf_refs=("IEDLD0/X.A",)),
            DatasetMember(1, "IEDLD0/X.B", "MX", leaf_refs=("IEDLD0/X.B",)),
        ),
    )

    result = DatasetTransport(_FakeConnection(), native).read(dataset)

    assert result.value_map == {"IEDLD0/X.A": 12.5}
    assert result.runtime_type_map == {"IEDLD0/X.A": "MMS_FLOAT"}
    assert result.errors == (DatasetMemberError(1, "IEDLD0/X.B", "data access error"),)
    assert native.deleted_values == 1
    assert native.destroyed_errors == 1


def test_transport_rejects_structure_projection_mismatch(monkeypatch):
    """模型叶子数和 MMS 结构数量不一致时必须整体拒绝该成员，禁止错位赋值。"""
    from src.proto.iec61850.plugins.datasets import transport as transport_module

    structure = _FakeValue(
        _FakeNative.MMS_STRUCTURE,
        children=[_FakeValue(_FakeNative.MMS_FLOAT, 1.0), _FakeValue(_FakeNative.MMS_FLOAT, 2.0)],
    )
    native = _FakeNative([structure])
    monkeypatch.setattr(transport_module, "mms_value_to_python", lambda value, _iec_type: value.value)
    dataset = DatasetDescriptor(
        ref="IEDLD0/LLN0$ds",
        members=(DatasetMember(0, "IEDLD0/MMXU1.TotW", "MX", leaf_refs=("IEDLD0/MMXU1.TotW.mag.f",)),),
    )

    result = DatasetTransport(_FakeConnection(), native).read(dataset)

    assert result.value_map == {}
    assert "projection mismatch" in result.errors[0].reason
    assert native.deleted_values == 1
    assert native.destroyed_errors == 1


class _PluginConnection:
    """DataSetsPlugin 编排测试使用的连接替身。"""

    model_name = "IED"

    @staticmethod
    def ensure_connected():
        return True

    @staticmethod
    def reconnect_if_unhealthy(_reason):
        return False


class _PluginRegistry:
    """只实现 DataSet 规划和类型缓存所需的注册表接口。"""

    def __init__(self):
        self.point_refs = {"a": "IEDLD0/X.A", "b": "IEDLD0/X.B"}
        self.discovered_datasets = [
            {
                "ref": "IEDLD0/LLN0$ds",
                "members": [
                    {"ref": "IEDLD0/X.A", "fc": "MX"},
                    {"ref": "IEDLD0/X.B", "fc": "MX"},
                ],
            }
        ]
        self.mms_types = {}
        self.iec_types = {}

    def set_mms_type(self, address, value):
        self.mms_types[address] = value

    def set_iec_type(self, address, value):
        self.iec_types[address] = value


def test_plugin_falls_back_only_for_missing_or_failed_points():
    """DataSet 已成功返回的点不能再次进入单点回退，缺失点必须精确回退。"""
    plugin = DataSetsPlugin()
    plugin._connection = _PluginConnection()
    plugin._registry = _PluginRegistry()
    plugin._client = SimpleNamespace(model=None)
    plugin._transport = SimpleNamespace(
        read=lambda dataset: DatasetReadResult(
            dataset_ref=dataset.ref,
            values=(("IEDLD0/X.A", 10.0),),
            runtime_types=(("IEDLD0/X.A", "MMS_FLOAT"),),
            request_count=1,
        )
    )
    fallback_calls = []

    def fallback(addresses, _fc_map):
        fallback_calls.append(tuple(addresses))
        return {"b": 20.0}

    result = plugin.read_points_batch(["a", "b"], None, fallback)

    assert result == {"a": 10.0, "b": 20.0}
    assert fallback_calls == [("b",)]
    assert plugin._registry.mms_types == {"a": "MMS_FLOAT"}


def test_plugin_uses_zero_single_reads_when_dataset_fully_covers_batch():
    """DataSet 100% 覆盖且解码成功时不得触发任何单点请求。"""
    plugin = DataSetsPlugin()
    plugin._connection = _PluginConnection()
    plugin._registry = _PluginRegistry()
    plugin._client = SimpleNamespace(model=None)
    plugin._transport = SimpleNamespace(
        read=lambda dataset: DatasetReadResult(
            dataset_ref=dataset.ref,
            values=(("IEDLD0/X.A", 10.0), ("IEDLD0/X.B", 20.0)),
            request_count=1,
        )
    )

    def forbidden_fallback(_addresses, _fc_map):
        raise AssertionError("DataSet 已完全覆盖，不允许单点读取")

    assert plugin.read_points_batch(["a", "b"], None, forbidden_fallback) == {"a": 10.0, "b": 20.0}


def test_model_discovery_prefetches_exact_dataset_member_types(monkeypatch):
    """模型发现应先用 DataSet 填充精确 FCDA 类型缓存，供后续 DA 遍历复用。"""
    from src.proto.iec61850.model import discovery as discovery_module

    class FakeTransport:
        """返回一个精确叶子类型的发现阶段传输替身。"""

        def __init__(self, _connection, _native):
            pass

        @staticmethod
        def read(dataset):
            member = dataset.members[0]
            return DatasetReadResult(
                dataset_ref=dataset.ref,
                values=((member.ref, 1.25),),
                runtime_types=((member.ref, "MMS_FLOAT"),),
                request_count=1,
            )

    monkeypatch.setattr(discovery_module, "DatasetTransport", FakeTransport)
    service = ModelDiscoveryService()
    progress_events = []
    dataset = DataSetRef(
        name="dsMeas",
        ref="IEDLD0/LLN0.dsMeas",
        members=({"ref": "IEDLD0/MMXU1.TotW.mag.f", "fc": "MX", "iec_type": "float"},),
    )

    service._prefetch_dataset_types(
        object(),
        [dataset],
        lambda phase, current, total, message: progress_events.append((phase, current, total, message)),
    )

    assert service._type_probe_cache[("IEDLD0/MMXU1.TotW.mag.f", "MX")].value == "MMS_FLOAT"
    assert service.get_prefetched_value("IEDLD0/MMXU1.TotW.mag.f", "MX") == 1.25
    assert service._type_probe_stats["dataset"] == 1
    assert progress_events[-1][:3] == ("dataset_prefetch", 1, 1)


def test_connection_does_not_repeat_prefix_for_discovered_remote_ld():
    """在线发现得到的完整 MMS domain 不应再拼接配置 model_name。"""
    connection = SimpleNamespace(
        model_name="WRONG",
        _discovered_lds=["REALIEDLD0"],
    )
    from src.proto.iec61850.core.connection import Iec61850Connection

    assert Iec61850Connection.build_dataset_ref(connection, "REALIEDLD0/LLN0$ds") == "REALIEDLD0/LLN0$ds"


def test_fill_du_names_reuses_dataset_snapshot_before_single_read():
    """dU 已由 DataSet 预取时应直接复用，不再调用描述单点读取。"""
    client = IEC61850Client.__new__(IEC61850Client)
    client._registry = SimpleNamespace(set_name=lambda *_args: None)
    client._discovery = SimpleNamespace(
        get_prefetched_value=lambda ref, *_fcs: "总有功功率" if ref.endswith(".dU") else None
    )

    def unexpected_single_read(_ref):
        raise AssertionError("DataSet 已命中 dU，不应再次单点读取")

    client._read_du_description = unexpected_single_read
    discovered = [{"address": "LD0/MMXU1.TotW.mag.f"}]

    client._fill_du_names(discovered)

    assert discovered[0]["name"] == "总有功功率"


def test_handler_keeps_point_code_mapping_and_yc_coefficient_conversion():
    """协议层改为 DataSet 后，Handler 的编码映射和遥测反向系数换算保持不变。"""
    handler = IEC61850ClientHandler()
    handler._is_running = True
    handler._client = SimpleNamespace(
        is_connected=True,
        read_points_batch=lambda addresses, _fc_map: {addresses[0]: 12.0},
    )
    point = Yc(
        address="LD0/MMXU1.TotW.mag.f",
        code="total_power",
        mul_coe=2.0,
        add_coe=2.0,
        fc="MX",
    )

    assert handler.read_points_batch([point]) == {"total_power": 5}
