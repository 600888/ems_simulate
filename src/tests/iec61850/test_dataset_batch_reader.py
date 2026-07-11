"""IEC 61850 DataSet 优先批读的纯单元回归测试。"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from src.device.protocol.iec61850_handler import IEC61850ClientHandler
from src.enums.point_data import Yc
from src.proto.iec61850.core.connection import Iec61850Connection
from src.proto.iec61850.core.registry import PointRegistry
from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.model.discovery import IedModelBuilder, ModelDiscoveryService
from src.proto.iec61850.model.ied_model import DARef, DORef, IedModel, LDModel, LNModel
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
from src.proto.iec61850.plugins.scl.model.scl_document import SclDocument
from src.proto.iec61850.plugins.scl.service.import_service import SclImportResult


def test_normalizes_dataset_and_fcda_reference_forms():
    """点号、美元符号、模型前缀和 FC 后缀应归一到相同目录键。"""
    assert normalize_dataset_ref("LD0/LLN0.dsStatus", "IED") == "IEDLD0/LLN0$dsStatus"
    assert normalize_dataset_ref("IEDLD0/LLN0$dsStatus", "IED") == "IEDLD0/LLN0$dsStatus"
    assert normalize_point_ref("LD0/MMXU1$MX$TotW$mag$f[MX]", "IED") == "IEDLD0/MMXU1.TotW.mag.f"
    assert strip_fc_suffix("LD0/MMXU1.TotW.mag.f[MX]") == ("LD0/MMXU1.TotW.mag.f", "MX")


def test_icd_load_installs_offline_ied_model_for_dataset_projection():
    """ICD 导入必须像在线发现一样给 DataSet 目录提供完整 IedModel。"""
    client = IEC61850Client.__new__(IEC61850Client)
    client.ip = "127.0.0.1"
    client.port = 102
    client.model_name = "IED"
    client._registry = PointRegistry("IED", "LD0")
    client._discovery = ModelDiscoveryService()
    client._last_import_result = None
    client._rcbs_from_icd = []

    result = SclImportResult(doc=SclDocument(), ied_name="IED")

    assert client.load_model_from_icd("offline.icd", scl_result=result) is True
    assert client.model is not None
    assert client.model.host == "127.0.0.1"
    assert client.model.port == 102


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
                                    DARef(
                                        name="mag",
                                        path="mag",
                                        fc="MX",
                                        iec_type="float",
                                        mms_type="MMS_STRUCTURE",
                                        sub_das=(
                                            DARef(
                                                name="f",
                                                path="mag.f",
                                                fc="MX",
                                                iec_type="float",
                                                mms_type="MMS_FLOAT",
                                            ),
                                        ),
                                    ),
                                    DARef(
                                        name="q",
                                        path="q",
                                        fc="MX",
                                        iec_type="integer",
                                        mms_type="MMS_BIT_STRING",
                                        sub_das=(
                                            DARef(name="validity", path="q.validity", fc="MX", iec_type="integer"),
                                            DARef(name="source", path="q.source", fc="MX", iec_type="integer"),
                                        ),
                                    ),
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


def test_icd_import_aggregate_registry_filters_q_t_du():
    """ICD 导入（无模型）时，结构体成员只能投影值属性，排除 q/t/dU 等元数据。

    ``aggregate_registry`` 应从注册表中选取所有以 member_ref 开头的叶子引用，
    但只保留值属性终点（f / i / stVal / ctlVal / setVal），避免 dU 等
    VISIBLE_STRING 写入期望数值的 YC 测点。
    """
    # 模拟 ICD 导入后的注册表：包含 mag.f（值）、mag.i、以及元数据 q / t / dU
    registry = SimpleNamespace(
        point_refs={
            "power_f": "IEDLD0/MMXU1.TotW.mag.f",
            "power_i": "IEDLD0/MMXU1.TotW.mag.i",
            "power_q": "IEDLD0/MMXU1.TotW.mag.q",
            "power_t": "IEDLD0/MMXU1.TotW.mag.t",
            "power_du": "IEDLD0/MMXU1.TotW.mag.dU",
        }
    )
    catalog = DatasetCatalog.from_sources(
        [{"ref": "IEDLD0/LLN0$ds", "members": [{"ref": "IEDLD0/MMXU1.TotW.mag", "fc": "MX"}]}],
        registry=registry,
        model=None,
    )

    leaf_refs = catalog.datasets[0].members[0].leaf_refs

    # 值属性必须保留
    assert "IEDLD0/MMXU1.TotW.mag.f" in leaf_refs
    assert "IEDLD0/MMXU1.TotW.mag.i" in leaf_refs

    # 元数据属性必须排除
    assert "IEDLD0/MMXU1.TotW.mag.q" not in leaf_refs
    assert "IEDLD0/MMXU1.TotW.mag.t" not in leaf_refs
    assert "IEDLD0/MMXU1.TotW.mag.dU" not in leaf_refs

    assert len(leaf_refs) == 2  # 仅 mag.f + mag.i

    # 验证 planner 能正确规划覆盖
    assert DatasetReadPlanner(catalog).plan(["power_f", "power_i"]).uncovered == ()


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
        self.spec_with_result = None

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
        self.spec_with_result = _args[-1]
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
    assert native.spec_with_result is True


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


def test_transport_decodes_do_level_structure_using_wire_projection(monkeypatch):
    """DO 级成员应按 mag 结构、q 位串、t 时标三个线元素正确映射。"""
    from src.proto.iec61850.plugins.datasets import transport as transport_module

    do_value = _FakeValue(
        _FakeNative.MMS_STRUCTURE,
        children=[
            _FakeValue(
                _FakeNative.MMS_STRUCTURE,
                children=[_FakeValue(_FakeNative.MMS_FLOAT, 12.5)],
            ),
            _FakeValue(_FakeNative.MMS_BIT_STRING, 0),
            _FakeValue(_FakeNative.MMS_UTC_TIME, 123456),
        ],
    )
    native = _FakeNative([do_value])
    monkeypatch.setattr(transport_module, "mms_value_to_python", lambda value, _iec_type: value.value)
    dataset = DatasetDescriptor(
        ref="IEDLD0/LLN0$ds",
        members=(
            DatasetMember(
                0,
                "IEDLD0/MMXU1.TotW",
                "MX",
                leaf_refs=(
                    "IEDLD0/MMXU1.TotW.mag.f",
                    "IEDLD0/MMXU1.TotW.q",
                    "IEDLD0/MMXU1.TotW.t",
                ),
            ),
        ),
    )

    result = DatasetTransport(_FakeConnection(), native).read(dataset)

    assert result.value_map == {
        "IEDLD0/MMXU1.TotW.mag.f": 12.5,
        "IEDLD0/MMXU1.TotW.q": 0,
        "IEDLD0/MMXU1.TotW.t": 123456,
    }
    assert result.errors == ()


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


def test_plugin_reports_progress_after_each_dataset_read():
    """批读进度必须在规划后按已完成的 DataSet 数量逐步上报。"""
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
    progress_events = []

    result = plugin.read_points_batch(
        ["a", "b"],
        None,
        lambda *_args: {},
        progress=lambda phase, current, total, message: progress_events.append((phase, current, total, message)),
    )

    assert result == {"a": 10.0, "b": 20.0}
    assert [(phase, current, total) for phase, current, total, _ in progress_events] == [
        ("planning", 0, 1),
        ("dataset", 1, 1),
    ]
    assert "DataSet 1/1" in progress_events[-1][3]


def test_strict_dataset_read_never_falls_back_to_members(monkeypatch):
    """软件 GI 使用的严格模式遇到成员错误时必须整次失败，不能逐点补读。"""
    plugin = DataSetsPlugin()
    plugin._connection = _PluginConnection()
    plugin._registry = _PluginRegistry()
    plugin._client = SimpleNamespace(model=None)
    plugin._transport = SimpleNamespace(
        read=lambda dataset: DatasetReadResult(
            dataset_ref=dataset.ref,
            member_values=(("IEDLD0/X.A", 10.0),),
            errors=(DatasetMemberError(index=1, ref="IEDLD0/X.B", reason="access-error"),),
            request_count=1,
        )
    )
    monkeypatch.setattr(
        plugin,
        "_read_dataset_values_by_members",
        lambda _ref: (_ for _ in ()).throw(AssertionError("严格模式禁止逐点回退")),
    )

    assert plugin.read_dataset_values("IEDLD0/LLN0$ds", allow_member_fallback=False) == {}


def test_connection_does_not_repeat_prefix_for_discovered_remote_ld():
    """在线发现得到的完整 MMS domain 不应再拼接配置 model_name。"""
    connection = SimpleNamespace(
        model_name="WRONG",
        _discovered_lds=["REALIEDLD0"],
    )
    assert Iec61850Connection.build_dataset_ref(connection, "REALIEDLD0/LLN0$ds") == "REALIEDLD0/LLN0$ds"


def test_model_discovery_builds_complete_tree_before_dataset_catalog(monkeypatch):
    """模型发现必须先完成全部 DO/DA 遍历，之后才能解释 DataSet 引用。"""
    service = ModelDiscoveryService()
    events = []
    monkeypatch.setattr(service, "_browse_logical_nodes", lambda _conn, _ld: ["LLN0", "MMXU1"])

    def discover_data_objects(_conn, _ld, ln_ref, _ln_name, max_depth):
        events.append(("model", ln_ref, max_depth))
        return []

    def discover_datasets(_conn, _ld, ln_ref):
        events.append(("dataset", ln_ref))
        return []

    monkeypatch.setattr(service, "_discover_data_objects", discover_data_objects)
    monkeypatch.setattr(service, "_discover_datasets", discover_datasets)
    monkeypatch.setattr(service, "_discover_rcbs", lambda *_args: [])
    monkeypatch.setattr(service, "_discover_gocbs", lambda *_args: [])

    service._discover_ld(object(), IedModelBuilder("127.0.0.1", 102), "LD0", max_depth=10, on_error="abort")

    assert [event[0] for event in events] == ["model", "model", "dataset"]


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


def test_handler_exposes_monotonic_dataset_read_progress():
    """Handler 应把协议层 DataSet 进度转换为前端可轮询的 0-100 快照。"""
    handler = IEC61850ClientHandler()
    handler._is_running = True
    snapshots = []

    def read_points_batch(addresses, _fc_map, *, progress):
        progress("planning", 0, 2, "计划读取 2 个 DataSet")
        snapshots.append(handler.get_connect_progress())
        progress("dataset", 1, 2, "已读取 DataSet 1/2")
        snapshots.append(handler.get_connect_progress())
        progress("dataset", 2, 2, "已读取 DataSet 2/2")
        snapshots.append(handler.get_connect_progress())
        return {addresses[0]: 12.0}

    handler._client = SimpleNamespace(is_connected=True, read_points_batch=read_points_batch)
    point = Yc(address="LD0/MMXU1.TotW.mag.f", code="total_power", fc="MX")

    assert handler.read_points_batch([point], track_progress=True) == {"total_power": 12}
    assert [snapshot["progress"] for snapshot in snapshots] == sorted(snapshot["progress"] for snapshot in snapshots)
    assert snapshots[1]["progress"] < snapshots[2]["progress"] < 100
    final = handler.get_connect_progress()
    assert final["operation"] == "read"
    assert final["phase"] == "done"
    assert final["progress"] == 100
    assert final["active"] is False
