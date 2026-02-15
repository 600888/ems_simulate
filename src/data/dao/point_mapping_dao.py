"""
测点映射 DAO
"""
from typing import List, Optional
from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError

from src.data.model.point_mapping import PointMapping, PointMappingDict
from src.data.controller.db import local_session
from src.log import log


class PointMappingDao:

    @classmethod
    def create_mapping(cls, mapping_data: PointMappingDict) -> Optional[PointMapping]:
        """创建映射规则"""
        try:
            with local_session() as session:
                with session.begin():
                    mapping = PointMapping(**mapping_data)
                    session.add(mapping)
                    session.flush()
                    session.refresh(mapping)
                    session.expunge(mapping) # Detach from session before it closes
                    return mapping
        except Exception as e:
            log.error(f"Failed to create point mapping: {str(e)}")
            return None

    @classmethod
    def get_all_mappings(cls) -> List[PointMapping]:
        """获取所有映射规则"""
        try:
            with local_session() as session:
                with session.begin():
                    stmt = select(PointMapping)
                    result = session.scalars(stmt).all()
                    for item in result:
                        session.expunge(item)
                    return list(result)
        except Exception as e:
            log.error(f"Failed to get all point mappings: {str(e)}")
            return []

    @classmethod
    def get_mapping_by_id(cls, mapping_id: int) -> Optional[PointMapping]:
        """根据ID获取映射规则"""
        try:
            with local_session() as session:
                with session.begin():
                    mapping = session.get(PointMapping, mapping_id)
                    if mapping:
                        session.expunge(mapping)
                    return mapping
        except Exception as e:
            log.error(f"Failed to get point mapping by id {mapping_id}: {str(e)}")
            return None

    @classmethod
    def update_mapping(cls, mapping_id: int, mapping_data: dict) -> bool:
        """更新映射规则"""
        try:
            with local_session() as session:
                with session.begin():
                    mapping = session.get(PointMapping, mapping_id)
                    if not mapping:
                        return False
                    
                    for key, value in mapping_data.items():
                        if hasattr(mapping, key):
                            setattr(mapping, key, value)
                    return True
        except Exception as e:
            log.error(f"Failed to update point mapping {mapping_id}: {str(e)}")
            return False

    @classmethod
    def delete_mapping(cls, mapping_id: int) -> bool:
        """删除映射规则"""
        try:
            with local_session() as session:
                with session.begin():
                    stmt = delete(PointMapping).where(PointMapping.id == mapping_id)
                    result = session.execute(stmt)
                    return result.rowcount > 0
        except Exception as e:
            log.error(f"Failed to delete point mapping {mapping_id}: {str(e)}")
            return False
