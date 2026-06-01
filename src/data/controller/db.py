"""
数据库会话管理模块
根据配置自动选择 SQLite 或 MySQL
"""

from pathlib import Path

from sqlalchemy.orm import sessionmaker

from src.config.config import Config
from src.config.global_config import ROOT_DIR
from src.data.controller.db_controller import DbController

# 导入所有模型，确保它们在 Base.metadata 中注册
import src.data.model  # noqa: F401
from src.data.model.base import Base

# 加载配置
config_path = Path(ROOT_DIR) / "etc" / "config.ini"
if not config_path.exists():
    config_path = Path(ROOT_DIR) / "config.ini"
Config.load_config(str(config_path))

# 初始化数据库控制器
db_controller = DbController()

# 根据配置选择数据库类型
if Config.is_sqlite():
    # SQLite 模式
    sqlite_path = Path(ROOT_DIR) / Config.sqlite_path
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
