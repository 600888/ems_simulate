"""模型缓存 — LRU 线程安全缓存 + 文件持久化

用于缓存 IedModel 对象，支持多设备复用。
缓存命中时直接复用 IedModel，避免重复远程发现或 ICD 解析。

v2.0 新增: 整改计划第二阶段 — 模型缓存机制
v3.0 新增: 文件持久化，应用重启后可从磁盘恢复缓存
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import threading
import time
from typing import TYPE_CHECKING

from ..log import log

if TYPE_CHECKING:
    from .ied_model import IedModel


@dataclass
class CacheEntry:
    """缓存条目"""

    model: IedModel


# 文件缓存默认目录（当无法从 StorageSettings 获取时的回退）
_DEFAULT_CACHE_DIR = None


def _get_default_cache_dir() -> Path:
    global _DEFAULT_CACHE_DIR
    if _DEFAULT_CACHE_DIR is None:
        try:
            from src.config.storage import get_storage_path

            cache_dir = Path(get_storage_path("iec61850_model_cache_directory")) / "model_cache"
        except Exception:
            # 回退到当前项目目录
            cache_dir = Path("data") / "61850icd" / "model_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        _DEFAULT_CACHE_DIR = cache_dir
    return _DEFAULT_CACHE_DIR


def _sanitize_filename(key: str) -> str:
    """将缓存键转换为安全的文件名"""
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", key)


class ModelCache:
    """线程安全的 LRU 模型缓存（内存 + 文件持久化）

    缓存策略:
        - key: 模型唯一标识 (ip:port)
        - value: IedModel 不可变对象
        - 容量: 最近最多使用 (LRU), 最大 32 个模型
        - 有效期: 不自动过期，已发现的模型持续保存在本地，直到显式清除或刷新
        - 持久化: 每次 set() 同时保存到 JSON 文件，
                  get() 内存未命中时自动尝试从文件恢复
        - 淘汰: 内存淘汰不会删除文件缓存

    使用方式:
        cache = ModelCache.instance()
        cache.set("192.168.1.100:102", model)
        cached = cache.get("192.168.1.100:102")
    """

    _instance: ModelCache | None = None
    _lock = threading.Lock()

    MAX_SIZE = 32

    def __init__(self):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._cache_dir: Path | None = None  # 按需初始化

    @classmethod
    def instance(cls) -> ModelCache:
        """获取全局单例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ===== 缓存目录 =====

    @property
    def cache_dir(self) -> Path:
        if self._cache_dir is None:
            self._cache_dir = _get_default_cache_dir()
        return self._cache_dir

    def set_cache_dir(self, path: str | Path) -> None:
        """指定缓存目录（覆盖默认路径）"""
        p = Path(path).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        with self._cache_lock:
            self._cache_dir = p

    def _file_path(self, key: str) -> Path:
        """获取缓存键对应的磁盘文件路径"""
        fname = f"{_sanitize_filename(key)}_model.json"
        return self.cache_dir / fname

    # ===== 内存缓存操作 =====

    def has(self, key: str) -> bool:
        """检查本地缓存是否存在（不消耗缓存条目）

        同时检查内存和文件缓存。

        Args:
            key: 缓存键

        Returns:
            缓存存在时返回 True
        """
        with self._cache_lock:
            if key in self._cache:
                return True

        # 内存未命中，检查文件缓存
        file_path = self._file_path(key)
        if file_path.is_file():
            try:
                json.loads(file_path.read_text(encoding="utf-8"))
                return True
            except Exception:
                pass

        return False

    def get(self, key: str) -> IedModel | None:
        """获取缓存的模型

        内存未命中时自动尝试从磁盘文件恢复。

        Returns:
            缓存命中时返回 IedModel，否则返回 None
        """
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is not None:
                self._cache.move_to_end(key)
                return entry.model

        # 内存未命中，尝试从文件恢复
        model = self._load_from_file(key)
        if model is not None:
            log.info(f"从文件恢复模型缓存: {key}")
            # 重新写入内存缓存
            self.set(key, model)
            return model

        return None

    def set(self, key: str, model: IedModel) -> None:
        """写入缓存（内存 + 文件）

        Args:
            key: 缓存键
            model: IedModel 对象
        """
        with self._cache_lock:
            if key in self._cache:
                self._cache.move_to_end(key)

            self._cache[key] = CacheEntry(model=model)

            # LRU 淘汰: 超出最大容量时移除最久未使用的条目
            while len(self._cache) > self.MAX_SIZE:
                evicted_key, _ = self._cache.popitem(last=False)
                log.debug(f"模型缓存淘汰: {evicted_key}")

        # 同步写入文件（在锁外执行以避免阻塞其他缓存操作）
        self._save_to_file(key, model)

    def invalidate(self, key: str) -> None:
        """清除指定缓存（内存 + 文件）"""
        with self._cache_lock:
            self._cache.pop(key, None)
        self._delete_file(key)

    def clear(self) -> None:
        """清空所有缓存（内存 + 文件）"""
        with self._cache_lock:
            self._cache.clear()
        self._clear_all_files()
        log.info("模型缓存已全部清空（内存 + 文件）")

    # ===== 文件持久化 =====

    def _save_to_file(self, key: str, model: IedModel) -> None:
        """将模型序列化到文件"""
        file_path = self._file_path(key)
        try:
            data = model.to_dict()
            data["_cache_key"] = key
            data["_cached_at"] = time.time()
            file_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = file_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(file_path)
            log.debug(f"模型缓存已保存到文件: {file_path}")
        except Exception as e:
            log.warning(f"保存模型缓存文件失败: {file_path} ({e})")

    def _load_from_file(self, key: str) -> IedModel | None:
        """从文件反序列化恢复模型"""
        from .ied_model import IedModel as IedModelCls

        file_path = self._file_path(key)
        if not file_path.is_file():
            return None
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            model = IedModelCls.from_dict(data)
            log.debug(f"从文件恢复模型缓存成功: {file_path}")
            return model
        except Exception as e:
            log.warning(f"从文件恢复模型缓存失败: {file_path} ({e})")
            # 损坏的文件直接删除
            try:
                file_path.unlink(missing_ok=True)
            except Exception:
                pass
            return None

    def _delete_file(self, key: str) -> None:
        """删除缓存文件"""
        file_path = self._file_path(key)
        try:
            if file_path.is_file():
                file_path.unlink(missing_ok=True)
                log.debug(f"删除模型缓存文件: {file_path}")
        except Exception as e:
            log.warning(f"删除模型缓存文件失败: {file_path} ({e})")

    def _clear_all_files(self) -> None:
        """清空缓存目录下所有模型缓存文件"""
        try:
            if self._cache_dir.is_dir():
                count = 0
                for f in self._cache_dir.iterdir():
                    if f.suffix == ".json" and f.name.endswith("_model.json"):
                        try:
                            f.unlink()
                            count += 1
                        except Exception:
                            pass
                if count:
                    log.debug(f"已清理 {count} 个模型缓存文件")
        except Exception as e:
            log.warning(f"清理模型缓存文件目录失败: {e}")

    def get_cache_file_path(self, key: str) -> str:
        """获取缓存键对应的文件路径（仅用于展示）"""
        return str(self._file_path(key))

    # ===== 统计信息 =====

    def get_stats(self) -> dict:
        """获取缓存统计信息（内存 + 文件）"""
        stats = {}
        with self._cache_lock:
            stats = {
                "total_entries": len(self._cache),
                "active_entries": len(self._cache),
                "expired_entries": 0,
                "max_size": self.MAX_SIZE,
                "keys": list(self._cache.keys()),
            }

        # 文件缓存统计
        try:
            file_count = 0
            if self._cache_dir.is_dir():
                for f in self._cache_dir.iterdir():
                    if f.suffix == ".json" and f.name.endswith("_model.json"):
                        file_count += 1
            stats["file_cache_count"] = file_count
            stats["cache_dir"] = str(self._cache_dir)
        except Exception:
            stats["file_cache_count"] = 0
            stats["cache_dir"] = str(self._cache_dir)

        return stats

    # ===== 工具方法 =====

    @staticmethod
    def compute_key(ied_name: str, content_hash: str = "") -> str:
        """生成缓存键

        Args:
            ied_name: IED 名称
            content_hash: 文件内容 SHA256 摘要

        Returns:
            缓存键: "{ied_name}:{content_hash[:16]}"
        """
        suffix = content_hash[:16] if content_hash else "default"
        return f"{ied_name}:{suffix}"

    @staticmethod
    def compute_hash(content: bytes) -> str:
        """计算内容 SHA256 摘要"""
        return hashlib.sha256(content).hexdigest()
