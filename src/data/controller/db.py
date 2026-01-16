import os
from src.config.global_config import ROOT_DIR
from src.data.controller.db_controller import DbController
from sqlalchemy.orm import sessionmaker
from src.config.config import Config
from src.data.model.base import Base

db_controller = DbController()
Config.load_config(os.path.join(ROOT_DIR, "config.ini"))
db_controller.init_mysql_db(Config.host, Config.port, Config.username, Config.password)
engine = db_controller.db_config.get_engine()
local_session = sessionmaker(engine, expire_on_commit=False)
base = Base()
