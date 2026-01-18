"""
配置加载模块
支持从 config.ini 加载数据库和数据源配置
"""

import os
from configparser import ConfigParser
from typing import Optional
from src.enums.data_source import DataSource


class Config:
    """全局配置类"""

    # 数据库类型配置
    db_type: str = "sqlite"  # sqlite 或 mysql
    sqlite_path: str = "data/ems.db"

    # MySQL 配置
    host: str = "127.0.0.1"
    port: str = "3306"
    username: str = "nandu"
    password: str = "nandu123"
    database: str = "net"

    # 默认协议配置
    DEFAULT_PORT: int = 502
    IEC104_DEFAULT_PORT: int = 2404
    DLT645_DEFAULT_PORT: int = 8899
    DEFAULT_IP: str = "0.0.0.0"

    # 数据源配置
    data_source: DataSource = DataSource.Db

    @classmethod
    def load_config(cls, config_file: str) -> None:
        """加载配置文件并更新配置类属性
        
        Args:
            config_file: 配置文件路径
        """
        try:
            config = ConfigParser()
            if os.path.exists(config_file):
                config.read(config_file, encoding="utf8")

                # 数据库类型配置
                if "database" in config:
                    cls.db_type = config["database"].get("type", cls.db_type)
                    cls.sqlite_path = config["database"].get(
                        "sqlite_path", cls.sqlite_path
                    )

                # MySQL 配置
                if "mysql" in config:
                    cls.host = config["mysql"].get("host", cls.host)
                    cls.port = config["mysql"].get("port", cls.port)
                    cls.username = config["mysql"].get("username", cls.username)
                    cls.password = config["mysql"].get("password", cls.password)
                    cls.database = config["mysql"].get("database", cls.database)

                # 数据源配置
                if "data_source" in config and "type" in config["data_source"]:
                    data_source = config["data_source"]["type"]
                    cls.data_source = (
                        DataSource.Db if data_source == "db" else DataSource.CSV
                    )
            else:
                print(f"Warning: Config file {config_file} not found, using defaults")
        except Exception as e:
            print(f"Error loading config: {str(e)}")

    @classmethod
    def is_sqlite(cls) -> bool:
        """判断是否使用 SQLite"""
        return cls.db_type.lower() == "sqlite"

    @classmethod
    def is_mysql(cls) -> bool:
        """判断是否使用 MySQL"""
        return cls.db_type.lower() == "mysql"
