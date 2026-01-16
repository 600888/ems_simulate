import os
from configparser import ConfigParser
from typing import Optional
from src.enums.data_source import DataSource


class Config:
    # 数据库配置 - 设置默认值以提高鲁棒性
    host: str = "127.0.0.1"
    port: str = "3306"
    username: str = "nandu"
    password: str = "nandu123"
    database: str = "ems_simulate"

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
                
                # 安全地获取配置值，避免KeyError
                if "mysql" in config:
                    cls.host = config["mysql"].get("host", cls.host)
                    cls.port = config["mysql"].get("port", cls.port)
                    cls.username = config["mysql"].get("username", cls.username)
                    cls.password = config["mysql"].get("password", cls.password)
                    cls.database = config["mysql"].get("database", cls.database)
                
                if "data_source" in config and "type" in config["data_source"]:
                    data_source = config["data_source"]["type"]
                    cls.data_source = DataSource.Db if data_source == "db" else DataSource.CSV
            else:
                print(f"Warning: Config file {config_file} not found, using default values")
        except Exception as e:
            print(f"Error loading config: {str(e)}")
            # 发生异常时继续使用默认值
