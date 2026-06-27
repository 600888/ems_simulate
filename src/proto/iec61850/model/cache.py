"""模型缓存 — LRU 线程安全缓存

用于缓存 IedModel 对象，支持多设备复用。
缓存命中时直接复用 IedModel，避免重复远程发现或 ICD 解析。

v2.0 新增: 整改计划第二阶段 — 模型缓存机制
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
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
    timestamp: float
    ttl_seconds: float = 1800.0  # 默认 30 分钟


class ModelCache:
    """线程安全的 LRU 模型缓存

    缓存策略:
        - key: 模型唯一标识 (ied_name + model_hash)
        - value: IedModel 不可变对象
        - 容量: 最近最多使用 (LRU), 最大 32 个模型
        - 过期: 默认 30 分钟无访问自动过期

    使用方式:
        cache = ModelCache.instance()
        cache.set("PCS001G:v1.0", model)
        cached = cache.get("PCS001G:v1.0")
    """

    _instance: ModelCache | None = None
    _lock = threading.Lock()

    MAX_SIZE = 32
    TTL_SECONDS = 1800.0  # 30 分钟

    def __init__(self):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._cache_lock = threading.Lock()

    @classmethod
    def instance(cls) -> ModelCache:
        """获取全局单例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get(self, key: str) -> IedModel | None:
        """获取缓存的模型

        Returns:
            缓存命中且未过期时返回 IedModel，否则返回 None
        """
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            # 检查是否过期
            if time.time() - entry.timestamp > entry.ttl_seconds:
                del self._cache[key]
                log.debug(f"模型缓存已过期: {key}")
                return None

            # LRU: 移动到末尾（最近使用）
            self._cache.move_to_end(key)
            return entry.model

    def set(
        self,
        key: str,
        model: IedModel,
        ttl_seconds: float | None = None,
    ) -> None:
        """写入缓存

        Args:
            key: 缓存键
            model: IedModel 对象
            ttl_seconds: 自定义过期时间（秒），默认使用 TTL_SECONDS
        """
        with self._cache_lock:
            if key in self._cache:
                self._cache.move_to_end(key)

            self._cache[key] = CacheEntry(
                model=model,
                timestamp=time.time(),
                ttl_seconds=ttl_seconds or self.TTL_SECONDS,
            )

            # LRU 淘汰: 超出最大容量时移除最久未使用的条目
            while len(self._cache) > self.MAX_SIZE:
                evicted_key, _ = self._cache.popitem(last=False)
                log.debug(f"模型缓存淘汰: {evicted_key}")

    def invalidate(self, key: str) -> None:
        """清除指定缓存"""
        with self._cache_lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        """清空所有缓存"""
        with self._cache_lock:
            self._cache.clear()
        log.info("模型缓存已全部清空")

    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        with self._cache_lock:
            now = time.time()
            active_entries = 0
            expired_entries = 0
            for entry in self._cache.values():
                if now - entry.timestamp <= entry.ttl_seconds:
                    active_entries += 1
                else:
                    expired_entries += 1
            return {
                "total_entries": len(self._cache),
                "active_entries": active_entries,
                "expired_entries": expired_entries,
                "max_size": self.MAX_SIZE,
                "keys": list(self._cache.keys()),
            }

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
