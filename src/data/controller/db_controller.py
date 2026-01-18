"""
数据库控制器
支持 SQLite 和 MySQL 数据库的初始化和管理
"""

import os
from typing import Optional

from src.config.db.db_config import DbMysqlConfig, DbSqliteConfig
from src.data.model.base import Base


class DbController:
    """数据库控制器，统一管理数据库连接"""

    def __init__(self) -> None:
        self.db_config: Optional[DbMysqlConfig | DbSqliteConfig] = None
        self._db_type: str = "sqlite"

    @property
    def engine(self):
        """获取数据库引擎"""
        if self.db_config:
            return self.db_config.engine
        return None

    def close_db(self) -> None:
        """关闭数据库连接"""
        if self.db_config:
            self.db_config.close_engine()

    def init_db(self, db_type: str, **kwargs) -> bool:
        """根据类型初始化数据库
        
        Args:
            db_type: 数据库类型 (sqlite/mysql)
            **kwargs: 数据库配置参数
            
        Returns:
            bool: 初始化是否成功
        """
        self._db_type = db_type.lower()

        if self._db_type == "sqlite":
            return self.init_sqlite_db(
                db_path=kwargs.get("db_path", "data/ems.db")
            )
        else:
            return self.init_mysql_db(
                ip=kwargs.get("ip", "127.0.0.1"),
                port=kwargs.get("port", "3306"),
                user_name=kwargs.get("user_name", "root"),
                pass_word=kwargs.get("pass_word", ""),
                database=kwargs.get("database", "ems_simulate"),
            )

    def init_sqlite_db(self, db_path: str) -> bool:
        """初始化 SQLite 数据库
        
        Args:
            db_path: 数据库文件路径
            
        Returns:
            bool: 初始化是否成功
        """
        try:
            # 确保目录存在
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            self.db_config = DbSqliteConfig()
            self.db_config.set_db_path(db_path)
            self.db_config.create_engine()

            # 创建所有表
            Base.metadata.create_all(self.db_config.engine)

            print(f"SQLite 数据库初始化成功: {db_path}")
            return True
        except Exception as e:
            print(f"SQLite 数据库初始化失败: {e}")
            return False

    def init_mysql_db(
        self,
        ip: str,
        port: str,
        user_name: str,
        pass_word: str,
        database: str = "net",
    ) -> bool:
        """初始化 MySQL 数据库
        
        Args:
            ip: MySQL 主机地址
            port: MySQL 端口
            user_name: 用户名
            pass_word: 密码
            database: 数据库名
            
        Returns:
            bool: 初始化是否成功
        """
        try:
            self.db_config = DbMysqlConfig()
            self.db_config.set_db_config(ip, port, user_name, pass_word)
            self.db_config.create_engine(database, is_create_db=False)

            print(f"MySQL 数据库连接成功: {ip}:{port}/{database}")
            return True
        except Exception as e:
            print(f"MySQL 数据库连接失败: {e}")
            return False

    def is_sqlite(self) -> bool:
        """是否使用 SQLite"""
        return self._db_type == "sqlite"

    def is_mysql(self) -> bool:
        """是否使用 MySQL"""
        return self._db_type == "mysql"
