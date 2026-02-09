"""
从机数据访问层 (SlaveDao)
"""

from typing import List, Optional
from sqlalchemy import select, delete, update

from src.data.model import Slave, SlaveDict
from src.data.controller.db import local_session
from src.log import log


class SlaveDao:
    """从机数据访问类"""

    @classmethod
    def get_slaves_by_channel(cls, channel_id: int) -> List[SlaveDict]:
        """获取通道下所有从机"""
        try:
            with local_session() as session:
                with session.begin():
                    stmt = select(Slave).where(
                        Slave.channel_id == channel_id,
                        Slave.enable == True
                    ).order_by(Slave.slave_id)
                    result = session.execute(stmt).scalars().all()
                    return [slave.to_dict() for slave in result]
        except Exception as e:
            log.error(f"获取从机列表失败: {e}")
            return []

    @classmethod
    def get_slave_ids_by_channel(cls, channel_id: int) -> List[int]:
        """获取通道下所有从机ID列表"""
        try:
            with local_session() as session:
                with session.begin():
                    stmt = select(Slave.slave_id).where(
                        Slave.channel_id == channel_id,
                        Slave.enable == True
                    ).order_by(Slave.slave_id)
                    result = session.execute(stmt).scalars().all()
                    return list(result)
        except Exception as e:
            log.error(f"获取从机ID列表失败: {e}")
            return []

    @classmethod
    def slave_exists(cls, channel_id: int, slave_id: int) -> bool:
        """检查从机是否存在"""
        try:
            with local_session() as session:
                with session.begin():
                    stmt = select(Slave).where(
                        Slave.channel_id == channel_id,
                        Slave.slave_id == slave_id
                    )
                    result = session.execute(stmt).scalar_one_or_none()
                    return result is not None
        except Exception as e:
            log.error(f"检查从机存在性失败: {e}")
            return False

    @classmethod
    def create_slave(cls, channel_id: int, slave_id: int, name: Optional[str] = None) -> bool:
        """创建从机"""
        try:
            with local_session() as session:
                with session.begin():
                    stmt = select(Slave).where(
                        Slave.channel_id == channel_id,
                        Slave.slave_id == slave_id
                    )
                    exists = session.execute(stmt).scalar_one_or_none()
                    
                    if exists:
                        log.warning(f"从机已存在: channel_id={channel_id}, slave_id={slave_id}")
                        return False
                    
                    slave = Slave(
                        channel_id=channel_id,
                        slave_id=slave_id,
                        name=name or f"从机{slave_id}",
                        enable=True
                    )
                    session.add(slave)
                    log.info(f"创建从机成功: channel_id={channel_id}, slave_id={slave_id}")
                    return True
        except Exception as e:
            log.error(f"创建从机失败: {e}")
            return False

    @classmethod
    def delete_slave(cls, channel_id: int, slave_id: int) -> bool:
        """删除从机"""
        try:
            with local_session() as session:
                with session.begin():
                    stmt = delete(Slave).where(
                        Slave.channel_id == channel_id,
                        Slave.slave_id == slave_id
                    )
                    result = session.execute(stmt)
                    if result.rowcount > 0:
                        log.info(f"删除从机成功: channel_id={channel_id}, slave_id={slave_id}")
                        return True
                    else:
                        log.warning(f"从机不存在: channel_id={channel_id}, slave_id={slave_id}")
                        return False
        except Exception as e:
            log.error(f"删除从机失败: {e}")
            return False

    @classmethod
    def update_slave_id(cls, channel_id: int, old_slave_id: int, new_slave_id: int) -> bool:
        """更新从机地址"""
        try:
            with local_session() as session:
                with session.begin():
                    # Check new slave id existence directly
                    check_stmt = select(Slave).where(
                        Slave.channel_id == channel_id,
                        Slave.slave_id == new_slave_id
                    )
                    if session.execute(check_stmt).scalar_one_or_none():
                         log.warning(f"目标从机地址已存在: channel_id={channel_id}, slave_id={new_slave_id}")
                         return False

                    stmt = update(Slave).where(
                        Slave.channel_id == channel_id,
                        Slave.slave_id == old_slave_id
                    ).values(slave_id=new_slave_id)
                    result = session.execute(stmt)
                    if result.rowcount > 0:
                        log.info(f"更新从机地址成功: {old_slave_id} -> {new_slave_id}")
                        return True
                    else:
                        log.warning(f"从机不存在: channel_id={channel_id}, slave_id={old_slave_id}")
                        return False
        except Exception as e:
            log.error(f"更新从机地址失败: {e}")
            return False
