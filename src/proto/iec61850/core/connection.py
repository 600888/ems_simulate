"""IEC 61850 MMS 连接生命周期管理

封装 IedConnection 的创建/连接/断开/重连，
提供连接状态监控和 LD 列表缓存能力。
"""

import contextlib
from dataclasses import dataclass
import os
import threading
import time

from ..defs.constants import FC_MX, HAS_IEC61850
from ..log import log


def _positive_timeout_from_env(name: str, default: int) -> int:
    """读取并校验环境变量中的正数超时配置；无效或缺失时采用默认值。"""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        log.warning(f"忽略无效超时配置 {name}={raw_value!r}，使用默认值 {default}ms")
        return default
    if value <= 0:
        log.warning(f"忽略非正超时配置 {name}={raw_value!r}，使用默认值 {default}ms")
        return default
    return value


@dataclass(frozen=True, slots=True)
class Iec61850Timeouts:
    """Timeout policy for one MMS association.

    Connect timeout only protects association establishment. Request timeout is
    equally important because discovery performs many synchronous directory and
    value requests; leaving it implicit can stall an entire discovery phase.
    """

    connect_ms: int = 3000
    request_ms: int = 3000

    @classmethod
    def from_env(cls) -> "Iec61850Timeouts":
        """从环境变量加载连接、请求和模型发现超时，未配置项沿用默认值。"""
        return cls(
            connect_ms=_positive_timeout_from_env("EMS_IEC61850_CONNECT_TIMEOUT_MS", 3000),
            request_ms=_positive_timeout_from_env("EMS_IEC61850_REQUEST_TIMEOUT_MS", 3000),
        )


