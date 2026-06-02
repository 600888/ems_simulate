"""SCL 文件管理器 — 上传/列表/删除/浏览

管理 data/61850icd/ 目录下的 ICD/SCD/CID 文件。
使用 Context Manager 确保临时文件清理。
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from ....log import log


@dataclass
class SclFileInfo:
    """SCL 文件信息"""
    filename: str
    file_path: str
    file_size: int  # bytes
    modified_time: str
    extension: str  # .icd / .scd / .cid

    def to_dict(self) -> dict[str, str | int]:
        return {
            "filename": self.filename,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "modified_time": self.modified_time,
            "extension": self.extension,
        }


class SclFileManager:
    """SCL 文件管理器

    管理本地 ICD/SCD/CID 文件的 CRUD 操作。
    默认目录: data/61850icd/
    """

    VALID_EXTENSIONS = (".icd", ".scd", ".cid", ".xml")

    def __init__(self, base_dir: str | None = None):
        if base_dir is None:
            # 默认: 项目根目录/data/61850icd/
            project_root = Path(__file__).resolve().parents[5]
            base_dir = str(project_root / "data" / "61850icd")
        self._base_dir = base_dir
        _ = os.makedirs(self._base_dir, exist_ok=True)

    @property
    def base_dir(self) -> str:
        return self._base_dir

    def list_files(self) -> list[SclFileInfo]:
        """列出所有 SCL 文件"""
        result = []
        if not os.path.exists(self._base_dir):
            return result

        for filename in sorted(os.listdir(self._base_dir)):
            if not filename.lower().endswith(self.VALID_EXTENSIONS):
                continue
            file_path = os.path.join(self._base_dir, filename)
            if not os.path.isfile(file_path):
                continue

            stat = os.stat(file_path)
            result.append(SclFileInfo(
                filename=filename,
                file_path=file_path,
                file_size=stat.st_size,
                modified_time=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                extension=os.path.splitext(filename)[1].lower(),
            ))
        return result

    def get_file_path(self, filename: str) -> str | None:
        """获取文件完整路径"""
        file_path = os.path.join(self._base_dir, filename)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return file_path
        return None

    def save_uploaded_file(self, filename: str, content: bytes) -> str:
        """保存上传的文件

        Args:
            filename: 原始文件名
            content: 文件内容

        Returns:
            保存后的文件路径
        """
        # 安全检查: 仅允许有效扩展名
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self.VALID_EXTENSIONS:
            raise ValueError(f"不支持的文件类型: {ext}，支持: {', '.join(self.VALID_EXTENSIONS)}")

        # 安全检查: 防止路径遍历
        safe_name = os.path.basename(filename)
        file_path = os.path.join(self._base_dir, safe_name)

        # 覆盖写入
        with open(file_path, "wb") as f:
            f.write(content)

        log.info(f"SCL 文件已保存: {file_path} ({len(content)} bytes)")
        return file_path

    def save_uploaded_stream(self, filename: str, stream: BinaryIO) -> str:
        """保存上传的文件流

        Args:
            filename: 原始文件名
            stream: 文件流

        Returns:
            保存后的文件路径
        """
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self.VALID_EXTENSIONS:
            raise ValueError(f"不支持的文件类型: {ext}，支持: {', '.join(self.VALID_EXTENSIONS)}")

        safe_name = os.path.basename(filename)
        file_path = os.path.join(self._base_dir, safe_name)

        with open(file_path, "wb") as f:
            shutil.copyfileobj(stream, f)

        log.info(f"SCL 文件已保存: {file_path}")
        return file_path

    def delete_file(self, filename: str) -> bool:
        """删除文件

        Returns:
            是否删除成功
        """
        file_path = os.path.join(self._base_dir, filename)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            os.remove(file_path)
            log.info(f"SCL 文件已删除: {file_path}")
            return True
        return False

    def file_exists(self, filename: str) -> bool:
        """检查文件是否存在"""
        return os.path.isfile(os.path.join(self._base_dir, filename))

    def read_file_content(self, filename: str) -> str | None:
        """读取文件内容 (文本)

        Returns:
            文件内容字符串，失败返回 None
        """
        file_path = os.path.join(self._base_dir, filename)
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            log.warning(f"读取 SCL 文件失败: {e}")
            return None
