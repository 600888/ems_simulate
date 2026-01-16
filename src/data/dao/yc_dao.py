from pymysql import DatabaseError
from src.data.model.yc import Yc
from src.data.log import log
from src.data.controller.db import local_session


class YcDao:
    def __init__(self):
        pass

    @classmethod
    def get_yc_list(cls, grp_code: str) -> list:
        """
        获取遥测列表
        """

        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(Yc).where(grp_code=grp_code).all()
                    return [item.to_dict() for item in result]
        except DatabaseError as e:
            log.error(f"通道获取失败: {str(e)}")
            raise e
        except Exception as e:
            log.critical(f"系统异常: {str(e)}")
            raise e
        return []