class Iec61850Connection:
    """连接管理器

    职责:
    - IedConnection 创建与销毁
    - 连接/断开/重连
    - 连接状态心跳检测
    - LD 列表缓存
    """

    def __init__(
        self,
        ip: str,
        port: int,
        model_name: str = "",
        ld_name: str = "GenericLD",
        *,
        timeouts: Iec61850Timeouts | None = None,
    ):
        """保存 IED 地址与超时配置，并创建保护底层连接句柄的可重入锁。"""
        if not HAS_IEC61850:
            raise RuntimeError("pyiec61850 未安装，无法创建 IEC 61850 连接")

        self.ip = ip
        self.port = port
        self.model_name = model_name
        self.ld_name = ld_name
        self.timeouts = timeouts or Iec61850Timeouts.from_env()

        self._connection = None
        self._is_connected = False
        self._discovered_lds: list[str] = []
        self._lock = threading.RLock()
        self._discover_callback = None
        self._last_alive_check = 0.0
        self._alive_check_interval = 5.0

    @property
    def connection(self):
        """底层 IedConnection 对象"""
        return self._connection

    @property
    def is_connected(self) -> bool:
        """判断IED 连接管理器是否处于连接状态。"""
        return self._is_connected

    @contextlib.contextmanager
    def native_operation(self):
        """在连接锁保护下提供当前底层连接，避免操作期间被重连销毁。"""
        with self._lock:
            if not self._connection or not self._is_connected:
                yield None
                return
            yield self._connection

    def connect(self, auto_discover: bool = True, discover_callback=None) -> bool:
        """连接到 IEC 61850 服务器

        Args:
            auto_discover: 是否在连接成功后自动发现模型
            discover_callback: 自动发现回调 (client.discover_model)
        """
        from pyiec61850 import pyiec61850 as iec61850

        with self._lock:
            if discover_callback is not None:
                self._discover_callback = discover_callback

            try:
                self._connection = iec61850.IedConnection_create()
                # 连接和请求是两套独立超时。发现阶段的大量同步 MMS 请求
                # 必须显式受控，避免单个异常节点让整个任务长期停滞。
                iec61850.IedConnection_setConnectTimeout(self._connection, self.timeouts.connect_ms)
                iec61850.IedConnection_setRequestTimeout(self._connection, self.timeouts.request_ms)
                result = iec61850.IedConnection_connect(self._connection, self.ip, self.port)

                error = result
                if isinstance(result, (list, tuple)):
                    error = result[1]

                if error == iec61850.IED_ERROR_OK:
                    self._is_connected = True
                    self._last_alive_check = time.monotonic()
                    log.info(f"IEC 61850 连接已建立: {self.ip}:{self.port}")

                    # model_name is a local configuration hint, while DataSet
                    # references must use the exact MMS domains exposed by the
                    # current association.  Cache the remote LD directory even
                    # when model_name is configured; otherwise an offline model
                    # can be prefixed into an invalid reference such as
                    # ``ZCA-110LC001PCS06/LLN0$ds...``.
                    self._infer_model_name()

                    callback = discover_callback or self._discover_callback
                    if auto_discover and callback:
                        callback()

                    return True
                else:
                    log.error(f"IEC 61850 连接失败, 错误码: {error}")
                    self._is_connected = False
                    self._cleanup_connection()
                    return False
            except Exception as e:
                log.error(f"IEC 61850 连接异常: {e}")
                self._is_connected = False
                self._cleanup_connection()
                return False

    def disconnect(self):
        """断开连接"""
        with self._lock:
            if self._connection:
                from pyiec61850 import pyiec61850 as iec61850

                with contextlib.suppress(Exception):
                    iec61850.IedConnection_close(self._connection)
                with contextlib.suppress(Exception):
                    iec61850.IedConnection_destroy(self._connection)
                self._connection = None
                self._is_connected = False
                self._last_alive_check = 0.0
                log.info("IEC 61850 连接已断开")

    def check_alive(self, force: bool = False) -> bool:
        """探测底层 MMS Association 是否仍可用。

        `_is_connected` 只表示曾经连接成功，不能发现长时间运行后的半断开。
        这里用轻量的 LD 列表读取作为心跳，失败时标记连接失效。
        """
        if not self._connection or not self._is_connected:
            return False

        now = time.monotonic()
        if not force and now - self._last_alive_check < self._alive_check_interval:
            return True

        from pyiec61850 import pyiec61850 as iec61850

        with self._lock:
            if not self._connection or not self._is_connected:
                return False
            try:
                result = iec61850.IedConnection_getLogicalDeviceList(self._connection)
                if isinstance(result, (list, tuple)):
                    error = result[1] if len(result) > 1 else iec61850.IED_ERROR_OK
                else:
                    error = iec61850.IED_ERROR_OK if result is not None else -1

                if error == iec61850.IED_ERROR_OK:
                    self._last_alive_check = now
                    return True

                log.warning(f"IEC 61850 MMS 心跳失败，标记连接失效: error={error}")
            except Exception as e:
                log.warning(f"IEC 61850 MMS 心跳异常，标记连接失效: {e}")

            self._is_connected = False
            return False

    def ensure_connected(self) -> bool:
        """确保连接可用；必要时自动重连。"""
        if self.check_alive(force=False):
            return True
        return self.try_reconnect(max_retries=1, interval=0.2, discover_callback=self._discover_callback)

    def reconnect_if_unhealthy(self, reason: str = "") -> bool:
        """一次 MMS 操作失败后，强制探活；若不健康则重连。"""
        if self.check_alive(force=True):
            return False
        if reason:
            log.warning(f"IEC 61850 MMS 操作失败且心跳不可用，尝试重连: {reason}")
        return self.try_reconnect(max_retries=1, interval=0.2, discover_callback=self._discover_callback)

    def try_reconnect(self, max_retries: int = 3, interval: float = 5.0, discover_callback=None) -> bool:
        """自动重连 (指数退避)

        Args:
            max_retries: 最大重试次数
            interval: 初始重试间隔 (秒)
            discover_callback: 连接成功后的发现回调
        """
        import time

        for attempt in range(max_retries):
            wait = interval * (2**attempt)
            log.info(f"重连尝试 {attempt + 1}/{max_retries}, 等待 {wait:.1f}s...")
            time.sleep(wait)

            # 报告连接由 ReportsPlugin 在重连前完成禁用和回调排空；
            # 普通数据连接不能清理进程内其他 association 的报告回调。
            self.disconnect()
            if self.connect(auto_discover=True, discover_callback=discover_callback):
                log.info(f"重连成功: {self.ip}:{self.port}")
                return True

        log.error(f"重连失败，已达最大重试次数 {max_retries}")
        return False

    def _cleanup_connection(self):
        """清理连接资源"""
        if self._connection:
            try:
                from pyiec61850 import pyiec61850 as iec61850

                iec61850.IedConnection_destroy(self._connection)
            except Exception:
                pass
            self._connection = None

    def get_fc_value(self, fc: str):
        """将 FC 字符串转换为 pyiec61850 常量值"""
        if not fc or not HAS_IEC61850:
            return FC_MX
        from pyiec61850 import pyiec61850 as iec61850

        # pyiec61850 exposes every functional constraint with the same suffix
        # as the IEC name (SP/SE/SV/CF/SG/...); use that complete mapping rather
        # than silently treating unknown writable FCs as MX.
        return getattr(iec61850, f"IEC61850_FC_{str(fc).upper()}", FC_MX)

    def build_dataset_ref(self, dataset_ref: str) -> str:
        """构建 MMS DataSet 引用，确保包含 model_name 前缀"""
        if not dataset_ref or "/" not in dataset_ref:
            return dataset_ref
        if not self.model_name:
            return self._resolve_dataset_ref_with_ld_prefix(dataset_ref)
        ld_part, rest = dataset_ref.split("/", 1)
        # 在线发现返回的 LD 名称已经是远端 MMS domain，不能因为配置中的
        # model_name 不准确而再次添加前缀。
        if ld_part in self._discovered_lds:
            return dataset_ref
        if ld_part.startswith(self.model_name):
            return dataset_ref
        return f"{self.model_name}{ld_part}/{rest}"

    def _infer_model_name(self):
        """从远程 IED 的 LD 列表缓存 LD 名称"""
        if not self._connection or not self._is_connected:
            return
        try:
            lds = self.browse_logical_devices()
            if not lds:
                return
            self._discovered_lds = lds
            log.info(f"从远程 IED 发现 {len(lds)} 个逻辑设备: {lds[:3]}...")
        except Exception as e:
            log.debug(f"缓存 LD 列表失败: {e}")

    def _resolve_dataset_ref_with_ld_prefix(self, dataset_ref: str) -> str:
        """当 model_name 未知时，从已发现的 LD 列表中匹配完整 LD 名称"""
        if "/" not in dataset_ref:
            return dataset_ref
        ld_part, rest = dataset_ref.split("/", 1)

        if not self._discovered_lds:
            log.debug(f"LD 缓存为空，尝试实时获取, dataset_ref={dataset_ref}")
            try:
                self._infer_model_name()
            except Exception as e:
                log.debug(f"实时获取 LD 列表失败: {e}")

        if not self._discovered_lds:
            try:
                lds = self.browse_logical_devices()
                if lds:
                    self._discovered_lds = lds
            except Exception as e:
                log.debug(f"browse_logical_devices 失败: {e}")

        if self._discovered_lds:
            for full_ld in self._discovered_lds:
                if full_ld == ld_part:
                    return dataset_ref
                if full_ld.endswith(ld_part):
                    prefix = full_ld[: -len(ld_part)]
                    if prefix:
                        return f"{full_ld}/{rest}"
            log.warning(f"在 {len(self._discovered_lds)} 个 LD 中未匹配到 ld_part={ld_part}")
        else:
            log.warning(f"无法获取 LD 列表, 无法解析 ref={dataset_ref}")

        return dataset_ref

    def browse_logical_devices(self) -> list[str]:
        """浏览远程 IED 的逻辑设备列表

        需要由 Client 提供具体实现或由外部注入。
        此处提供基础实现。
        """
        if not self._connection or not self._is_connected:
            return []

        from pyiec61850 import pyiec61850 as iec61850

        from .linked_list import get_list_from_linked_list

        try:
            [lds, error] = iec61850.IedConnection_getLogicalDeviceList(self._connection)
            if error != iec61850.IED_ERROR_OK:
                return []
            return get_list_from_linked_list(lds)
        except Exception as e:
            log.debug(f"获取 LD 列表失败: {e}")
            return []
