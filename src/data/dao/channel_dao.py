from typing import List
from pymysql import DatabaseError
from src.data.model.channel import Channel, ChannelDict
from src.data.log import log
from src.data.controller.db import local_session


class ChannelDao:
    def __init__(self):
        pass

    @classmethod
    def get_channel_list(cls) -> List[ChannelDict]:
        """
        获取所有通道列表
        """

        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(Channel).where(Channel.enable==True).all()
                    log.info(f"获取所有通道列表成功")
                    return [item.to_dict() for item in result]
        except DatabaseError as e:
            log.error(f"通道获取失败: {str(e)}")
            raise e
        except Exception as e:
            log.critical(f"系统异常: {str(e)}")
            raise e
        return []
