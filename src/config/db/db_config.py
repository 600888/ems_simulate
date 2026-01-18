import json
import os

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from src.config.env import conf_path


class DbConfig:
    engine = None
    session = None
    base = None

    def __init__(self) -> None:
        pass

    def create_base(self, base) -> None:
        self.base = base

    def create_table(self) -> None:
        self.base.metadata.create_all(self.engine)

    def close_engine(self) -> None:
        self.engine.dispose()


class DbSqliteConfig(DbConfig):
    db_path = None

    def __init__(self) -> None:
        super().__init__()

    def init_db(self) -> None:
        self.remove_db()
        self.create_engine()

    def set_db_path(self, db_path: str) -> None:
        self.db_path = db_path

    def create_engine(self) -> None:
        self.engine = create_engine("sqlite:///" + self.db_path, echo=False)

    def remove_db(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)


class DbMysqlConfig(DbConfig):
    default_path = os.path.join(conf_path, "mysql.json")

    def __init__(self) -> None:
        super().__init__()
        self._host = "10.10.111.5"
        self._port = "3306"
        self._user_name = "nandu"
        self._password = "nandu123"

    def read_config_from_json(self, file_path: str = default_path) -> None:
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

    def get_url(self, db_name: str):
        mysql_url = "mysql+pymysql://"
        mysql_url += self._user_name + ":"
        mysql_url += self._password + "@"
        mysql_url += self._host + ":" + self._port + "/"
        mysql_url += db_name
        print(mysql_url)
        return mysql_url

    def create_engine(self, db_name: str, is_create_db: bool = False) -> None:
        mysql_url = self.get_url(db_name)
        if is_create_db:
            self.engine = create_engine(mysql_url, echo=False)
            with self.engine.connect() as connection:
                connection.execute(text("DROP DATABASE IF EXISTS " + db_name))
                connection.execute(text("CREATE DATABASE IF NOT EXISTS " + db_name))
        self.engine = create_engine(mysql_url, echo=False, pool_size=100, max_overflow=50, pool_pre_ping=True)

    def is_connect(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False


class DbMysqlAsyncConfig(DbMysqlConfig):
    engine = None

    def get_engine(self):
        return self.engine

    def get_url(self, db_name: str):
        mysql_url = "mysql+aiomysql://"
        mysql_url += self._user_name + ":"
        mysql_url += self._password + "@"
        mysql_url += self._host + ":" + self._port + "/"
        mysql_url += db_name
        print(mysql_url)
        return mysql_url

    def create_async_engine(self, db_name: str, is_create_db: bool = False) -> None:
        mysql_url = self.get_url(db_name)
        if is_create_db:
            self.engine = create_engine(mysql_url, echo=False)
            with self.engine.connect() as connection:
                connection.execute(text("DROP DATABASE IF EXISTS " + db_name))
                connection.execute(text("CREATE DATABASE IF NOT EXISTS " + db_name))
        self.engine = create_async_engine(mysql_url, echo=False, future=True, pool_size=100, max_overflow=50,
                                          pool_pre_ping=True)

    async def is_connect(self) -> bool:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False
