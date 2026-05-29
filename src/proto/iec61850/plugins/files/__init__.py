"""Files 插件 - 文件服务操作

骨架实现，Phase 3.10 中完成具体逻辑。
"""

from typing import Any, List, Dict

from ..base import Iec61850Plugin
from ...defs.constants import HAS_IEC61850
from ...log import log


class FilesPlugin:
    """Files 插件

    管理文件服务操作 (获取文件列表/下载文件)。
    """

    def __init__(self):
        self._connection = None
        self._initialized = False

    @property
    def name(self) -> str:
        return "files"

    @property
    def available(self) -> bool:
        return HAS_IEC61850

    def initialize(self, connection: Any, **kwargs) -> None:
        self._connection = connection
        self._initialized = True
        log.info("Files 插件已初始化 (骨架)")

    def shutdown(self) -> None:
        self._connection = None
        self._initialized = False

    def get_file_list(self, directory: str = "") -> List[Dict[str, Any]]:
        """获取远程 IED 的文件列表"""
        return []

    def get_file(self, filename: str) -> bytes:
        """从远程 IED 下载文件"""
        return b""
