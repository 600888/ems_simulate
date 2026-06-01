"""Files 插件 - IEC 61850 文件下载服务

提供远程 IED 的文件浏览、下载、上传、删除操作，
以及本地缓存管理能力。

模块结构:
- types.py      — 数据类型定义 (FileEntry, TransferProgress, FileMetadata)
- directory.py  — DirectoryBrowser 目录浏览与递归遍历
- transfer.py   — FileTransfer 文件下载/上传/删除操作
- cache.py      — CacheManager 本地缓存与版本管理
"""

from typing import Any, Callable, Dict, List, Optional

from ...core.connection import Iec61850Connection
from ...defs.constants import HAS_IEC61850
from ...log import log
from ..base import Iec61850Plugin
from .cache import CacheManager
from .directory import DirectoryBrowser
from .transfer import FileTransfer, ProgressCallback
from .types import FileEntry, FileMetadata, FileType, TransferProgress, TransferStatus


class FilesPlugin:
    """Files 插件 — IEC 61850 文件下载服务门面

    组合 DirectoryBrowser、FileTransfer、CacheManager 三个子模块，
    通过 Iec61850Plugin 协议接入插件系统。
    """

    def __init__(self):
        self._connection: Optional[Iec61850Connection] = None
        self._browser: Optional[DirectoryBrowser] = None
        self._transfer: Optional[FileTransfer] = None
        self._cache: Optional[CacheManager] = None
        self._initialized = False

    # ===== Iec61850Plugin 协议实现 =====

    @property
    def name(self) -> str:
        return "files"

    @property
    def available(self) -> bool:
        return HAS_IEC61850

    def initialize(self, connection: Any, **kwargs) -> None:
        if self._initialized:
            return
        self._connection = connection
        self._browser = DirectoryBrowser(connection)
        self._transfer = FileTransfer(connection)
        self._cache = CacheManager()
        self._initialized = True
        log.info("Files 插件已初始化 (文件下载服务)")

    def shutdown(self) -> None:
        # 程序关闭时清理下载缓存目录
        if self._cache:
            try:
                self._cache.clear()
            except Exception as e:
                log.debug(f"清理文件缓存失败: {e}")
        self._browser = None
        self._transfer = None
        self._cache = None
        self._connection = None
        self._initialized = False

    # ===== 目录浏览 (委托 DirectoryBrowser) =====

    def get_file_list(self, directory: str = "") -> list[dict[str, Any]]:
        """获取远程 IED 的文件/目录列表

        Args:
            directory: 目录路径，空字符串表示根目录

        Returns:
            [{"name": "...", "type": "file|directory", "size": 1234,
              "size_human": "1.2 KB", "last_modified": "2026-05-31T12:00:00+00:00",
              "full_path": "/logs/..."}]
        """
        if not self._browser:
            return []
        entries = self._browser.list_directory(directory)
        return [e.to_dict() for e in entries]

    def list_directory(self, directory: str = "") -> list[dict[str, Any]]:
        """获取远程 IED 的文件/目录列表 (get_file_list 的别名)"""
        return self.get_file_list(directory)

    def list_directory_recursive(
        self,
        directory: str = "",
        max_depth: int = 5,
    ) -> list[dict[str, Any]]:
        """递归获取完整目录树

        Args:
            directory: 起始目录
            max_depth: 最大递归深度

        Returns:
            所有层级的文件/目录扁平列表
        """
        if not self._browser:
            return []
        entries = self._browser.list_directory_recursive(directory, max_depth)
        return [e.to_dict() for e in entries]

    # ===== 文件传输 (委托 FileTransfer) =====

    def get_file(
        self,
        filename: str,
        local_path: str = "",
        progress_callback: Optional[ProgressCallback] = None,
        overwrite: bool = False,
    ) -> bytes:
        """从远程 IED 下载文件

        Args:
            filename: 远程文件绝对路径 (如 "/logs/fault1.comtrade")
            local_path: 本地保存路径，为空时下载到内存并返回字节数据
            progress_callback: 进度回调
            overwrite: 是否覆盖已存在的本地文件

        Returns:
            若 local_path 为空，返回文件字节数据；否则返回空 bytes
        """
        if not self._transfer:
            return b""

        if local_path:
            progress = self._transfer.download_file(filename, local_path, progress_callback, overwrite)
            if progress.status == TransferStatus.COMPLETED and self._cache:
                # 下载成功，加入缓存
                self._cache.put(filename, local_path)
            return b""
        else:
            data, progress = self._transfer.download_file_to_bytes(filename, progress_callback)
            if progress.status == TransferStatus.COMPLETED and self._cache:
                # 下载到内存成功，也加入缓存
                self._cache.put_bytes(filename, data)
            return data

    def download_file(
        self,
        filename: str,
        local_path: str = "",
        progress_callback: Optional[ProgressCallback] = None,
        overwrite: bool = False,
    ) -> TransferProgress:
        """下载文件并返回传输进度信息

        Args:
            filename: 远程文件绝对路径
            local_path: 本地保存路径，为空时下载到内存
            progress_callback: 进度回调
            overwrite: 是否覆盖已存在的本地文件

        Returns:
            TransferProgress 传输进度对象
        """
        if not self._transfer:
            return TransferProgress(filename, status=TransferStatus.FAILED, error="插件未初始化")

        if local_path:
            progress = self._transfer.download_file(filename, local_path, progress_callback, overwrite)
        else:
            _, progress = self._transfer.download_file_to_bytes(filename, progress_callback)

        # 缓存处理
        if progress.status == TransferStatus.COMPLETED and self._cache and local_path:
            self._cache.put(filename, local_path)
            # download_file_to_bytes 的缓存在 get_file 中处理

        return progress

    def upload_file(
        self,
        local_path: str,
        remote_filename: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> bool:
        """上传文件到远程 IED

        Args:
            local_path: 本地文件路径
            remote_filename: 远程目标文件名
            progress_callback: 进度回调

        Returns:
            是否上传成功
        """
        if not self._transfer:
            return False
        progress = self._transfer.upload_file(local_path, remote_filename, progress_callback)
        return progress.status == TransferStatus.COMPLETED

    def delete_file(self, remote_filename: str) -> bool:
        """删除远程 IED 上的文件

        Args:
            remote_filename: 远程文件绝对路径

        Returns:
            是否删除成功
        """
        if not self._transfer:
            return False
        result = self._transfer.delete_file(remote_filename)
        # 删除成功后清理本地缓存
        if result and self._cache:
            self._cache.remove(remote_filename)
        return result

    # ===== 缓存管理 (委托 CacheManager) =====

    def get_cached_file(self, remote_path: str) -> Optional[str]:
        """获取缓存文件路径

        Args:
            remote_path: 远程文件路径

        Returns:
            本地缓存路径 (str)，未缓存时返回 None
        """
        if not self._cache:
            return None
        return self._cache.get_cached_path(remote_path)

    def is_cache_valid(
        self,
        remote_path: str,
        remote_modified: Optional[Any] = None,
    ) -> bool:
        """检查缓存是否有效

        Args:
            remote_path: 远程文件路径
            remote_modified: 远程文件修改时间 (datetime)

        Returns:
            缓存是否有效
        """
        if not self._cache:
            return False
        return self._cache.is_cache_valid(remote_path, remote_modified)

    def list_cached_files(self) -> list[dict[str, Any]]:
        """列出所有本地缓存文件"""
        if not self._cache:
            return []
        return [m.to_dict() for m in self._cache.list_cached()]

    def clear_cache(self) -> int:
        """清空本地缓存

        Returns:
            清理的文件数量
        """
        if not self._cache:
            return 0
        return self._cache.clear()
