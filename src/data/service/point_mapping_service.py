"""
测点映射服务
"""

import json
from typing import Any

from src.data.dao.point_mapping_dao import PointMappingDao


class PointMappingService:
    @staticmethod
    def create_mapping(
        device_name: str,
        target_point_code: str,
        source_point_codes: list[dict[str, str]],
        formula: str,
        enable: bool = True,
    ) -> dict[str, Any] | None:
        """创建新的映射"""
        mapping_data = {
            "device_name": device_name,
            "target_point_code": target_point_code,
            "source_point_codes": json.dumps(source_point_codes),
            "formula": formula,
            "enable": enable,
        }
        # MyPy check: ignore the typed dict mismatch for now as we pass a dict to SQLAlchemy model
        mapping = PointMappingDao.create_mapping(mapping_data)  # type: ignore
        if mapping:
            return mapping.to_dict()
        return None

    @staticmethod
    def get_all_mappings() -> list[dict[str, Any]]:
        """获取所有映射"""
        mappings = PointMappingDao.get_all_mappings()
        return [m.to_dict() for m in mappings]

    @staticmethod
    def get_mapping_by_id(mapping_id: int) -> dict[str, Any] | None:
        """根据ID获取映射"""
        mapping = PointMappingDao.get_mapping_by_id(mapping_id)
        if mapping:
            return mapping.to_dict()
        return None

    @staticmethod
    def update_mapping(mapping_id: int, data: dict[str, Any]) -> bool:
        """更新映射"""
        update_data = {}
        if "device_name" in data:
            update_data["device_name"] = data["device_name"]
        if "target_point_code" in data:
            update_data["target_point_code"] = data["target_point_code"]
        if "source_point_codes" in data:
            update_data["source_point_codes"] = json.dumps(data["source_point_codes"])
        if "formula" in data:
            update_data["formula"] = data["formula"]
        if "enable" in data:
            update_data["enable"] = data["enable"]

        return PointMappingDao.update_mapping(mapping_id, update_data)

    @staticmethod
    def delete_mapping(mapping_id: int) -> bool:
        """删除映射"""
        return PointMappingDao.delete_mapping(mapping_id)

    @staticmethod
    def clone_for_device(source_device_name: str, target_device_name: str) -> int:
        """复制目标属于源设备的测点映射，并重写映射中的设备自引用。"""
        copied_count = 0
        for mapping in PointMappingService.get_all_mappings():
            if mapping.get("device_name") != source_device_name:
                continue

            try:
                source_points = json.loads(mapping.get("source_point_codes") or "[]")
            except (json.JSONDecodeError, TypeError):
                continue

            if not isinstance(source_points, list):
                continue

            remapped_sources = []
            for item in source_points:
                if not isinstance(item, dict):
                    remapped_sources.append(item)
                    continue
                cloned_item = dict(item)
                if cloned_item.get("device_name") == source_device_name:
                    cloned_item["device_name"] = target_device_name
                remapped_sources.append(cloned_item)

            copied = PointMappingService.create_mapping(
                device_name=target_device_name,
                target_point_code=mapping["target_point_code"],
                source_point_codes=remapped_sources,
                formula=mapping["formula"],
                enable=bool(mapping.get("enable", True)),
            )
            if copied:
                copied_count += 1

        return copied_count
