"""IEC 61850 文件服务数据类型定义

定义文件浏览、传输、缓存相关的数据结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import enum


class FileType(enum.Enum):
    """文件/目录类型"""

    FILE = "file"
    DIRECTORY = "directory"


class TransferStatus(enum.Enum):
    """传输状态"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class FileEntry:
    """远程文件目录条目

    对应 libiec61850 的 FileDirectoryEntry:
    - fileName: 文件名
    - fileSize: 文件大小 (字节), 未知时为 -1
    - lastModified: 最后修改时间 (UTC 毫秒时间戳)
    """

    name: str  # 文件/目录名
    file_type: FileType = FileType.FILE  # 文件类型
    size: int = -1  # 文件大小 (字节), -1 表示未知
    last_modified: datetime | None = None  # 最后修改时间
    full_path: str = ""  # 完整路径 (用于下载/删除)

    @property
    def is_directory(self) -> bool:
        """判断FileEntry是否处于目录。"""
        return self.file_type == FileType.DIRECTORY

    def size_human(self) -> str:
        """人类可读的文件大小"""
        size = self.size
        if size < 0:
            return "未知"
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def to_dict(self) -> dict[str, object]:
        """转换为字典 (用于 API 返回)"""
        return {
            "name": self.name,
            "type": self.file_type.value,
            "size": self.size,
            "size_human": self.size_human(),
            "last_modified": self.last_modified.isoformat() if self.last_modified else None,
            "full_path": self.full_path,
        }


@dataclass
class TransferProgress:
    """文件传输进度"""

    filename: str  # 远程文件名
    status: TransferStatus = TransferStatus.PENDING
    bytes_transferred: int = 0  # 已传输字节数
    total_bytes: int = -1  # 总字节数, -1 表示未知
    error: str | None = None  # 错误信息

    @property
    def progress_percent(self) -> float:
        """进度百分比 (0.0 ~ 100.0)"""
        if self.total_bytes <= 0:
            return 0.0
        return min(100.0, self.bytes_transferred / self.total_bytes * 100)

    @property
    def is_complete(self) -> bool:
        """判断TransferProgress是否处于完成状态。"""
        return self.status in (TransferStatus.COMPLETED, TransferStatus.FAILED, TransferStatus.CANCELLED)

    def to_dict(self) -> dict[str, object]:
        """把TransferProgress转换为可序列化字典。"""
        return {
            "filename": self.filename,
            "status": self.status.value,
            "bytes_transferred": self.bytes_transferred,
            "total_bytes": self.total_bytes,
            "progress_percent": round(self.progress_percent, 1),
            "error": self.error,
        }


@dataclass
class FileMetadata:
    """本地缓存文件元数据"""

    remote_path: str  # 远程文件路径 (唯一键)
    local_path: str  # 本地缓存路径
    file_size: int  # 文件大小
    remote_modified: datetime | None = None  # 远程最后修改时间
    download_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    checksum: str | None = None  # 文件校验和 (MD5)

    def to_dict(self) -> dict[str, object]:
        """把FileMetadata转换为可序列化字典。"""
        return {
            "remote_path": self.remote_path,
            "local_path": self.local_path,
            "file_size": self.file_size,
            "remote_modified": self.remote_modified.isoformat() if self.remote_modified else None,
            "download_time": self.download_time.isoformat() if self.download_time else None,
            "checksum": self.checksum,
        }
