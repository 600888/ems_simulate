"""IEC 61850 读取类型单元测试

连接真实 BAMS 设备，测试 float / boolean / integer / string / timestamp / quality / auto-detect
等各种数据类型的 MMS 读取。

用法:
    pytest tests/iec61850/test_read.py -v -s
    或指定设备:
    IEC61850_TEST_HOST=192.168.1.100 IEC61850_TEST_PORT=102 pytest tests/iec61850/test_read.py -v -s
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any
from dataclasses import dataclass

import pytest

# ---- 确保项目根目录在 sys.path 中 ----
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ---- 被测模块 ----
from src.proto.iec61850.core.connection import Iec61850Connection
from src.proto.iec61850.core.reader import (
    READ_STRATEGIES,
    AutoDetectReader,
    BooleanReader,
    FloatReader,
    Iec61850Reader,
    IntegerReader,
    StringReader,
    TimestampReader,
)
from src.proto.iec61850.defs.constants import (
    HAS_IEC61850,
    IecType,
    IEC_TYPE_FLOAT,
    IEC_TYPE_BOOLEAN,
    IEC_TYPE_INTEGER,
    IEC_TYPE_STRING,
    IEC_TYPE_TIMESTAMP,
    IEC_TYPE_UNKNOWN,
)
from src.proto.iec61850.defs.da_patterns import DA_PATTERNS, EXTRA_DA_INFO
from src.proto.iec61850.model.discovery import ModelDiscoveryService, IedModel
from src.proto.iec61850.model.registry_bridge import build_registry_from_model
from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.core.registry import PointRegistry


# ============================================================
# 配置
# ============================================================

TEST_HOST = os.environ.get("IEC61850_TEST_HOST", "127.0.0.1")
TEST_PORT = int(os.environ.get("IEC61850_TEST_PORT", "102"))


def _device_available() -> bool:
    """快速探测设备是否可达"""
    if not HAS_IEC61850:
        return False
    try:
        conn = Iec61850Connection(TEST_HOST, TEST_PORT)
        result = conn.connect(auto_discover=False)
        conn.disconnect()
        return result
    except Exception:
        return False


DEVICE_AVAILABLE = _device_available()
pytestmark = pytest.mark.skipif(not DEVICE_AVAILABLE, reason=f"设备不可达: {TEST_HOST}:{TEST_PORT}")


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def connection():
    """模块级连接 fixture — 复用同一个连接"""
    conn = Iec61850Connection(TEST_HOST, TEST_PORT)
    ok = conn.connect(auto_discover=False)
    assert ok, f"连接失败: {TEST_HOST}:{TEST_PORT}"
    yield conn
    conn.disconnect()


@pytest.fixture(scope="module")
def model(connection):
    """模块级模型发现 fixture"""
    discovery = ModelDiscoveryService()
    ied_model = discovery.discover(connection)
    print(f"\n  [model] 发现: {ied_model.summary}")
    return ied_model


@pytest.fixture(scope="module")
def registry(model):
    """模块级 PointRegistry"""
    reg = PointRegistry()
    build_registry_from_model(model, reg)
    return reg


@pytest.fixture
def reader(connection, registry):
    """每个测试函数独立的 Iec61850Reader"""
    return Iec61850Reader(connection, registry)


# ============================================================
# 辅助函数
# ============================================================

@dataclass
class TestPoint:
    """测试用测点描述"""
    address: str      # 完整地址 (如 KG_BAMSCTMP01/MMCL1.Temp001.mag.f)
    ref: str          # MMS 引用
    fc: str           # 功能约束
    iec_type: str     # 数据类型
    frame_type: int   # 帧类型 (0=YC, 1=YX, 2=YK, 3=YT)
    description: str  # 可读描述


def _filter_points(
    registry: PointRegistry,
    model: IedModel,
    *,
    iec_type: str | None = None,
    frame_type: int | None = None,
    name_contains: str | None = None,
    max_count: int = 20,
) -> list[TestPoint]:
    """从已发现模型中筛选测试用测点"""
    points: list[TestPoint] = []
    for address, info in model.point_refs.items():
        if iec_type and info.get("iec_type") != iec_type:
            continue
        if frame_type is not None and info.get("frame_type") != frame_type:
            continue
        if name_contains and name_contains not in address:
            continue
        points.append(TestPoint(
            address=address,
            ref=info.get("ref", ""),
            fc=info.get("fc", ""),
            iec_type=info.get("iec_type", ""),
            frame_type=info.get("frame_type", -1),
            description=address.split(".")[-1] if "." in address else address,
        ))
        if len(points) >= max_count:
            break
    return points


# ============================================================
# FloatReader — 遥测浮点
# ============================================================

class TestFloatReader:
    """浮点值读取测试"""

    def test_read_single_float(self, connection, reader, model, registry):
        """读取单个浮点测点 (如 mag.f)"""
        points = _filter_points(registry, model, iec_type=IEC_TYPE_FLOAT, frame_type=0, max_count=5)
        assert points, "未发现浮点测点 (YC)"

        for pt in points:
            value = reader.read(pt.address)
            print(f"  [float] {pt.address} → {value}")
            assert isinstance(value, (float, int)), f"{pt.address}: 期望 float/int, 实际 {type(value).__name__}={value}"

    def test_read_float_batch(self, connection, reader, model, registry):
        """批量读取浮点测点"""
        points = _filter_points(registry, model, iec_type=IEC_TYPE_FLOAT, max_count=10)
        assert len(points) >= 2, "至少需要 2 个浮点测点用于批量测试"

        addresses = [pt.address for pt in points]
        results = reader.read_batch(addresses)
        assert len(results) == len(addresses), f"期望读取 {len(addresses)} 个, 实际 {len(results)} 个"
        for addr in addresses:
            assert addr in results, f"{addr} 不在批量结果中"
            val = results[addr]
            assert isinstance(val, (float, int)), f"{addr}: 批量读取值类型错误 {type(val).__name__}"

    def test_read_float_strategy_direct(self, connection):
        """直接用 FloatReader 策略读取 (绕过 Iec61850Reader)"""
        from pyiec61850 import pyiec61850 as iec61850
        conn = connection.connection
        strategy = FloatReader()

        # 使用 LLN0.Mod.stVal 作为探针 (若为 YC 类型 DO 的 mag.f 更佳)
        ref = f"{connection.model_name}{connection.ld_name}/LLN0.Mod.stVal"
        fc_val = connection.get_fc_value("ST")
        value = strategy.read(conn, ref, fc_val)
        print(f"  [float-strategy] {ref} → {value}")
        assert value is not None


# ============================================================
# BooleanReader — 遥信布尔
# ============================================================

class TestBooleanReader:
    """布尔值读取测试"""

    def test_read_single_boolean(self, connection, reader, model, registry):
        """读取单个布尔测点 (如 stVal)"""
        points = _filter_points(registry, model, iec_type=IEC_TYPE_BOOLEAN, frame_type=1, max_count=5)
        assert points, "未发现布尔测点 (YX)"

        success = 0
        for pt in points:
            value = reader.read(pt.address)
            print(f"  [bool] {pt.address} → {value}")
            if isinstance(value, bool):
                success += 1
            elif isinstance(value, int):
                # 部分设备布尔值以 0/1 返回
                success += 1
            elif value is None:
                print(f"  [bool] {pt.address} 读取返回 None (设备不支持该属性)")

        print(f"  [bool] 成功读取 {success}/{len(points)} 个布尔测点")

    def test_read_boolean_fallback_integer(self, connection):
        """布尔失败时回退整数读取"""
        from pyiec61850 import pyiec61850 as iec61850
        conn = connection.connection
        strategy = BooleanReader()
        reader_obj = Iec61850Reader(connection)

        # 找一个 ENC 类型的 stVal (如 LLN0.Mod.stVal)，它是整型枚举，不是布尔
        ref = f"{connection.model_name}{connection.ld_name}/LLN0.Mod.stVal"
        fc_val = connection.get_fc_value("ST")
        value = strategy.read(conn, ref, fc_val)
        print(f"  [bool-fallback] {ref} → {value}")
        # 整型回退至少返回一个整数
        assert isinstance(value, (int, bool)), f"回退读取失败: {type(value).__name__}={value}"


# ============================================================
# IntegerReader — 整数
# ============================================================

class TestIntegerReader:
    """整数值读取测试"""

    def test_read_enc_stval(self, connection, reader, model, registry):
        """读取 ENC 类型的 stVal (整数枚举)"""
        points = _filter_points(registry, model, iec_type=IEC_TYPE_INTEGER, max_count=5)
        if not points:
            pytest.skip("未发现整数测点")

        for pt in points:
            value = reader.read(pt.address)
            print(f"  [int] {pt.address} → {value}")
            assert isinstance(value, (int, float)), f"{pt.address}: 期望 int, 实际 {type(value).__name__}={value}"

    def test_read_integer_strategy_direct(self, connection):
        """直接用 IntegerReader 策略读取"""
        from pyiec61850 import pyiec61850 as iec61850
        conn = connection.connection
        strategy = IntegerReader()
        if not hasattr(iec61850, "IedConnection_readIntegerValue"):
            pytest.skip("pyiec61850 不支持 readIntegerValue")

        ref = f"{connection.model_name}{connection.ld_name}/LLN0.Mod.stVal"
        fc_val = connection.get_fc_value("ST")
        value = strategy.read(conn, ref, fc_val)
        print(f"  [int-strategy] {ref} → {value}")
        assert isinstance(value, int)


# ============================================================
# StringReader — 字符串
# ============================================================

class TestStringReader:
    """字符串值读取测试"""

    def test_read_string_strategy(self, connection):
        """直接测试 StringReader 策略"""
        from pyiec61850 import pyiec61850 as iec61850
        conn = connection.connection
        strategy = StringReader()
        if not hasattr(iec61850, "IedConnection_readStringValue"):
            pytest.skip("pyiec61850 不支持 readStringValue")

        # 尝试读取描述属性 dU
        ref = f"{connection.model_name}{connection.ld_name}/LLN0.Mod.dU"
        fc_val = iec61850.IEC61850_FC_DC
        value = strategy.read(conn, ref, fc_val)
        print(f"  [string] dU via DC → {value!r}")

        if value is None:
            ref = f"{connection.model_name}{connection.ld_name}/LLN0.NamPlt.vendor"
            fc_val = iec61850.IEC61850_FC_DC
            value = strategy.read(conn, ref, fc_val)
            print(f"  [string] vendor via DC → {value!r}")

        # 字符串读取可能返回 None（设备不支持），不做硬断言
        if value is not None:
            assert isinstance(value, str)


# ============================================================
# TimestampReader — 时标
# ============================================================

class TestTimestampReader:
    """时标值读取测试"""

    def test_read_timestamp_t(self, connection, model, registry):
        """通过 MetadataReader 读取 t (IedConnection_readObject → Timestamp_fromMmsValue)"""
        from src.proto.iec61850.core.metadata import MetadataReader

        for _, _, do in model.iter_dos():
            for da in do.das:
                if da.name == "t":
                    reader = MetadataReader()
                    result = reader.read_timestamp(connection, do.ref, fc="MX")
                    print(f"  [timestamp] {do.ref}.t → seconds={result.seconds}, ms={result.unix_timestamp_ms}, leap={result.leap_seconds_known}")
                    # 可能成功也可能设备不支持，不硬断
                    return
        pytest.skip("未找到 t DA")

    def test_read_timestamp_strategy_direct(self, connection):
        """直接用 TimestampReader 读取完整 EntryTime"""
        from pyiec61850 import pyiec61850 as iec61850
        conn = connection.connection
        strategy = TimestampReader()

        if hasattr(iec61850, "IedConnection_readTimestampValue"):
            # 某个 DO 的完整 t 属性
            ref = f"{connection.model_name}{connection.ld_name}/LLN0.Mod.t"
            fc_val = connection.get_fc_value("MX")
            value = strategy.read(conn, ref, fc_val)
            print(f"  [timestamp-direct] {ref} → {value}")
            if value is not None:
                assert isinstance(value, (int, float))


# ============================================================
# AutoDetectReader — 自动探测
# ============================================================

class TestAutoDetectReader:
    """自动探测读取测试"""

    def test_autodetect_unknown_type(self, connection):
        """对未知类型使用 AutoDetectReader"""
        from pyiec61850 import pyiec61850 as iec61850
        conn = connection.connection
        strategy = AutoDetectReader()

        # 读取已知存在的属性 (stVal)
        ref = f"{connection.model_name}{connection.ld_name}/LLN0.Mod.stVal"
        fc_val = connection.get_fc_value("ST")
        value = strategy.read(conn, ref, fc_val)
        print(f"  [autodetect] {ref} → {value}")
        assert value is not None, "自动探测应能读取已知属性"


# ============================================================
# Quality (q) 子属性 — 品质
# ============================================================

class TestQualityReader:
    """品质 (q) 子属性按需读取 — 旧版直接 MMS 路径"""

    def test_read_quality_sub_das(self, connection, model, registry):
        """通过 do_ref 直接读取 q.validity, q.source 等（旧方式）"""
        for _, _, do in model.iter_dos():
            for da in do.das:
                if da.name == "q" and da.sub_das:
                    from pyiec61850 import pyiec61850 as iec61850
                    conn = connection.connection
                    fc_val = connection.get_fc_value(da.fc)
                    success = 0
                    for bda in da.sub_das:
                        full_ref = f"{do.ref}.{bda.path}"
                        strategy = IntegerReader()
                        value = strategy.read(conn, full_ref, fc_val)
                        print(f"  [quality] {full_ref} ({bda.iec_type}) → {value}")
                        if value is not None:
                            assert isinstance(value, (int, bool))
                            success += 1
                    print(f"  [quality] 成功: {success}/{len(da.sub_das)}")
                    assert success > 0, "q 子属性全部读取失败"
                    return
        pytest.skip("未找到包含 q 子 DA 的 DO")


# ============================================================
# MetadataReader — 新按需读取服务
# ============================================================

class TestMetadataReader:
    """MetadataReader 按需读取服务测试"""

    @pytest.fixture
    def _find_do_ref(self, model):
        """找到第一个有 q/t 子 DA 的 DO 引用"""
        for _, _, do in model.iter_dos():
            for da in do.das:
                if da.name == "q" and da.sub_das:
                    return do.ref
        pytest.skip("未找到包含 q/t 子 DA 的 DO")

    def test_read_quality(self, connection, model, _find_do_ref):
        """MetadataReader.read_quality() — 返回 QualityInfo"""
        from src.proto.iec61850.core.metadata import MetadataReader, QualityInfo

        reader = MetadataReader()
        do_ref = _find_do_ref
        result = reader.read_quality(connection, do_ref, fc="MX")

        print(f"\n  [metadata] read_quality({do_ref}) →")
        print(f"    validity={result.validity}")
        print(f"    detail_quality={result.detail_quality}")
        print(f"    source={result.source}")
        print(f"    operator_blocked={result.operator_blocked}")
        print(f"    test={result.test}")
        print(f"    is_valid={result.is_valid}")

        assert isinstance(result, QualityInfo)
        assert result.is_readable, f"品质读取完全失败: {do_ref}"

    def test_read_timestamp(self, connection, model, _find_do_ref):
        """MetadataReader.read_timestamp() — 返回 TimestampInfo"""
        from src.proto.iec61850.core.metadata import MetadataReader, TimestampInfo

        reader = MetadataReader()
        do_ref = _find_do_ref
        result = reader.read_timestamp(connection, do_ref, fc="MX")

        print(f"\n  [metadata] read_timestamp({do_ref}) →")
        print(f"    seconds={result.seconds}")
        print(f"    fraction={result.fraction}")
        print(f"    time_accuracy={result.time_accuracy}")
        print(f"    unix_timestamp_ms={result.unix_timestamp_ms}")
        print(f"    to_dict()={result.to_dict()}")

        assert isinstance(result, TimestampInfo)
        assert result.is_readable, f"时标读取完全失败: {do_ref}"

    def test_read_metadata(self, connection, model, _find_do_ref):
        """MetadataReader.read_metadata() — 一次获取品质+时标"""
        from src.proto.iec61850.core.metadata import MetadataReader, MetadataInfo

        reader = MetadataReader()
        do_ref = _find_do_ref
        result = reader.read_metadata(connection, do_ref, fc="MX")

        print(f"\n  [metadata] read_metadata({do_ref}) →")
        print(f"    quality={result.quality.to_dict()}")
        print(f"    timestamp={result.timestamp.to_dict()}")

        assert isinstance(result, MetadataInfo)
        assert result.is_readable, f"元数据读取完全失败: {do_ref}"
        assert result.quality.is_readable, "品质子属性全部失败"
        assert result.timestamp.is_readable, "时标子属性全部失败"

    def test_quality_info_is_valid(self, connection, model, _find_do_ref):
        """QualityInfo.is_valid 派生属性"""
        from src.proto.iec61850.core.metadata import MetadataReader

        reader = MetadataReader()
        q = reader.read_quality(connection, _find_do_ref, fc="MX")
        # is_valid 是布尔值，不抛异常即可
        is_valid = q.is_valid
        print(f"  [metadata] is_valid={is_valid}")
        assert isinstance(is_valid, bool)

    def test_timestamp_unix_ms(self, connection, model, _find_do_ref):
        """TimestampInfo.unix_timestamp_ms 派生属性"""
        from src.proto.iec61850.core.metadata import MetadataReader

        reader = MetadataReader()
        t = reader.read_timestamp(connection, _find_do_ref, fc="MX")
        ts = t.unix_timestamp_ms
        print(f"  [metadata] unix_timestamp_ms={ts}")
        if ts is not None:
            assert isinstance(ts, int)
            assert ts > 0, f"unix_timestamp_ms 应 >0, 实际 {ts}"

    def test_empty_on_disconnected(self, model, _find_do_ref):
        """断开连接时返回空对象, 不抛异常"""
        from src.proto.iec61850.core.metadata import MetadataReader, QualityInfo, TimestampInfo
        from src.proto.iec61850.core.connection import Iec61850Connection

        reader = MetadataReader()
        # 使用未连接的 connection
        dead_conn = Iec61850Connection("127.0.0.1", 102)

        q = reader.read_quality(dead_conn, _find_do_ref)
        assert isinstance(q, QualityInfo)
        assert not q.is_readable

        t = reader.read_timestamp(dead_conn, _find_do_ref)
        assert isinstance(t, TimestampInfo)
        assert not t.is_readable


# ============================================================
# 连接管理测试
# ============================================================

class TestConnectionManagement:
    """连接/断开/重连测试"""

    def test_connect_disconnect(self):
        """连接和断开的完整生命周期"""
        conn = Iec61850Connection(TEST_HOST, TEST_PORT)
        assert conn.connect(auto_discover=False), "连接失败"
        assert conn.is_connected
        conn.disconnect()
        assert not conn.is_connected

    def test_reconnect(self):
        """断开后重新连接"""
        conn = Iec61850Connection(TEST_HOST, TEST_PORT)
        conn.connect(auto_discover=False)
        assert conn.is_connected
        conn.disconnect()
        conn.connect(auto_discover=False)
        assert conn.is_connected, "重连失败"
        conn.disconnect()

    def test_connection_context_manager(self):
        """使用 with 语句管理连接"""
        conn = Iec61850Connection(TEST_HOST, TEST_PORT)
        try:
            conn.connect(auto_discover=False)
            assert conn.is_connected
        finally:
            conn.disconnect()
        assert not conn.is_connected


# ============================================================
# 模型发现测试
# ============================================================

class TestModelDiscovery:
    """模型发现测试"""

    def test_discover_model(self, model):
        """模型发现后 IedModel 结构完整性"""
        assert model is not None
        assert len(model.lds) > 0, "未发现逻辑设备"
        print(f"  [model] LD 数量: {len(model.lds)}")

        total_lns = sum(len(ld.lns) for ld in model.lds)
        total_dos = sum(len(ln.dos) for ld in model.lds for ln in ld.lns)
        total_das = sum(len(do.das) for ld in model.lds for ln in ld.lns for do in ln.dos)
        print(f"  [model] LN: {total_lns}, DO: {total_dos}, DA: {total_das}")

        assert total_lns > 0, "未发现逻辑节点"
        assert total_dos > 0, "未发现数据对象"

    def test_point_refs_coverage(self, model, registry):
        """point_refs 测点覆盖"""
        refs = model.point_refs
        assert len(refs) > 0, "未生成任何测点"
        print(f"  [points] 总测点数: {len(refs)}")

        # 按类型分类
        type_counts: dict[str, int] = {}
        for addr, info in refs.items():
            t = info.get("iec_type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        print(f"  [points] 类型分布: {type_counts}")

    def test_q_t_sub_da_expansion(self, model):
        """验证 q 和 t 在模型结构中已展开为子 DA（但不作为测点）"""
        expanded_q = False
        expanded_t = False
        for _, _, do in model.iter_dos():
            for da in do.das:
                if da.name == "q" and da.sub_das:
                    expanded_q = True
                    print(f"  [q-expand] {do.ref}.q → {[bda.name for bda in da.sub_das]}")
                if da.name == "t" and da.sub_das:
                    expanded_t = True
                    print(f"  [t-expand] {do.ref}.t → {[bda.name for bda in da.sub_das]}")

        assert expanded_q, "q 未展开为子 DA"
        assert expanded_t, "t 未展开为子 DA"

    def test_q_t_not_in_point_refs(self, model):
        """验证 q 和 t 子属性不在 point_refs 中（避免测点膨胀）"""
        refs = model.point_refs
        q_count = sum(1 for addr in refs if ".q." in addr)
        t_count = sum(1 for addr in refs if ".t." in addr)
        print(f"  [point_refs] .q.* 测点数: {q_count}, .t.* 测点数: {t_count}")
        assert q_count == 0, f".q.* 不应作为测点, 实际 {q_count} 个"
        assert t_count == 0, f".t.* 不应作为测点, 实际 {t_count} 个"


# ============================================================
# 便捷入口
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
