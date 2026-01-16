import os.path

from src.config.global_config import ROOT_DIR, LOG_DIR
from src.config.log.logger import Log

log = Log(
    filename=os.path.join(LOG_DIR, "db.log"),
    cmdlevel="DEBUG",
    filelevel="INFO",
    limit=2048000,
    backup_count=1,
    colorful=True,
)
