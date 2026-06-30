"""本地文件缓存管理器

管理从远程 IED 下载的文件在本地磁盘的缓存，提供:
- 缓存文件存储与元数据管理
- 缓存命中检测 (路径 + 修改时间)
- 缓存空间管理 (LRU 淘汰 + 容量限制)
- 缓存清理
"""

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil

from src.config.storage import get_storage_path

from ...log import log
from .types import FileMetadata


class CacheManager:
    """本地文件缓存管理器"""

    METADATA_FILE = ".cache_index.json"
    DEFAULT_MAX_SIZE_MB = 500

    def __init__(self, cache_dir: str = "", max_size_mb: int = DEFAULT_MAX_SIZE_MB):
        """
        Args:
            cache_dir: 缓存目录，为空时使用默认路径
            max_size_mb: 最大缓存大小 (MB)
        """
        self._cache_dir = Path(cache_dir) if cache_dir else self._default_cache_dir()
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._index: dict[str, FileMetadata] = {}
        self._ensure_cache_dir()
        self._load_index()

    @staticmethod
    def _default_cache_dir() -> Path:
        """默认缓存目录"""
        return Path(get_storage_path("iec61850_file_cache_directory"))

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    @property
    def total_size(self) -> int:
        """当前缓存总大小 (字节)"""
        return sum(m.file_size for m in self._index.values())

    # ===== 公共 API =====

    def get_cached_path(self, remote_path: str) -> str | None:
        """查询文件是否已缓存

        Args:
            remote_path: 远程文件路径

        Returns:
            本地缓存路径 (str)，未缓存时返回 None
        """
        meta = self._index.get(self._normalize_key(remote_path))
        if meta and os.path.isfile(meta.local_path):
            return meta.local_path
        # 缓存索引中有记录但文件不存在，清理无效记录
        if meta:
            self._index.pop(self._normalize_key(remote_path), None)
            self._save_index()
        return None

    def is_cache_valid(
        self,
        remote_path: str,
        remote_modified: datetime | None,
    ) -> bool:
        """检查缓存是否有效

        若远程修改时间较新，则缓存失效。
        """
        meta = self._index.get(self._normalize_key(remote_path))
        if not meta:
            return False

        # 本地文件不存在则无效
        if not os.path.isfile(meta.local_path):
            return False

        # 无远程修改时间信息，假设有效
        if remote_modified is None or meta.remote_modified is None:
            return True

        # 远程修改时间 > 缓存记录的远程修改时间 → 失效
        return remote_modified <= meta.remote_modified

    def put(
        self,
        remote_path: str,
        local_source: str,
        remote_modified: datetime | None = None,
    ) -> str:
        """将文件加入缓存

        Args:
            remote_path: 远程文件路径 (作为缓存键)
            local_source: 本地源文件路径
            remote_modified: 远程文件修改时间

        Returns:
            缓存文件路径
        """
        if not os.path.isfile(local_source):
            log.warning(f"源文件不存在，无法缓存: {local_source}")
            return local_source

        cache_path = self._remote_path_to_local(remote_path)
        cache_path_parent = cache_path.parent

        # 确保目标目录存在
        cache_path_parent.mkdir(parents=True, exist_ok=True)

        # 复制文件到缓存
        try:
            shutil.copy2(local_source, str(cache_path))
        except Exception as e:
            log.error(f"复制文件到缓存失败: {e}")
            return local_source

        # 计算校验和
        checksum = self._compute_checksum(local_source)

        # 更新索引
        meta = FileMetadata(
            remote_path=remote_path,
            local_path=str(cache_path),
            file_size=os.path.getsize(local_source),
            remote_modified=remote_modified,
            download_time=datetime.now(UTC),
            checksum=checksum,
        )
        self._index[self._normalize_key(remote_path)] = meta
        self._save_index()

        log.debug(f"文件已缓存: {remote_path} → {cache_path}")
        return str(cache_path)

    def put_bytes(
        self,
        remote_path: str,
        data: bytes,
        remote_modified: datetime | None = None,
    ) -> str:
        """将字节数据直接写入缓存

        Args:
            remote_path: 远程文件路径 (作为缓存键)
            data: 文件字节数据
            remote_modified: 远程文件修改时间

        Returns:
            缓存文件路径
        """
        # 空数据不缓存
        if not data:
            log.debug(f"跳过空数据缓存: {remote_path}")
            return ""

        cache_path = self._remote_path_to_local(remote_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(cache_path, "wb") as f:
                f.write(data)
        except Exception as e:
            log.error(f"写入缓存文件失败: {e}")
            return ""

        checksum = hashlib.md5(data).hexdigest()

        meta = FileMetadata(
            remote_path=remote_path,
            local_path=str(cache_path),
            file_size=len(data),
            remote_modified=remote_modified,
            download_time=datetime.now(UTC),
            checksum=checksum,
        )
        self._index[self._normalize_key(remote_path)] = meta
        self._save_index()

        log.debug(f"字节数据已缓存: {remote_path} → {cache_path} ({len(data)} bytes)")
        return str(cache_path)

    def remove(self, remote_path: str) -> bool:
        """从缓存中移除文件"""
        key = self._normalize_key(remote_path)
        meta = self._index.pop(key, None)
        if not meta:
            return False

        # 删除本地文件
        try:
            if os.path.isfile(meta.local_path):
                os.remove(meta.local_path)
        except Exception as e:
            log.debug(f"删除缓存文件失败: {e}")

        self._save_index()
        return True

    def list_cached(self) -> list[FileMetadata]:
        """列出所有缓存文件"""
        # 过滤已不存在的文件
        valid = []
        invalid_keys = []
        for key, meta in self._index.items():
            if os.path.isfile(meta.local_path):
                valid.append(meta)
            else:
                invalid_keys.append(key)

        if invalid_keys:
            for key in invalid_keys:
                self._index.pop(key, None)
            self._save_index()

        return valid

    def clear(self) -> int:
        """清空所有缓存，并删除缓存目录

        Returns:
            清理的文件数量
        """
        count = len(self._index)
        try:
            if self._cache_dir.exists():
                shutil.rmtree(self._cache_dir, ignore_errors=True)
        except Exception as e:
            log.error(f"清空缓存目录失败: {e}")

        self._index.clear()
        log.info(f"缓存已清空，共清理 {count} 个文件")
        return count

    def enforce_size_limit(self) -> int:
        """执行 LRU 缓存淘汰，确保总大小不超过限制

        按下载时间排序，优先淘汰最久未使用的缓存。

        Returns:
            淘汰的文件数量
        """
        if self.total_size <= self._max_size_bytes:
            return 0

        # 按下载时间升序排序 (最早的优先淘汰)
        sorted_items = sorted(
            self._index.items(),
            key=lambda x: x[1].download_time or datetime.min.replace(tzinfo=UTC),
        )

        evicted = 0
        current_size = self.total_size

        for key, meta in sorted_items:
            if current_size <= self._max_size_bytes:
                break

            try:
                if os.path.isfile(meta.local_path):
                    os.remove(meta.local_path)
            except Exception:
                pass

            current_size -= meta.file_size
            self._index.pop(key, None)
            evicted += 1

        if evicted > 0:
            self._save_index()
            log.info(f"LRU 缓存淘汰完成，淘汰 {evicted} 个文件")

        return evicted

    # ===== 内部方法 =====

    def _ensure_cache_dir(self) -> None:
        """确保缓存目录存在"""
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> None:
        """从磁盘加载缓存索引"""
        index_path = self._cache_dir / self.METADATA_FILE
        if not index_path.is_file():
            return

        try:
            with open(index_path, encoding="utf-8") as f:
                data = json.load(f)

            for key, item in data.items():
                self._index[key] = FileMetadata(
                    remote_path=item.get("remote_path", ""),
                    local_path=item.get("local_path", ""),
                    file_size=item.get("file_size", 0),
                    remote_modified=self._parse_datetime(item.get("remote_modified")),
                    download_time=self._parse_datetime(item.get("download_time")) or datetime.now(UTC),
                    checksum=item.get("checksum"),
                )
            log.debug(f"加载缓存索引: {len(self._index)} 条记录")

        except Exception as e:
            log.warning(f"加载缓存索引失败: {e}")
            self._index = {}

    def _save_index(self) -> None:
        """将缓存索引保存到磁盘"""
        index_path = self._cache_dir / self.METADATA_FILE
        try:
            data = {}
            for key, meta in self._index.items():
                data[key] = {
                    "remote_path": meta.remote_path,
                    "local_path": meta.local_path,
                    "file_size": meta.file_size,
                    "remote_modified": meta.remote_modified.isoformat() if meta.remote_modified else None,
                    "download_time": meta.download_time.isoformat() if meta.download_time else None,
                    "checksum": meta.checksum,
                }

            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            log.error(f"保存缓存索引失败: {e}")

    def _remote_path_to_local(self, remote_path: str) -> Path:
        """将远程路径映射为本地缓存路径

        例: /logs/fault1.comtrade → {cache_dir}/logs/fault1.comtrade
        """
        # 去除开头的 /
        relative = remote_path.lstrip("/")
        if not relative:
            relative = "_root"
        return self._cache_dir / relative

    @staticmethod
    def _normalize_key(remote_path: str) -> str:
        """规范化缓存键"""
        return remote_path.strip().lower()

    @staticmethod
    def _compute_checksum(file_path: str) -> str:
        """计算文件 MD5 校验和"""
        h = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    h.update(chunk)
        except Exception:
            return ""
        return h.hexdigest()

    @staticmethod
    def _parse_datetime(value) -> datetime | None:
        """解析 ISO 格式日期时间字符串"""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None
