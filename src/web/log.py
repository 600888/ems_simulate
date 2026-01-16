import os.path

from src.config.global_config import LOG_DIR
from src.config.log.logger import Log

log = None


def get_logger():
    global log
    if log is None:
        log = Log(
            filename=os.path.join(LOG_DIR, "flask.log"),
            cmdlevel="DEBUG",
            filelevel="DEBUG",
            limit=2048000,
            backup_count=1,
            colorful=True,
        )
    return log
