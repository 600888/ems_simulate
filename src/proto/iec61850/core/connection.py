"""IEC 61850 MMS 连接生命周期管理

封装 IedConnection 的创建/连接/断开/重连，
提供连接状态监控和 LD 列表缓存能力。
"""

from ..defs.constants import HAS_IEC61850, FC_MX
from ..log import log


class Iec61850Connection:
    """连接管理器

    职责:
    - IedConnection 创建与销毁
    - 连接/断开/重连
    - 连接状态心跳检测
    - LD 列表缓存
    """

    def __init__(self, ip: str, port: int, model_name: str = "", ld_name: str = "GenericLD"):
        if not HAS_IEC61850:
            raise RuntimeError("pyiec61850 未安装，无法创建 IEC 61850 连接")

        self.ip = ip
        self.port = port
        self.model_name = model_name
        self.ld_name = ld_name

        self._connection = None
        self._is_connected = False
        self._discovered_lds: list[str] = []

    @property
    def connection(self):
        """底层 IedConnection 对象"""
        return self._connection

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect(self, auto_discover: bool = True, discover_callback=None) -> bool:
        """连接到 IEC 61850 服务器

        Args:
            auto_discover: 是否在连接成功后自动发现模型
            discover_callback: 自动发现回调 (client.discover_model)
        """
        from pyiec61850 import pyiec61850 as iec61850

        try:
            self._connection = iec61850.IedConnection_create()
            result = iec61850.IedConnection_connect(
                self._connection, self.ip, self.port
            )

            error = result
            if isinstance(result, (list, tuple)):
                error = result[1]

            if error == iec61850.IED_ERROR_OK:
                self._is_connected = True
                log.info(f"IEC 61850 连接已建立: {self.ip}:{self.port}")

                if not self.model_name:
                    self._infer_model_name()

                if auto_discover and discover_callback:
                    discover_callback()

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
        if self._connection:
            from pyiec61850 import pyiec61850 as iec61850
            try:
                iec61850.IedConnection_close(self._connection)
            except Exception:
                pass
            try:
                iec61850.IedConnection_destroy(self._connection)
            except Exception:
                pass
            self._connection = None
            self._is_connected = False
            log.info("IEC 61850 连接已断开")

    def try_reconnect(self, max_retries: int = 3, interval: float = 5.0,
                      discover_callback=None) -> bool:
        """自动重连 (指数退避)

        Args:
            max_retries: 最大重试次数
            interval: 初始重试间隔 (秒)
            discover_callback: 连接成功后的发现回调
        """
        import time

        for attempt in range(max_retries):
            wait = interval * (2 ** attempt)
            log.info(f"重连尝试 {attempt + 1}/{max_retries}, 等待 {wait:.1f}s...")
            time.sleep(wait)

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
        from ..defs.constants import FC_MX, FC_ST, FC_CO

        if not fc or not HAS_IEC61850:
            return FC_MX
        fc_map = {
            "MX": FC_MX,
            "ST": FC_ST,
            "CO": FC_CO,
        }
        return fc_map.get(fc, FC_MX)

    def build_dataset_ref(self, dataset_ref: str) -> str:
        """构建 MMS DataSet 引用，确保包含 model_name 前缀"""
        if not dataset_ref or '/' not in dataset_ref:
            return dataset_ref
        if not self.model_name:
            return self._resolve_dataset_ref_with_ld_prefix(dataset_ref)
        ld_part, rest = dataset_ref.split('/', 1)
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
        if '/' not in dataset_ref:
            return dataset_ref
        ld_part, rest = dataset_ref.split('/', 1)

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
                    prefix = full_ld[:-len(ld_part)]
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
