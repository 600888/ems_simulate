import json
import os
import time
from typing import Optional

from src.config.db.db_config import DbMysqlConfig
from src.data.model.base import Base
from src.data.model.channel import Channel
from src.data.model.yc import Yc
from src.data.model.yx import Yx


class DbController:
    channel = Channel()
    yc = Yc()
    yx = Yx()

    def __init__(self) -> None:
        self.db_config = None

    def close_db(self):
        self.db_config.commit_session()
        self.db_config.close_session()
        self.db_config.close_engine()

    def init_mysql_db(self, ip, port, user_name, pass_word) -> bool:
        self.db_config = DbMysqlConfig()
        self.db_config.set_db_config(ip, port, user_name, pass_word)
        self.db_config.create_engine("net", is_create=False)
