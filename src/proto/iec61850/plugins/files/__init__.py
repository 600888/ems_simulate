"""Files 插件 - IEC 61850 文件下载服务

提供远程 IED 的文件浏览、下载、上传、删除操作，
以及本地缓存管理能力。

模块结构:
- types.py      — 数据类型定义 (FileEntry, TransferProgress, FileMetadata)
- directory.py  — DirectoryBrowser 目录浏览与递归遍历
- transfer.py   — FileTransfer 文件下载/上传/删除操作
- cache.py      — CacheManager 本地缓存与版本管理

Phase 8 增强: 添加 search_files / get_file_info / list_directory_paginated 等功能。
"""

from collections.abc import Callable
import fnmatch
from typing import Any, Optional

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

    Phase 8 增强:
    - search_files: 按文件名模式搜索
    - get_file_info: 获取单个文件详情
    - list_directory_paginated: 分页浏览目录
    - get_directory_summary: 获取目录统计摘要
    """

    def __init__(self):
        """保存插件宿主引用；协议能力在 initialize 阶段装配，在 shutdown 阶段统一释放。"""
        self._connection: Iec61850Connection | None = None
        self._browser: DirectoryBrowser | None = None
        self._transfer: FileTransfer | None = None
        self._cache: CacheManager | None = None
        self._initialized = False

    # ===== Iec61850Plugin 协议实现 =====

    @property
    def name(self) -> str:
        """返回FilesPlugin当前的名称。"""
        return "files"

    @property
    def available(self) -> bool:
        """返回FilesPlugin当前的可用状态。"""
        return HAS_IEC61850

    def initialize(self, connection: Any, **kwargs) -> None:
        """装配依赖并开放插件能力。"""
        if self._initialized:
            return
        self._connection = connection
        self._browser = DirectoryBrowser(connection)
        self._transfer = FileTransfer(connection)
        self._cache = CacheManager()
        self._initialized = True
        log.info("Files 插件已初始化 (文件下载服务)")

    def shutdown(self) -> None:
        """程序关闭时清理下载缓存目录"""
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

    # ===== 目录浏览 (委托 DirectoryBrowser) — 增强版 =====

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

    def list_directory_paginated(
        self,
        directory: str = "",
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """分页获取远程 IED 的文件/目录列表

        Args:
            directory: 目录路径
            offset: 起始偏移 (从 0 开始)
            limit: 最大返回条目数

        Returns:
            {
                "total": int,           # 目录下总条目数
                "offset": int,           # 当前偏移
                "limit": int,            # 当前限制
                "files": [...],          # 文件列表 (同 get_file_list 格式)
                "directories": [...],    # 子目录列表 (同 get_file_list 格式)
                "has_more": bool,        # 是否还有更多
            }
        """
        all_entries = self.get_file_list(directory)
        total = len(all_entries)

        # 区分文件和目录
        files = [e for e in all_entries if e.get("type") == "file"]
        directories = [e for e in all_entries if e.get("type") == "directory"]

        # 分页
        sliced = all_entries[offset : offset + limit]
        has_more = (offset + limit) < total

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "files": files,
            "directories": directories,
            "entries": sliced,
            "has_more": has_more,
        }

    def get_file_info(self, full_path: str) -> dict[str, Any] | None:
        """获取单个文件的详细信息

        Args:
            full_path: 文件/目录的完整路径

        Returns:
            FileEntry 的 dict 表示，或 None (文件不存在/查询失败)
        """
        if not self._browser:
            return None

        # 从父目录中查找
        parent_dir = self._extract_parent_dir(full_path)
        filename = self._extract_filename(full_path)
        entries = self._browser.list_directory(parent_dir)

        for entry in entries:
            if entry.name == filename or entry.full_path == full_path:
                return entry.to_dict()

        # 尝试递归搜索
        all_entries = self._browser.list_directory_recursive(parent_dir, max_depth=3)
        for entry in all_entries:
            if entry.full_path == full_path:
                return entry.to_dict()

        return None

    def search_files(
        self,
        pattern: str,
        directory: str = "",
        max_depth: int = 5,
        max_results: int = 200,
    ) -> list[dict[str, Any]]:
        """按文件名模式搜索远程 IED 上的文件

        支持 fnmatch 模式 (如 "*.comtrade", "fault*", "*.cfg")。

        Args:
            pattern: 文件名匹配模式 (支持 * 和 ? 通配符)
            directory: 起始搜索目录
            max_depth: 最大递归深度
            max_results: 最大返回结果数 (限制搜索范围)

        Returns:
            匹配的文件条目列表 (同 get_file_list 格式)
        """
        if not self._browser:
            return []

        all_entries = self._browser.list_directory_recursive(directory, max_depth=max_depth)

        result = []
        for entry in all_entries:
            if len(result) >= max_results:
                break
            if entry.file_type == FileType.FILE:
                if fnmatch.fnmatch(entry.name, pattern):
                    result.append(entry.to_dict())

        log.info(
            f"文件搜索完成: pattern={pattern!r}, directory={directory!r}, 匹配={len(result)}/{len(all_entries)} 条"
        )
        return result

    def get_directory_summary(self, directory: str = "") -> dict[str, Any]:
        """获取目录统计摘要

        Args:
            directory: 目录路径

        Returns:
            {
                "directory": str,
                "file_count": int,
                "dir_count": int,
                "total_size": int,
                "total_size_human": str,
                "file_types": {".ext": count, ...},
            }
        """
        entries = []
        if self._browser:
            entries = self._browser.list_directory(directory)

        file_count = 0
        dir_count = 0
        total_size = 0
        file_types: dict[str, int] = {}

        for entry in entries:
            if entry.is_directory:
                dir_count += 1
            else:
                file_count += 1
                if entry.size > 0:
                    total_size += entry.size
                # 统计文件类型
                ext = self._get_extension(entry.name)
                if ext:
                    file_types[ext] = file_types.get(ext, 0) + 1

        return {
            "directory": directory or "/",
            "file_count": file_count,
            "dir_count": dir_count,
            "total_size": total_size,
            "total_size_human": self._human_size(total_size),
            "file_types": file_types,
        }

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
        progress_callback: ProgressCallback | None = None,
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
        progress_callback: ProgressCallback | None = None,
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
        progress_callback: ProgressCallback | None = None,
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

    def get_cached_file(self, remote_path: str) -> str | None:
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
        remote_modified: Any | None = None,
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

    # ===== 内部辅助方法 =====

    @staticmethod
    def _extract_parent_dir(full_path: str) -> str:
        """从完整路径中提取父目录路径"""
        if not full_path or full_path == "/":
            return ""
        normalized = full_path.rstrip("/")
        last_sep = normalized.rfind("/")
        if last_sep <= 0:
            return ""
        return normalized[:last_sep]

    @staticmethod
    def _extract_filename(full_path: str) -> str:
        """从完整路径中提取文件名"""
        if not full_path:
            return ""
        return full_path.rstrip("/").split("/")[-1]

    @staticmethod
    def _get_extension(name: str) -> str:
        """获取文件扩展名"""
        if not name or "." not in name:
            return ""
        return "." + name.rsplit(".", 1)[-1].lower()

    @staticmethod
    def _human_size(size: int) -> str:
        """人类可读的文件大小"""
        if size < 0:
            return "未知"
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
