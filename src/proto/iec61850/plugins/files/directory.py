"""远程 IED 文件目录浏览器

封装 pyiec61850 的 getFileDirectory 系列函数，提供:
- 单层目录浏览
- 递归目录遍历 (处理 moreFollows 分页)
- 目录条目解析 (FileDirectoryEntry → FileEntry)
"""

import contextlib
from datetime import datetime, timezone
from typing import Callable, List, Optional

from ...core.connection import Iec61850Connection
from ...defs.constants import HAS_IEC61850
from ...log import log
from .types import FileEntry, FileType


class DirectoryBrowser:
    """远程 IED 文件目录浏览器"""

    def __init__(self, connection: Iec61850Connection):
        self._conn = connection

    # ===== 公共 API =====

    def list_directory(self, directory: str = "") -> list[FileEntry]:
        """获取指定目录下的文件和子目录列表

        Args:
            directory: 目录路径，空字符串或 "/" 表示根目录

        Returns:
            FileEntry 列表，包含文件和子目录
        """
        if not HAS_IEC61850:
            log.warning("pyiec61850 未安装，无法浏览文件目录")
            return []

        if not self._conn or not self._conn.is_connected:
            log.warning("连接不可用，无法浏览文件目录")
            return []

        try:
            raw_entries = self._collect_all_entries(directory)
            return raw_entries
        except Exception as e:
            log.error(f"浏览文件目录失败 (directory={directory!r}): {e}")
            return []

    def list_directory_recursive(
        self,
        directory: str = "",
        max_depth: int = 5,
        on_entry: Optional[Callable[[FileEntry], None]] = None,
    ) -> list[FileEntry]:
        """递归获取完整文件目录树

        Args:
            directory: 起始目录
            max_depth: 最大递归深度 (防止无限递归)
            on_entry: 每发现一个条目时的回调 (用于前端渐进显示)

        Returns:
            所有层级的 FileEntry 扁平列表
        """
        all_entries: list[FileEntry] = []
        self._recursive_walk(directory, max_depth, 0, all_entries, on_entry)
        return all_entries

    # ===== 内部实现 =====

    def _recursive_walk(
        self,
        directory: str,
        max_depth: int,
        current_depth: int,
        result: list[FileEntry],
        on_entry: Optional[Callable[[FileEntry], None]] = None,
    ) -> None:
        """递归遍历目录"""
        if current_depth >= max_depth:
            log.debug(f"达到最大递归深度 {max_depth}，停止遍历 (directory={directory!r})")
            return

        entries = self.list_directory(directory)
        for entry in entries:
            result.append(entry)
            if on_entry:
                with contextlib.suppress(Exception):
                    on_entry(entry)

            if entry.is_directory:
                subdir = entry.full_path
                self._recursive_walk(subdir, max_depth, current_depth + 1, result, on_entry)

    def _collect_all_entries(self, directory: str) -> list:
        """获取目录条目列表，迭代时即解析为 FileEntry

        条目内存由 file_list (LinkedList) 持有，必须在 LinkedList_destroy 之前
        完成解析，且不可再单独 destroy 每个条目，否则造成 use-after-free / double-free
        导致 C 层崩溃使进程终止。

        Returns:
            FileEntry 列表
        """
        from pyiec61850 import pyiec61850 as iec61850

        conn = self._conn.connection
        all_entries = []

        # 规范化目录参数: "" 表示根目录，映射为 "/" (libiec61850 不接受 None 或 "")
        dir_name = directory if directory and directory != "/" else "/"

        # 使用 getFileDirectory 获取目录列表
        try:
            result = iec61850.IedConnection_getFileDirectory(conn, dir_name)

            # 返回值格式: [fileList, error]
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                file_list, error_code = result[0], result[1]
            else:
                file_list = result
                error_code = iec61850.IED_ERROR_OK

            if error_code != iec61850.IED_ERROR_OK:
                log.warning(f"获取文件目录失败 (directory={directory!r}), 错误码: {error_code}")
                return []

            if not file_list:
                return []

            # 迭代并即时解析 (条目内存由 file_list 持有，解析后随 list 一起释放)
            entry = iec61850.LinkedList_getNext(file_list)
            while entry:
                data = iec61850.LinkedList_getData(entry)
                if data is not None:
                    fd_entry = iec61850.toFileDirectoryEntry(data)
                    all_entries.append(self._parse_entry(fd_entry, directory))
                entry = iec61850.LinkedList_getNext(entry)

            # 释放 LinkedList (一并释放其持有的所有条目，勿再单独 destroy 条目)
            iec61850.LinkedList_destroy(file_list)

        except Exception as e:
            log.error(f"IedConnection_getFileDirectory 调用异常: {e}")
            return []

        return all_entries

    def _parse_entry(self, entry, parent_directory: str) -> FileEntry:
        """将 pyiec61850 FileDirectoryEntry 转换为 FileEntry"""
        from pyiec61850 import pyiec61850 as iec61850

        try:
            filename = iec61850.FileDirectoryEntry_getFileName(entry)
            file_size = iec61850.FileDirectoryEntry_getFileSize(entry)
            last_modified_ms = iec61850.FileDirectoryEntry_getLastModified(entry)
        except Exception as e:
            log.warning(f"解析 FileDirectoryEntry 失败: {e}")
            return FileEntry(name="unknown", full_path="unknown")

        # 构建完整路径
        is_dir = self._is_directory_name(filename)
        full_path = self._build_full_path(parent_directory, filename)

        # 转换时间戳
        last_modified = None
        if last_modified_ms and last_modified_ms > 0:
            with contextlib.suppress(OSError, ValueError):
                last_modified = datetime.fromtimestamp(last_modified_ms / 1000.0, tz=timezone.utc)

        file_entry = FileEntry(
            name=filename.rstrip("/") if filename else "unknown",
            file_type=FileType.DIRECTORY if is_dir else FileType.FILE,
            size=file_size if file_size >= 0 else -1,
            last_modified=last_modified,
            full_path=full_path,
        )

        # 注意: 条目内存由 file_list (LinkedList) 持有，会随 LinkedList_destroy 一并释放，
        # 此处不可单独 destroy，否则造成 double-free 使 C 层崩溃。
        return file_entry

    @staticmethod
    def _is_directory_name(filename: str) -> bool:
        """判断文件名是否为目录

        IEC 61850 标准中 GetFileDirectory 响应无显式类型标识，
        常见判据:
        1. 文件名以 "/" 结尾 (libiec61850 惯例)
        2. 文件大小为 0 (辅助判断)
        """
        if not filename:
            return False
        return filename.endswith("/")

    @staticmethod
    def _build_full_path(parent_directory: str, filename: str) -> str:
        """构建完整文件路径

        Args:
            parent_directory: 父目录路径 (如 "/logs" 或 "")
            filename: 文件/目录名 (如 "fault1.comtrade" 或 "subdir/")

        Returns:
            完整路径 (如 "/logs/fault1.comtrade" 或 "/logs/subdir/")
        """
        # 规范化
        parent = parent_directory.strip("/") if parent_directory else ""

        # 清理文件名中的尾部 "/" 用于拼接
        clean_name = filename.rstrip("/") if filename else ""

        if not clean_name:
            return f"/{parent}" if parent else "/"

        if parent:
            return f"/{parent}/{clean_name}"
        else:
            return f"/{clean_name}"
