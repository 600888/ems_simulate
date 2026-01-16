import os.path

from src.config.global_config import LOG_DIR
from src.config.log.logger import Log

log = Log(
    filename=os.path.join(LOG_DIR, "iec104.log"),
    cmdlevel="DEBUG",
    filelevel="INFO",
    limit=2048000,
    backup_count=1,
    colorful=True,
)
