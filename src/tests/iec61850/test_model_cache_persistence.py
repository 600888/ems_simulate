"""IEC 61850 本地模型缓存持久化回归测试。"""

import json
import time

from src.proto.iec61850.model.cache import ModelCache
from src.proto.iec61850.model.ied_model import IedModel


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
