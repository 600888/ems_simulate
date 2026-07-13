"""IEC 61850 本地模型缓存持久化回归测试。"""

import json
import time
from unittest.mock import Mock

from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.model.cache import ModelCache
from src.proto.iec61850.model.ied_model import IedModel, LDModel, LNModel, RCBRef


def test_discovered_model_cache_does_not_expire_after_thirty_minutes(tmp_path):
    key = "192.168.1.100:102"
    model = IedModel(
        host="192.168.1.100",
        port=102,
        _point_refs={"LD0/LLN0.Mod.stVal": {"ref": "LD0/LLN0.Mod.stVal", "fc": "ST"}},
    )

    writer = ModelCache()
    writer.set_cache_dir(tmp_path)
    writer.set(key, model)

    cache_file = tmp_path / "192.168.1.100_102_model.json"
    data = json.loads(cache_file.read_text(encoding="utf-8"))
    data["_cached_at"] = time.time() - 31 * 60
    cache_file.write_text(json.dumps(data), encoding="utf-8")

    # 模拟应用重启：新实例只能从磁盘恢复旧缓存。
    reader = ModelCache()
    reader.set_cache_dir(tmp_path)

    assert reader.has(key) is True
    persisted_before_read = cache_file.read_bytes()
    modified_before_read = cache_file.stat().st_mtime_ns
    restored = reader.get(key)
    assert restored is not None
    assert restored.host == model.host
    assert restored._point_refs == model._point_refs
    assert cache_file.exists()
    assert cache_file.read_bytes() == persisted_before_read
    assert cache_file.stat().st_mtime_ns == modified_before_read


def test_model_cache_preserves_report_rpt_id(tmp_path):
    key = "192.168.1.100:102"
    report = RCBRef(
        name="rpSystemCtrlMeas01",
        ref="LD0/LLN0.rpSystemCtrlMeas01",
        rcb_type="URCB",
        rpt_id="rpSystemCtrlMeas01",
        dat_set="dsSystemCtrlMeas",
    )
    model = IedModel(
        host="192.168.1.100",
        port=102,
        lds=(LDModel(name="LD0", lns=(LNModel(name="LLN0", rcb_list=(report,)),)),),
        _point_refs={"LD0/LLN0.Mod.stVal": {"ref": "LD0/LLN0.Mod.stVal", "fc": "ST"}},
    )

    writer = ModelCache()
    writer.set_cache_dir(tmp_path)
    writer.set(key, model)

    reader = ModelCache()
    reader.set_cache_dir(tmp_path)
    restored = reader.get(key)

    assert restored is not None
    assert restored.lds[0].lns[0].rcb_list[0].rpt_id == "rpSystemCtrlMeas01"


def _make_cache_validation_client(*, connected: bool, online_lds: list[str]):
    client = IEC61850Client.__new__(IEC61850Client)
    client._conn = Mock()
    client._conn.is_connected = connected
    client._conn.browse_logical_devices.return_value = online_lds
    return client


def test_cached_model_is_rejected_when_online_logical_devices_changed():
    client = _make_cache_validation_client(connected=True, online_lds=["PCS01PIGO"])
    cached = IedModel(lds=(LDModel(name="LC001RACK06"),))

    assert client._cached_model_matches_online_server(cached) is False


def test_cached_model_is_accepted_when_online_logical_devices_match():
    client = _make_cache_validation_client(
        connected=True,
        online_lds=["LC001RACK07", "LC001RACK06"],
    )
    cached = IedModel(
        lds=(LDModel(name="LC001RACK06"), LDModel(name="LC001RACK07")),
    )

    assert client._cached_model_matches_online_server(cached) is True


def test_cached_model_can_still_be_loaded_offline():
    client = _make_cache_validation_client(connected=False, online_lds=[])
    cached = IedModel(lds=(LDModel(name="LC001RACK06"),))

    assert client._cached_model_matches_online_server(cached) is True
    client._conn.browse_logical_devices.assert_not_called()


def test_cached_model_is_rejected_when_online_directory_cannot_be_read():
    client = _make_cache_validation_client(connected=True, online_lds=[])
    cached = IedModel(lds=(LDModel(name="LC001RACK06"),))

    assert client._cached_model_matches_online_server(cached) is False
