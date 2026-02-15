"""
测点映射服务
"""
import json
from typing import List, Optional, Dict, Any

from src.data.dao.point_mapping_dao import PointMappingDao
from src.data.model.point_mapping import PointMappingDict as PointMappingModelDict


class PointMappingService:

    @staticmethod
    def create_mapping(
        device_name: str,
        target_point_code: str,
        source_point_codes: List[Dict[str, str]],
        formula: str,
        enable: bool = True
    ) -> Optional[Dict[str, Any]]:
        """创建新的映射"""
        mapping_data = {
            "device_name": device_name,
            "target_point_code": target_point_code,
            "source_point_codes": json.dumps(source_point_codes),
            "formula": formula,
            "enable": enable
        }
        # MyPy check: ignore the typed dict mismatch for now as we pass a dict to SQLAlchemy model
        mapping = PointMappingDao.create_mapping(mapping_data) # type: ignore
        if mapping:
            return mapping.to_dict()
        return None

    @staticmethod
    def get_all_mappings() -> List[Dict[str, Any]]:
        """获取所有映射"""
        mappings = PointMappingDao.get_all_mappings()
        return [m.to_dict() for m in mappings]

    @staticmethod
    def get_mapping_by_id(mapping_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取映射"""
        mapping = PointMappingDao.get_mapping_by_id(mapping_id)
        if mapping:
            return mapping.to_dict()
        return None


    @staticmethod
    def update_mapping(mapping_id: int, data: Dict[str, Any]) -> bool:
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
