import json
import os
from typing import Type

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import (
    sessionmaker,
    DeclarativeBase,
)


class Base(DeclarativeBase):
    pass


class DbConfig:
    engine = None
    session = None
    base = None

    def __init__(self) -> None:
        pass

    def create_base(self, base: Type[Base]) -> None:
        self.base = base

    def create_session(self) -> None:
        Session = sessionmaker(self.engine, expire_on_commit=False)
        self.session = Session()

    def flush_session(self) -> None:
        self.session.flush()

    def commit_session(self) -> None:
        self.session.commit()

    def rollback_session(self) -> None:
        self.session.rollback()

    def close_session(self) -> None:
        self.session.close()

    def create_table(self) -> None:
        self.base.metadata.create_all(self.engine)

    def close_engine(self) -> None:
        self.engine.dispose()

    def get_engine(self):
        return self.engine


class DbMysqlConfig(DbConfig):
    def __init__(self) -> None:
        super().__init__()
        self._host = "127.0.0.1"
        self._port = "3306"
        self._user_name = "nandu"
        self._password = "nandu123"

    def read_config_from_json(self, file_path: str = "") -> None:
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    host = data["host"]
                    port = data["port"]
                    user_name = data["username"]
                    pass_word = data["password"]
                    self.set_db_config(host, port, user_name, pass_word)
                print("读取mysql配置文件成功！")
            except Exception as e:
                print(e)

    def set_db_config(self, host, port, user_name, pass_word):
        self._host = host
        self._port = port
        self._user_name = user_name
        self._password = pass_word

    def connect_db(self, db_name: str) -> str:
        mysql_url = "mysql+pymysql://"
        mysql_url += self._user_name + ":"
        mysql_url += self._password + "@"
        mysql_url += self._host + ":" + self._port + "/"
        print(mysql_url + db_name)
        self.engine = create_engine(mysql_url + db_name, echo=False, pool_size=20)
        return mysql_url

    def create_engine(self, db_name: str, is_create=True) -> None:
        mysql_url = self.connect_db(db_name)
        if is_create:
            with self.engine.connect() as connection:
                connection.execute(text("DROP DATABASE IF EXISTS " + db_name))
                connection.execute(text("CREATE DATABASE IF NOT EXISTS " + db_name))
        self.engine = create_engine(mysql_url + db_name, echo=False)

    def is_connect(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False
