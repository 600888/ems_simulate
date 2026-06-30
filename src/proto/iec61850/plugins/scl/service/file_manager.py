"""SCL 文件管理器 — 上传/列表/删除/浏览

管理 data/61850icd/ 目录下的 ICD/SCD/CID 文件。
使用 Context Manager 确保临时文件清理。

v2.0 变更:
  - 新增文件完整性校验 (SHA256)
  - 新增规范存储机制: data/61850icd/{ied_name}/{ied_name}_v{revision}.icd
  - 新增元数据文件 (*.meta)，跟踪设备/通道关联关系
  - 新增 compute_hash() / verify_integrity() 工具方法
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import os
import re
import shutil
from typing import BinaryIO

from src.config.storage import get_storage_path

from ....log import log

# ICD 文件名规范: {ied_name}_v{revision}.icd
_RE_ICD_FILENAME = re.compile(r"^(.+?)_v(.+)\.icd$")


@dataclass
class IcdMetaData:
    """ICD 文件元数据"""

    ied_name: str = ""
    version: str = ""
    revision: str = ""
    file_hash: str = ""
    upload_time: str = ""
    device_ids: list[int] = field(default_factory=list)
    channel_ids: list[int] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "ied_name": self.ied_name,
            "version": self.version,
            "revision": self.revision,
            "file_hash": self.file_hash,
            "upload_time": self.upload_time,
            "device_ids": self.device_ids,
            "channel_ids": self.channel_ids,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> IcdMetaData:
        return cls(
            ied_name=data.get("ied_name", ""),
            version=data.get("version", ""),
            revision=data.get("revision", ""),
            file_hash=data.get("file_hash", ""),
            upload_time=data.get("upload_time", ""),
            device_ids=data.get("device_ids", []),
            channel_ids=data.get("channel_ids", []),
            description=data.get("description", ""),
        )


@dataclass
class SclFileInfo:
    """SCL 文件信息"""

    filename: str
    file_path: str
    file_size: int  # bytes
    modified_time: str
    extension: str  # .icd / .scd / .cid
    file_hash: str = ""  # SHA256 摘要

    def to_dict(self) -> dict[str, str | int]:
        return {
            "filename": self.filename,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "modified_time": self.modified_time,
            "extension": self.extension,
            "file_hash": self.file_hash,
        }


class SclFileManager:
    """SCL 文件管理器

    管理本地 ICD/SCD/CID 文件的 CRUD 操作。
    默认目录: data/61850icd/

    目录结构:
        data/61850icd/
        ├── {ied_name}/
        │   ├── {ied_name}_v{revision}.icd    # 规范存储
        │   ├── {ied_name}_v{revision}.icd.sha256  # 完整性校验文件
        │   └── {ied_name}_v{revision}.icd.meta    # 元数据文件 (JSON)
        ├── {ied_name}_raw.icd                 # 非规范存储（向后兼容）
        └── temp/                              # 临时上传目录
    """

    VALID_EXTENSIONS = (".icd", ".scd", ".cid", ".xml")

    def __init__(self, base_dir: str | None = None):
        if base_dir is None:
            base_dir = get_storage_path("iec61850_model_cache_directory")
        self._base_dir = base_dir
        _ = os.makedirs(self._base_dir, exist_ok=True)
        # 确保 temp 子目录存在
        _ = os.makedirs(os.path.join(self._base_dir, "temp"), exist_ok=True)

    @property
    def base_dir(self) -> str:
        return self._base_dir

    # ===== 文件完整性校验 =====

    @staticmethod
    def compute_hash(content: bytes) -> str:
        """计算文件内容的 SHA256 摘要"""
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def compute_hash_from_file(file_path: str, chunk_size: int = 65536) -> str:
        """计算文件的 SHA256 摘要（大文件流式读取）"""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _get_hash_file_path(self, icd_path: str) -> str:
        """获取与 ICD 文件对应的 sha256 校验文件路径"""
        return icd_path + ".sha256"

    def _write_hash_file(self, icd_path: str, file_hash: str) -> None:
        """写入 sha256 校验文件"""
        hash_path = self._get_hash_file_path(icd_path)
        with open(hash_path, "w") as f:
            f.write(f"{file_hash}  {os.path.basename(icd_path)}\n")

    def verify_integrity(self, file_path: str) -> bool:
        """验证文件的 SHA256 完整性

        优先使用 .sha256 校验文件比对，不存在则直接计算返回 True。
        """
        hash_path = self._get_hash_file_path(file_path)
        if not os.path.exists(hash_path):
            # 无校验文件，直接计算
            return True
        try:
            with open(hash_path) as f:
                line = f.readline().strip()
            expected_hash = line.split()[0]
            actual_hash = self.compute_hash_from_file(file_path)
            return expected_hash == actual_hash
        except Exception as e:
            log.warning(f"完整性校验失败: {file_path}, error={e}")
            return False

    def ensure_integrity_file(self, file_path: str) -> str:
        """确保文件有对应的 sha256 校验文件，没有则创建

        Returns:
            SHA256 摘要
        """
        file_hash = self.compute_hash_from_file(file_path)
        hash_path = self._get_hash_file_path(file_path)
        if not os.path.exists(hash_path):
            self._write_hash_file(file_path, file_hash)
        return file_hash

    # ===== 元数据管理 =====

    def _get_meta_path(self, icd_path: str) -> str:
        """获取与 ICD 文件对应的元数据文件路径"""
        return icd_path + ".meta"

    def read_meta(self, icd_path: str) -> IcdMetaData | None:
        """读取 ICD 文件的元数据"""
        meta_path = self._get_meta_path(icd_path)
        if not os.path.exists(meta_path):
            return None
        try:
            with open(meta_path, encoding="utf-8") as f:
                data = json.load(f)
            return IcdMetaData.from_dict(data)
        except Exception as e:
            log.warning(f"读取元数据失败: {meta_path}, error={e}")
            return None

    def write_meta(self, icd_path: str, meta: IcdMetaData) -> None:
        """写入 ICD 文件元数据"""
        meta_path = self._get_meta_path(icd_path)
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.warning(f"写入元数据失败: {meta_path}, error={e}")

    def update_meta_device_assoc(self, icd_path: str, device_id: int, channel_id: int) -> None:
        """更新 ICD 文件的设备/通道关联关系

        将设备 ID 和通道 ID 追加到元数据的关联列表中。
        """
        meta = self.read_meta(icd_path) or IcdMetaData()
        if device_id not in meta.device_ids:
            meta.device_ids.append(device_id)
        if channel_id not in meta.channel_ids:
            meta.channel_ids.append(channel_id)
        self.write_meta(icd_path, meta)

    def remove_meta_device_assoc(self, icd_path: str, device_id: int, channel_id: int) -> None:
        """移除 ICD 文件的设备/通道关联关系"""
        meta = self.read_meta(icd_path)
        if not meta:
            return
        meta.device_ids = [d for d in meta.device_ids if d != device_id]
        meta.channel_ids = [c for c in meta.channel_ids if c != channel_id]
        self.write_meta(icd_path, meta)

    # ===== 规范存储 =====

    def _parse_icd_info(self, file_path: str) -> tuple[str, str, str]:
        """从 ICD 文件解析 IED 名称、版本、修订号

        优先读取元数据，其次从文件名推断，最后使用默认值。

        Returns:
            (ied_name, version, revision)
        """
        # 尝试从元数据读取
        meta = self.read_meta(file_path)
        if meta and meta.ied_name:
            return meta.ied_name, meta.version, meta.revision

        # 尝试从文件名解析: {ied_name}_v{revision}.icd
        basename = os.path.basename(file_path)
        m = _RE_ICD_FILENAME.match(basename)
        if m:
            return m.group(1), "", m.group(2)

        # 默认值
        name = os.path.splitext(basename)[0]
        return name, "", ""

    def get_ied_storage_dir(self, ied_name: str) -> str:
        """获取指定 IED 的规范存储目录"""
        return os.path.join(self._base_dir, ied_name)

    def get_standard_path(self, ied_name: str, revision: str = "") -> str:
        """获取 IED 的规范 ICD 文件路径

        格式: data/61850icd/{ied_name}/{ied_name}_v{revision}.icd
        """
        sub_dir = os.path.join(self._base_dir, ied_name)
        rev_suffix = f"_v{revision}" if revision else ""
        filename = f"{ied_name}{rev_suffix}.icd"
        return os.path.join(sub_dir, filename)

    def save_to_standard_location(
        self,
        source_path: str,
        ied_name: str,
        revision: str = "",
        *,
        device_id: int | None = None,
        channel_id: int | None = None,
    ) -> str:
        """将文件保存到规范位置

        Args:
            source_path: 源文件路径
            ied_name: IED 名称
            revision: ICD 修订版本号
            device_id: 关联的设备 ID（可选）
            channel_id: 关联的通道 ID（可选）

        Returns:
            规范存储后的文件路径
        """
        # 创建 IED 子目录
        dest_dir = self.get_ied_storage_dir(ied_name)
        os.makedirs(dest_dir, exist_ok=True)

        # 目标文件路径
        dest_path = self.get_standard_path(ied_name, revision)

        # 复制文件
        shutil.copy2(source_path, dest_path)

        # 计算并写入 hash 校验文件
        file_hash = self.ensure_integrity_file(dest_path)

        # 写入元数据
        meta = IcdMetaData(
            ied_name=ied_name,
            revision=revision,
            file_hash=file_hash,
            upload_time=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            device_ids=[device_id] if device_id is not None else [],
            channel_ids=[channel_id] if channel_id is not None else [],
        )
        self.write_meta(dest_path, meta)

        log.info(f"ICD 文件已保存到规范位置: {dest_path}")
        return dest_path

    # ===== 设备目录存储 (v2.1) =====

    def _get_device_dir(self) -> str:
        """获取设备 ICD 存储根目录"""
        device_dir = os.path.join(get_storage_path("data_directory"), "device")
        return device_dir

    def save_to_device_dir(
        self,
        source_path: str,
        device_name: str | None,
        *,
        original_filename: str | None = None,
        device_id: int | None = None,
        channel_id: int | None = None,
    ) -> str:
        """将 ICD 文件保存到 data/device/{device_name}/ 目录

        保存为 data/device/{device_name}/{original_filename}，
        同名文件直接覆盖。

        Args:
            source_path: 源文件路径
            device_name: 设备名称（用作目录名）
            original_filename: 原始文件名（用作保存的文件名，默认 {device_name}.icd）
            device_id: 关联的设备 ID（可选）
            channel_id: 关联的通道 ID（可选）

        Returns:
            保存后的文件路径
        """
        device_root = self._get_device_dir()
        if device_name is None:
            device_name = ""
        dest_dir = os.path.join(device_root, device_name)
        os.makedirs(dest_dir, exist_ok=True)

        base_name = original_filename or f"{device_name}.icd"
        dest_path = os.path.join(dest_dir, base_name)

        # 直接复制（覆盖已有文件）
        shutil.copy2(source_path, dest_path)

        # 计算 hash
        file_hash = self.ensure_integrity_file(dest_path)

        # 写入元数据
        meta = IcdMetaData(
            ied_name=device_name,
            file_hash=file_hash,
            upload_time=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            device_ids=[device_id] if device_id is not None else [],
            channel_ids=[channel_id] if channel_id is not None else [],
        )
        self.write_meta(dest_path, meta)

        log.info(f"ICD 文件已保存到设备目录: {dest_path}")
        return dest_path

    def find_standard_icd(self, ied_name: str) -> str | None:
        """查找指定 IED 的规范 ICD 文件

        遍历 {ied_name}/ 目录，返回最新版本的 ICD 文件路径。
        """
        sub_dir = self.get_ied_storage_dir(ied_name)
        if not os.path.isdir(sub_dir):
            return None

        icd_files = []
        for f in os.listdir(sub_dir):
            if f.lower().endswith(".icd"):
                fp = os.path.join(sub_dir, f)
                if os.path.isfile(fp):
                    icd_files.append((fp, os.path.getmtime(fp)))

        if not icd_files:
            return None

        # 按修改时间降序，返回最新
        icd_files.sort(key=lambda x: x[1], reverse=True)
        return icd_files[0][0]

    # ===== 文件列表 =====

    def _scan_directory(self, directory: str, depth: int = 0, max_depth: int = 2) -> list[SclFileInfo]:
        """递归扫描目录下的 SCL 文件"""
        result = []
        if depth > max_depth:
            return result
        if not os.path.exists(directory):
            return result

        for entry in sorted(os.listdir(directory)):
            full_path = os.path.join(directory, entry)
            if os.path.isdir(full_path):
                if entry != "temp":
                    result.extend(self._scan_directory(full_path, depth + 1, max_depth))
            elif entry.lower().endswith(self.VALID_EXTENSIONS):
                stat = os.stat(full_path)
                file_hash = ""
                try:
                    file_hash = self.compute_hash_from_file(full_path)
                except Exception:
                    pass
                result.append(
                    SclFileInfo(
                        filename=entry,
                        file_path=full_path,
                        file_size=stat.st_size,
                        modified_time=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        extension=os.path.splitext(entry)[1].lower(),
                        file_hash=file_hash,
                    )
                )
        return result

    def list_files(self) -> list[SclFileInfo]:
        """列出所有 SCL 文件（递归扫描所有子目录）"""
        return self._scan_directory(self._base_dir)

    def get_file_path(self, filename: str) -> str | None:
        """获取文件完整路径（递归查找）"""
        # 优先在根目录查找
        file_path = os.path.join(self._base_dir, filename)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return file_path
        # 递归子目录查找
        for root, _dirs, files in os.walk(self._base_dir):
            if filename in files:
                return os.path.join(root, filename)
        return None

    # ===== 文件上传/保存 =====

    def save_uploaded_file(self, filename: str, content: bytes) -> str:
        """保存上传的文件到临时目录

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

        # 保存到临时目录
        temp_dir = os.path.join(self._base_dir, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        safe_name = os.path.basename(filename)
        file_path = os.path.join(temp_dir, safe_name)

        with open(file_path, "wb") as f:
            f.write(content)

        log.info(f"SCL 文件已上传到临时目录: {file_path} ({len(content)} bytes)")
        return file_path

    def save_uploaded_stream(self, filename: str, stream: BinaryIO) -> str:
        """保存上传的文件流到临时目录"""
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self.VALID_EXTENSIONS:
            raise ValueError(f"不支持的文件类型: {ext}，支持: {', '.join(self.VALID_EXTENSIONS)}")

        temp_dir = os.path.join(self._base_dir, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        safe_name = os.path.basename(filename)
        file_path = os.path.join(temp_dir, safe_name)

        with open(file_path, "wb") as f:
            shutil.copyfileobj(stream, f)

        log.info(f"SCL 文件流已上传到临时目录: {file_path}")
        return file_path

    def delete_file(self, filename: str) -> bool:
        """删除文件

        Returns:
            是否删除成功
        """
        file_path = self.get_file_path(filename)
        if file_path and os.path.isfile(file_path):
            os.remove(file_path)
            # 也删除关联的 .sha256 和 .meta 文件
            for suffix in (".sha256", ".meta"):
                extra_path = file_path + suffix
                if os.path.exists(extra_path):
                    os.remove(extra_path)
            log.info(f"SCL 文件已删除: {file_path}")
            return True
        return False

    def file_exists(self, filename: str) -> bool:
        """检查文件是否存在"""
        return self.get_file_path(filename) is not None

    def read_file_content(self, filename: str) -> str | None:
        """读取文件内容 (文本)

        Returns:
            文件内容字符串，失败返回 None
        """
        file_path = self.get_file_path(filename)
        if not file_path:
            return None
        try:
            with open(file_path, encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            log.warning(f"读取 SCL 文件失败: {e}")
            return None

    def get_icd_by_device(self, device_id: int) -> list[dict]:
        """根据设备 ID 查找关联的 ICD 文件

        遍历所有 .meta 文件，筛选包含指定 device_id 的 ICD 文件。

        Returns:
            匹配的文件信息列表
        """
        result = []
        for root, _dirs, files in os.walk(self._base_dir):
            for f in files:
                if f.endswith(".icd.meta"):
                    meta_path = os.path.join(root, f)
                    try:
                        with open(meta_path, encoding="utf-8") as mf:
                            meta = json.load(mf)
                        if device_id in meta.get("device_ids", []):
                            icd_path = meta_path[:-5]  # 去掉 .meta
                            if os.path.exists(icd_path):
                                stat = os.stat(icd_path)
                                result.append(
                                    {
                                        "file_path": icd_path,
                                        "filename": os.path.basename(icd_path),
                                        "ied_name": meta.get("ied_name", ""),
                                        "file_hash": meta.get("file_hash", ""),
                                        "file_size": stat.st_size,
                                        "modified_time": datetime.fromtimestamp(stat.st_mtime).strftime(
                                            "%Y-%m-%d %H:%M:%S"
                                        ),
                                    }
                                )
                    except Exception:
                        continue
        return result
