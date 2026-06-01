from pathlib import Path

from src.config.global_config import LOG_DIR
from src.config.log.logger import Log

log = Log(
    filename=str(Path(LOG_DIR) / "db.log"),
    cmdlevel="DEBUG",
    filelevel="INFO",
    limit=2048000,
    backup_count=1,
    colorful=True,
)
