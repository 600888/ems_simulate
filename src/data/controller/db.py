"""
数据库会话管理模块
根据配置自动选择 SQLite 或 MySQL
"""

from pathlib import Path

from sqlalchemy.orm import sessionmaker

from src.config.config import Config, resolve_config_path
from src.config.global_config import ROOT_DIR
from src.config.storage import get_storage_path
from src.data.controller.db_controller import DbController

# 导入所有模型，确保它们在 Base.metadata 中注册
import src.data.model  # noqa: F401
from src.data.model.base import Base

# 加载运行目录中可编辑的主配置文件
config_path = resolve_config_path(ROOT_DIR)
Config.load_config(str(config_path))

# 初始化数据库控制器
db_controller = DbController()

# 根据配置选择数据库类型
if Config.is_sqlite():
    # SQLite 模式
    configured_sqlite_path = Path(Config.sqlite_path)
    if configured_sqlite_path.is_absolute():
        sqlite_path = configured_sqlite_path
    elif configured_sqlite_path.parts and configured_sqlite_path.parts[0].lower() == "data":
        # The conventional data/ems.db path follows the user-selected data directory.
        sqlite_path = Path(get_storage_path("data_directory")).joinpath(*configured_sqlite_path.parts[1:])
    else:
        sqlite_path = Path(ROOT_DIR) / configured_sqlite_path
    db_controller.init_db(
        db_type="sqlite",
        db_path=str(sqlite_path),
    )
else:
    # MySQL 模式
    db_controller.init_db(
        db_type="mysql",
        ip=Config.host,
        port=Config.port,
        user_name=Config.username,
        pass_word=Config.password,
        database=Config.database,
    )

# 创建会话工厂
engine = db_controller.engine
local_session = sessionmaker(engine, expire_on_commit=False)
base = Base()
