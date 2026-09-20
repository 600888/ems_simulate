import json
import os

from sqlalchemy import URL, create_engine, event, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
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
        self.engine = create_engine(
            "sqlite:///" + self.db_path,
            echo=False,
            pool_pre_ping=True,
        )

        @event.listens_for(self.engine, "connect")
        def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
            finally:
                cursor.close()

        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
            connection.exec_driver_sql("PRAGMA synchronous=NORMAL")

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
                with open(file_path, encoding="utf-8") as f:
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

    def get_url(self, db_name: str | None) -> URL:
        return URL.create(
            "mysql+pymysql",
            username=self._user_name,
            password=self._password,
            host=self._host,
            port=int(self._port),
            database=db_name,
        )

    def _ensure_database(self, db_name: str) -> None:
        """仅在数据库不存在时建库，已有库不要求额外的 CREATE 权限。"""
        # 使用同步驱动，也供异步引擎创建前的初始化流程复用。
        mysql_url = DbMysqlConfig.get_url(self, db_name)
        probe_engine = create_engine(mysql_url, echo=False)
        try:
            with probe_engine.connect():
                return
        except OperationalError as exc:
            if not exc.orig.args or exc.orig.args[0] != 1049:  # ER_BAD_DB_ERROR
                raise
        finally:
            probe_engine.dispose()

        server_engine = create_engine(DbMysqlConfig.get_url(self, None), echo=False, isolation_level="AUTOCOMMIT")
        try:
            # 数据库名是标识符，不能使用值参数绑定；由 MySQL 方言转义。
            quoted_name = server_engine.dialect.identifier_preparer.quote_identifier(db_name)
            with server_engine.connect() as connection:
                connection.exec_driver_sql(f"CREATE DATABASE IF NOT EXISTS {quoted_name} CHARACTER SET utf8mb4")
        finally:
            server_engine.dispose()

    def create_engine(self, db_name: str, is_create_db: bool = True) -> None:
        if is_create_db:
            self._ensure_database(db_name)
        mysql_url = self.get_url(db_name)
        self.engine = create_engine(
            mysql_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=1800,
        )

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

    def get_url(self, db_name: str | None) -> URL:
        return URL.create(
            "mysql+aiomysql",
            username=self._user_name,
            password=self._password,
            host=self._host,
            port=int(self._port),
            database=db_name,
        )

    def create_async_engine(self, db_name: str, is_create_db: bool = True) -> None:
        if is_create_db:
            self._ensure_database(db_name)
        mysql_url = self.get_url(db_name)
        self.engine = create_async_engine(
            mysql_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=1800,
        )

    async def is_connect(self) -> bool:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False
