"""PointRegistry 衍生逻辑 — 从 IedModel 派生，不再独立发现

连接时:
  ModelDiscoveryService.discover() → IedModel (缓存)
  build_registry_from_model() → PointRegistry (派生)

替代 DataModelsPlugin.discover_model() 的独立遍历。
"""

from __future__ import annotations

from typing import Any

from ..log import log
from .ied_model import IedModel


def build_registry_from_model(model: IedModel, registry: Any) -> list[dict[str, Any]]:
    """从 IedModel 构建 PointRegistry — 替代 DataModelsPlugin.discover_model()

    Args:
        model: 已发现的 IedModel
        registry: 待填充的 PointRegistry 实例

    Returns:
        发现的测点列表 (向后兼容 DataModelsPlugin.discover_model() 返回格式)
    """
    discovered_points: list[dict[str, Any]] = []
    # 模型发现/加载是全量替换，不能把新模型叠加到旧注册表上。
    # 兼容测试或外部传入的简化 registry 实现。
    clear_registry = getattr(registry, "clear", None)
    if callable(clear_registry):
        clear_registry()
    else:
        registry.discovered_goose_items.clear()

    # 填充测点映射
    for address, info in model.point_refs.items():
        registry.set_ref(address, info["ref"])
        registry.set_fc(address, info["fc"])
        registry.set_iec_type(address, info["iec_type"])

        point_entry: dict[str, Any] = {
            "address": address,
            "frame_type": info["frame_type"],
            "ref": info["ref"],
            "code": info.get("code", ""),
            "fc": info["fc"],
            "iec_type": info["iec_type"],
        }
        if "name" in info:
            registry.set_name(address, info["name"])
            point_entry["name"] = info["name"]

        discovered_points.append(point_entry)

    # 填充 GOOSE 控制块
    for goose_item in model.goose_items:
        discovered_points.append(goose_item)
        registry.discovered_goose_items.append(goose_item)
        log.info(
            f"发现 GOOSE 控制块: {goose_item['go_cb_ref']}, "
            f"appID=0x{(goose_item.get('app_id') or 0):04X}, "
            f"ds={goose_item.get('data_set_ref', '')}"
        )

    # 填充 DataSet 列表
    datasets = []
    for ld in model.lds:
        for ln in ld.lns:
            for ds in ln.datasets:
                ds_dict = ds.to_dict()
                ds_dict["ld"] = ld.name
                ds_dict["ln"] = ln.name
                ds_dict["member_count"] = len(ds.members)
                datasets.append(ds_dict)
    registry.discovered_datasets = datasets

    log.info(f"从 IedModel 派生完成, 填充了 {len(discovered_points)} 个测点, {len(datasets)} 个 DataSet")
    return discovered_points
