"""
IEC 61850 协议处理器
支持 IEC 61850 MMS 服务端和客户端
"""

import asyncio
from collections.abc import Sequence
import os
import time
from typing import Any

from src.device.protocol.base_handler import ClientHandler, ServerHandler
from src.enums.point_data import Yc, Yk, Yt, Yx
from src.enums.points.base_point import BasePoint


def _discovery_timeout_seconds() -> int:
    """返回模型发现允许使用的总超时时间，并保证结果不低于连接请求超时。"""
    raw_value = os.getenv("EMS_IEC61850_DISCOVERY_TIMEOUT_SECONDS", "600")
    try:
        value = int(raw_value)
    except ValueError:
        return 600
    return value if value > 0 else 600


class IEC61850ServerHandler(ServerHandler):
    """IEC 61850 服务端处理器"""

    def __init__(self, log=None):
        """绑定服务端通道与设备对象，准备模型加载、点值更新和生命周期管理状态。"""
        super().__init__()
        self._server = None
        self._log = log
        self._discovered_goose_items: list[dict[str, Any]] = []
        self._discovered_datasets: list[dict[str, Any]] = []
        self._mms_capture = None
        self._tls_bridge = None

    def initialize(self, config: dict[str, Any]) -> None:
        """初始化 IEC 61850 服务器

        Args:
            config: 配置字典，包含:
                - ip: 监听 IP（默认 0.0.0.0）
                - port: 监听端口（默认 102）
                - model_name: IED 模型名称
                - ied_name: IED 名称
                - ld_name: 逻辑设备名称
                - icd_path: ICD 文件路径（可选，v2.0 新增）
        """
        from src.proto.iec61850.iec61850_server import IEC61850Server

        self._config = config
        ip = config.get("ip", "0.0.0.0")
        port = config.get("port", 102)
        model_name = config.get("model_name")
        ied_name = config.get("ied_name")
        ld_name = config.get("ld_name", "GenericLD")
        self._icd_path: str | None = config.get("icd_path")
        runtime = config.get("runtime", {})
        security = config.get("security", {})

        from src.proto.iec61850.tls import TlsServerBridge, allocate_loopback_port, create_server_context

        tls_context = create_server_context(security)
        server_ip = ip
        server_port = port
        if tls_context is not None:
            server_ip = "127.0.0.1"
            server_port = allocate_loopback_port()
            self._tls_bridge = TlsServerBridge(ip, port, server_port, tls_context)

        # model_name 由 Device._build_protocol_config() 从通道配置传入，
        # 对应 ICD 文件的 IED 名称 (如 "PCS001G")，传给 ied_name 参数
        effective_ied = ied_name or model_name or "EMS"

        self._server = IEC61850Server(
            ip=server_ip,
            port=server_port,
            model_name=effective_ied,
            ied_name=effective_ied,
            ld_name=ld_name,
            max_connections=runtime.get("max_connections", 5),
            authentication_enabled=runtime.get("authentication_enabled", False),
            authentication_password=runtime.get("authentication_password", ""),
            file_service_directory=runtime.get("file_service_directory") or None,
        )
        from src.device.core.message.mms_capture import MmsMessageCapture

        if runtime.get("mms_capture_enabled", False):
            self._mms_capture = MmsMessageCapture(port=server_port, client=False, logger=self._log)
        else:
            self._mms_capture = None

    @property
    def model_loaded(self) -> bool:
        """模型是否已加载"""
        if not self._server:
            return False
        return self._server.model_loaded

    async def start(self) -> bool:
        """启动 IEC 61850 服务器

        v3.0+: 必须先加载 ICD 模型后才能启动，不再支持默认 GenericLD 模型。
        请先通过 load_model(icd_path) 加载 ICD 模型，再调用 start()。
        """
        try:
            if not self._server:
                return False

            if not self._server.model_loaded:
                if self._log:
                    self._log.error("启动 IEC 61850 服务器失败: 未加载 ICD 模型，请先通过 ICD 文件加载模型")
                return False

            # 模型已加载，启动 MMS 服务
            if self._mms_capture:
                self._mms_capture.start()
            await asyncio.to_thread(self._server.start_device)
            self._is_running = self._server.is_running
            if self._is_running and self._tls_bridge:
                self._tls_bridge.start()
            return self._is_running
        except Exception as e:
            if self._tls_bridge:
                self._tls_bridge.stop()
            if self._server and self._server.is_running:
                await asyncio.to_thread(self._server.stop)
            if self._mms_capture:
                self._mms_capture.stop()
            self._is_running = False
            if self._log:
                self._log.error(f"启动 IEC 61850 服务器失败: {e}")
            return False

    def load_model(self, icd_path: str, scl_result: Any = None) -> bool:
        """加载 ICD 模型（不启动 MMS 服务）

        用户手动在界面点击"加载模型"后调用。
        加载完 ICD 模型后再通过 start() 启动 MMS 服务。

        Args:
            icd_path: ICD 文件路径
            scl_result: 可选，预先解析的 SclImportResult，提供时跳过内部解析

        Returns:
            是否加载成功
        """
        if not self._server:
            return False
        self._icd_path = icd_path
        success = self._server.load_model(icd_path, scl_result=scl_result)
        if success:
            self._discovered_goose_items.clear()
            self._discovered_goose_items.extend(self._server.get_discovered_goose_items())
            self._discovered_datasets.clear()
            self._discovered_datasets.extend(self._server.browse_datasets())
        return success

    def get_icd_points(self) -> dict[str, list]:
        """获取最近一次 ICD 导入的测点列表

        透传自 IEC61850Server.get_icd_points()

        Returns:
            {"yc_points": [...], "yx_points": [...], "yk_points": [...], "yt_points": [...]}
        """
        if not self._server:
            return {"yc_points": [], "yx_points": [], "yk_points": [], "yt_points": []}
        return self._server.get_icd_points()

    def clear_cache(self) -> None:
        """清除服务端侧的缓存"""
        self._discovered_goose_items.clear()
        self._discovered_datasets.clear()
        if self._server:
            self._server.reset_model()

    async def stop(self) -> bool:
        """停止 IEC 61850 服务器"""
        try:
            if self._tls_bridge:
                self._tls_bridge.stop()
            if self._server:
                await asyncio.to_thread(self._server.stop)
                if self._mms_capture:
                    self._mms_capture.stop()
                self._is_running = False
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"停止 IEC 61850 服务器失败: {e}")
            return False

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值"""
        if self._server:
            fc = getattr(point, "fc", "") or ""
            return self._server.get_point_value(address=point.address, fc=fc)
        return 0

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值"""
        if self._server:
            fc = getattr(point, "fc", "") or ""
            self._server.set_point_value(
                address=point.address,
                value=value,
                fc=fc,
            )
            return True
        return False

    def write_values_batch(self, values: Sequence[tuple[BasePoint, Any]]) -> bool:
        """批量写入一轮模拟值，并让服务端合并报告通知。"""
        if not self._server:
            return False
        updates = [(point.address, value, getattr(point, "fc", "") or "") for point, value in values]
        return self._server.set_point_values(updates)

    async def read_value_async(self, point: BasePoint) -> Any:
        """异步读取测点值"""
        return self.read_value(point)

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        """异步写入测点值"""
        return self.write_value(point, value)

    def add_points(self, points: list[BasePoint]) -> None:
        """添加测点到 IEC 61850 服务器"""
        if not self._server:
            return

        for point in points:
            fc = getattr(point, "fc", "") or ""
            self._server.add_point(
                address=point.address,
                frame_type=point.frame_type,
                fc=fc,
            )

    def get_discovered_datasets(self) -> list[dict[str, Any]]:
        """获取服务端上已注册的 DataSet 列表"""
        if self._server:
            return self._server.browse_datasets()
        return []

    def read_dataset_values(self, dataset_ref: str) -> dict[str, Any]:
        """读取 DataSet 中所有成员的值（服务端模式从当前点值获取）

        Args:
            dataset_ref: DataSet 引用路径

        Returns:
            {fcda_ref: value} 字典
        """
        if not self._server:
            return {}
        # 服务端模式：直接从 DataSet 目录获取成员，再逐个读取
        datasets = self.get_discovered_datasets()
        for ds in datasets:
            if ds.get("ref") == dataset_ref:
                members = ds.get("members", [])
                break
        else:
            members = []

        values = {}
        for member in members:
            ref = member.get("ref", "")
            if not ref:
                continue
            # 使用地址格式读取值
            fc = member.get("fc", "MX")
            try:
                val = self._server.get_point_value(address=ref, fc=fc)
                if val is not None:
                    values[ref] = val
            except Exception:
                pass
        return values

    def get_value_by_address(self, func_code: int, slave_id: int, address: int) -> Any:
        """根据地址获取值"""
        if self._server:
            return self._server.get_point_value(address=address, fc="MX")
        return 0

    def set_value_by_address(self, func_code: int, slave_id: int, address: int, value: Any) -> None:
        """根据地址设置值"""
        if self._server:
            self._server.set_point_value(address=address, value=value, fc="MX")

    @property
    def server(self):
        """获取底层服务器对象"""
        return self._server

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取捕获的报文列表"""
        return self._mms_capture.get_messages(limit) if self._mms_capture else []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._mms_capture:
            self._mms_capture.clear()

    def get_avg_time(self) -> dict:
        """获取平均收发时间"""
        return self._mms_capture.get_avg_time() if self._mms_capture else {}


class IEC61850ClientHandler(ClientHandler):
    """IEC 61850 客户端处理器"""

    # 连接阶段定义
    PHASE_IDLE = "idle"  # 未开始
    PHASE_CONNECTING = "connecting"  # 正在连接服务器
    PHASE_DISCOVERING = "discovering"  # 正在发现模型
    PHASE_READING = "reading"  # 正在按 DataSet 批量读取
    PHASE_DONE = "done"  # 连接完成
    PHASE_FAILED = "failed"  # 连接失败

    def __init__(self, log=None):
        """绑定客户端通道与设备对象，准备连接、模型发现、报告和读写协调状态。"""
        super().__init__()
        self._client = None
        self._log = log
        self._discovery_timeout = _discovery_timeout_seconds()
        self._on_points_discovered = None  # 测点发现回调
        self._connecting = False  # 是否正在连接中（防止重复启动）
        self._connect_phase = self.PHASE_IDLE  # 当前连接阶段
        self._connect_progress = 0  # 连接进度 0-100
        self._progress_active = False  # 连接、发现或批读任务是否仍在执行
        self._progress_operation = "idle"  # idle/connect/discover/read
        self._progress_message = ""
        self._progress_error_code = ""
        self._progress_started_at: float | None = None
        self._progress_elapsed_seconds = 0
        self._progress_operation_id = 0
        self._discovered_goose_items: list[dict[str, Any]] = []  # 发现的 GOOSE 控制块
        self._discovered_datasets: list[dict[str, Any]] = []  # 发现的 DataSet 列表
        self._discovered_rcbs: list[dict[str, Any]] = []  # 发现的报告控制块 (连接时缓存)
        self._model_loaded: bool = False  # 模型是否已加载
        self._mms_capture = None
        self._tls_bridge = None

    @property
    def model_loaded(self) -> bool:
        """模型是否已加载"""
        return self._model_loaded

    @model_loaded.setter
    def model_loaded(self, value: bool) -> None:
        """更新IEC61850ClientHandler的模型加载状态，使后续操作使用新值。"""
        self._model_loaded = value

    def set_on_points_discovered(self, callback):
        """设置测点发现回调

        Args:
            callback: 回调函数，签名为 callback(discovered_points: List[Dict])
                      每个 dict 包含 {"address": str, "frame_type": int, "ref": str, "code": str}
                      address 为完整 IEC 61850 引用路径，如 "MEAS/M0GGIO1.AnIn1.mag.f"
                      code 为短编码，简单地址模式为原始地址(如 "1")，ICD 模式为 "LN.DO"(如 "M0GGIO1.AnIn1")
        """
        self._on_points_discovered = callback

    def initialize(self, config: dict[str, Any]) -> None:
        """初始化 IEC 61850 客户端

        Args:
            config: 配置字典，包含:
                - ip: 服务器 IP
                - port: 服务器端口（默认 102）
                - model_name: IED 模型名称
                - ld_name: 逻辑设备名称
        """
        from src.proto.iec61850.iec61850_client import IEC61850Client

        self._config = config
        ip = config.get("ip", "127.0.0.1")
        port = config.get("port", 102)
        model_name = config.get("model_name", "EMS")
        ld_name = config.get("ld_name", "GenericLD")
        runtime = config.get("runtime", {})
        security = config.get("security", {})
        self._discovery_timeout = runtime.get("model_discovery_timeout_ms", 600000) / 1000

        from src.proto.iec61850.tls import TlsClientBridge, create_client_context

        tls_context = create_client_context(security)
        client_ip = ip
        client_port = port
        if tls_context is not None:
            self._tls_bridge = TlsClientBridge(ip, port, tls_context)
            client_ip = "127.0.0.1"
            client_port = self._tls_bridge.local_port

        from src.proto.iec61850.core.connection import Iec61850AssociationParameters, Iec61850Timeouts

        timeouts = Iec61850Timeouts(
            connect_ms=runtime.get("connect_timeout_ms", 3000),
            request_ms=runtime.get("command_timeout_ms", 3000),
        )
        association_parameters = Iec61850AssociationParameters(
            remote_ap_title=runtime.get("remote_ap_title", "1,1,1,999,1"),
            remote_ae_qualifier=runtime.get("remote_ae_qualifier", 12),
            remote_p_selector=runtime.get("remote_p_selector", "00 00 00 01"),
            remote_s_selector=runtime.get("remote_s_selector", "00 01"),
            remote_t_selector=runtime.get("remote_t_selector", "00 01"),
            local_ap_title=runtime.get("local_ap_title", "1,1,1,999,1"),
            local_ae_qualifier=runtime.get("local_ae_qualifier", 12),
            local_p_selector=runtime.get("local_p_selector", "00 00 00 01"),
            local_s_selector=runtime.get("local_s_selector", "00 01"),
            local_t_selector=runtime.get("local_t_selector", "00 01"),
            authentication_enabled=runtime.get("authentication_enabled", False),
            authentication_password=runtime.get("authentication_password", ""),
        )

        self._client = IEC61850Client(
            ip=client_ip,
            port=client_port,
            model_name=model_name,
            ld_name=ld_name,
            timeouts=timeouts,
            association_parameters=association_parameters,
            # The server-side ACSE authenticator is invoked from a native
            # server thread and needs the Python interpreter briefly. Polling
            # the asynchronous connect state prevents a same-process client
            # from holding the GIL for the whole association handshake.
            nonblocking_connect=True,
        )
        from src.device.core.message.mms_capture import MmsMessageCapture

        if runtime.get("mms_capture_enabled", False):
            self._mms_capture = MmsMessageCapture(
                port=client_port,
                remote_ip=client_ip,
                client=True,
                logger=self._log,
            )
        else:
            self._mms_capture = None

    async def start(self) -> bool:
        """启动客户端（仅连接 MMS 服务器，不自动发现模型）

        v2.0: 模型加载与连接分离。
        连接后需要手动调用 load_model_from_icd() 或 remote_discover_model() 加载模型。

        IEC 61850 的 IedConnection_connect 是 C 扩展同步阻塞调用，会持有 GIL，
        导致 run_in_executor 也无法避免阻塞事件循环。
        因此使用 daemon 线程在后台执行连接，start() 立即返回，
        前端通过轮询 get_device_info 获取最终连接状态。
        """
        if not self._client:
            return False

        # 防止重复启动连接
        if self._connecting:
            return True  # 已在连接中，视为成功受理
        if self._progress_active:
            return False

        # 重置连接进度（重新连接时清除上一次的状态）
        self._connect_phase = self.PHASE_IDLE
        self._connect_progress = 0

        self._connecting = True
        if not self._start_tls_bridge():
            self._connecting = False
            return False
        self._ensure_mms_capture_started()
        self._begin_progress("connect", self.PHASE_CONNECTING, 10, "正在连接 MMS 服务器")
        import threading

        thread = threading.Thread(target=self._connect_background, daemon=True)
        thread.start()
        return True  # 立即返回，表示连接任务已受理

    def _start_tls_bridge(self) -> bool:
        """确保原生 MMS 客户端连接前，本地 TLS 桥已经开始监听。"""
        if not self._tls_bridge:
            return True
        try:
            self._tls_bridge.start()
            return True
        except OSError as exc:
            if self._log:
                self._log.error(f"启动 IEC61850 TLS 客户端桥接器失败: {exc}")
            return False

    def _ensure_mms_capture_started(self) -> bool:
        """Ensure every MMS connection entry point has an active packet capture."""
        if not self._mms_capture:
            return True
        if self._mms_capture.is_running:
            return True
        started = self._mms_capture.start()
        if not started and self._log:
            self._log.warning("MMS报文捕获启动失败，连接将继续但查看报文可能为空")
        return started

    def _stop_tls_bridge_after_connect_failure(self) -> str:
        """停止失败的 TLS 桥并返回可用于界面和日志的握手错误。"""
        if not self._tls_bridge:
            return ""
        tls_error = self._tls_bridge.last_error or ""
        self._tls_bridge.stop()
        if tls_error and self._log:
            self._log.error(f"IEC61850 TLS 握手失败: {tls_error}")
        return tls_error

    def load_model_from_icd(self, icd_path: str, scl_result: Any = None) -> bool:
        """从 ICD 文件加载模型（不依赖 MMS 连接）

        Args:
            icd_path: ICD 文件路径
            scl_result: 可选，预先解析的 SclImportResult，提供时跳过内部解析

        Returns:
            是否加载成功
        """
        if not self._client:
            return False
        success = self._client.load_model_from_icd(icd_path, scl_result=scl_result)
        if success:
            # 统一从 IEC61850Client 的标准化解析结果同步 UI 发现缓存。
            self._discovered_goose_items.clear()
            self._discovered_goose_items.extend(self._client._discovered_goose_items)
            self._discovered_datasets = self._client.get_discovered_datasets()
            self._discovered_rcbs = list(getattr(self._client, "_rcbs_from_icd", []))
            self._model_loaded = True
        return success

    def get_icd_points(self) -> dict[str, list]:
        """获取最近一次 ICD 导入的测点列表

        Returns:
            {"yc_points": [...], "yx_points": [...], "yk_points": [...], "yt_points": [...]}
        """
        if not self._client:
            return {"yc_points": [], "yx_points": [], "yk_points": [], "yt_points": []}
        return self._client.get_icd_points()

    def clear_cache(self) -> None:
        """清除客户端侧的缓存"""
        self._model_loaded = False
        self._discovered_goose_items.clear()
        self._discovered_datasets.clear()
        self._discovered_rcbs.clear()
        if self._client:
            self._client._last_import_result = None

    def check_model_cache(self) -> dict:
        """检查当前设备是否有可用的远程模型缓存

        Returns:
            {"cache_exists": bool, "cache_key": str}
        """
        if not self._client:
            return {"cache_exists": False, "cache_key": ""}
        return self._client.check_model_cache()

    def load_model_from_cache(self) -> bool:
        """从缓存加载模型（不进行 MMS 在线发现）

        与 remote_discover_model() 同步:
        - 重建 _discovered_goose_items、_discovered_datasets
        - 重建 _discovered_rcbs（从 IedModel.rcb_list 提取）
        - 通知 _on_points_discovered 注册测点

        Returns:
            缓存命中且加载成功返回 True
        """
        if not self._client:
            return False
        success = self._client.load_model_from_cache()
        if not success:
            return False

        # 同步 GOOSE 控制块
        self._discovered_goose_items.clear()
        self._discovered_goose_items.extend(self._client._discovered_goose_items)

        # 同步 DataSet 列表
        self._discovered_datasets.clear()
        if hasattr(self._client, "get_discovered_datasets"):
            self._discovered_datasets.extend(self._client.get_discovered_datasets())

        # 从缓存模型重建报告控制块列表（避免 Reports 侧边栏消失）
        self._discovered_rcbs.clear()
        try:
            cached_model = getattr(self._client, "_discovery", None)
            model = cached_model._model if cached_model and hasattr(cached_model, "_model") else None
            if model:
                for ld in model.lds:
                    for ln in ld.lns:
                        for rcb in ln.rcb_list:
                            # 将 RCBRef 中的 TrgOps/OptFields 位图转为前端 dict 格式
                            trg_map = {
                                "dchg": bool(rcb.trg_ops & 0x01),
                                "qchg": bool(rcb.trg_ops & 0x02),
                                "dupd": bool(rcb.trg_ops & 0x04),
                                "period": bool(rcb.trg_ops & 0x08),
                                "gi": bool(rcb.trg_ops & 0x10),
                            }
                            opt_map = {
                                "seq_num": bool(rcb.opt_fields & 0x01),
                                "time_stamp": bool(rcb.opt_fields & 0x02),
                                "reason_code": bool(rcb.opt_fields & 0x04),
                                "data_set": bool(rcb.opt_fields & 0x08),
                                "data_ref": bool(rcb.opt_fields & 0x10),
                                "buf_ovfl": bool(rcb.opt_fields & 0x20),
                                "entry_id": bool(rcb.opt_fields & 0x40),
                                "config_ref": bool(rcb.opt_fields & 0x80),
                            }
                            # 构建完整 DataSet 引用路径（MMS 格式: LD/LN.dataset）
                            ds_ref = rcb.dat_set
                            if ds_ref and "/" not in ds_ref and ld.name:
                                ds_ref = f"{ld.name}/{ln.name}.{ds_ref}"
                            self._discovered_rcbs.append(
                                {
                                    "ref": rcb.ref,
                                    "name": rcb.name,
                                    "rcb_type": rcb.rcb_type,
                                    "rpt_id": rcb.rpt_id,
                                    "ld": ld.name,
                                    "ln": ln.name,
                                    "data_set_ref": ds_ref,
                                    "intg_period": rcb.intg_pd,
                                    "rpt_ena": False,
                                    "trg_ops": trg_map,
                                    "opt_fields": opt_map,
                                }
                            )
        except Exception as e:
            if self._log:
                self._log.warning(f"从缓存模型重建 RCB 列表失败: {e}")

        # 通知上层注册测点
        if self._on_points_discovered:
            try:
                discovered = self._client.get_discovered_points()
                if discovered:
                    self._on_points_discovered(discovered)
            except Exception as e:
                if self._log:
                    self._log.error(f"从缓存加载模型: 注册测点时出错: {e}")

        self._model_loaded = True
        return True

    def remote_discover_model(self) -> bool:
        """远程发现模型（通过 MMS 在线遍历）

        如果客户端未连接，自动先连接再发现。
        注意：这是一个同步阻塞调用（connect + discover），
        不要在事件循环中直接调用。

        Returns:
            是否发现成功
        """
        if not self._client:
            return False
        if self._progress_active:
            if self._log:
                self._log.warning("IEC61850 连接或模型发现任务已在执行")
            return False

        # 用户显式触发的“重新发现”必须建立新的 MMS association。部分 IED
        # 会把数据模型目录绑定到 association；即使 Python 侧模型缓存已清空，
        # 复用旧连接仍可能继续浏览到切换前的模型。
        self._begin_progress("discover", self.PHASE_CONNECTING, 5, "正在重建 MMS 连接")

        try:
            if self._log:
                self._log.info("显式重新发现模型: 关闭旧 MMS association 并重新连接...")
            self._client.disconnect()
            self._is_running = False
            self._update_progress(self.PHASE_CONNECTING, 10, "正在建立新的 MMS 连接")
            if not self._start_tls_bridge():
                message = "启动 IEC61850 TLS 客户端桥接器失败"
                self._finish_progress(False, message)
                return False
            self._ensure_mms_capture_started()
            is_connected = self._client.connect(auto_discover=False)
            self._is_running = is_connected
            if not is_connected:
                tls_error = self._stop_tls_bridge_after_connect_failure()
                message = "重新建立 MMS 连接失败"
                if tls_error:
                    message = f"{message}: TLS 握手失败: {tls_error}"
                self._finish_progress(False, message)
                if self._log:
                    self._log.error(f"远程发现模型失败: {message}")
                return False

            self._update_progress(self.PHASE_DISCOVERING, 20, "开始远程发现模型")
            if self._log:
                self._log.info("开始远程发现模型...")

            discovery_timeout = self._discovery_timeout
            discovery_deadline = time.monotonic() + discovery_timeout

            def on_discovery_progress(phase: str, current: int, total: int, message: str) -> None:
                """接收模型发现进度，更新通道状态并向前端推送最新阶段与完成数量。"""
                if time.monotonic() >= discovery_deadline:
                    raise TimeoutError(f"IEC61850 模型发现超过 {discovery_timeout} 秒，任务已终止")
                ratio = min(max(current / total, 0.0), 1.0) if total > 0 else 0.0
                if phase == "discovering":
                    percent = 20 + round(ratio * 50)
                elif phase == "building":
                    percent = 75
                else:
                    percent = 80 + round(ratio * 5)
                self._update_progress(self.PHASE_DISCOVERING, percent, message)

            success = self._client.remote_discover_model(progress=on_discovery_progress)
            if not success:
                self._finish_progress(False, "远程模型发现失败")
                return False

            self._update_progress(self.PHASE_DISCOVERING, 88, "正在整理模型资源")

            # 保存发现的 GOOSE 控制块和 DataSet
            self._discovered_goose_items.clear()
            self._discovered_goose_items.extend(self._client._discovered_goose_items)
            if self._discovered_goose_items and self._log:
                self._log.info(
                    f"发现 {len(self._discovered_goose_items)} 个 GOOSE 控制块: "
                    + ", ".join(g.get("go_cb_ref", g.get("name", "")) for g in self._discovered_goose_items)
                )

            self._discovered_datasets.clear()
            if hasattr(self._client, "get_discovered_datasets"):
                self._discovered_datasets.extend(self._client.get_discovered_datasets())
                if self._discovered_datasets and self._log:
                    self._log.info(
                        f"发现 {len(self._discovered_datasets)} 个 DataSet: "
                        + ", ".join(ds.get("ref", ds.get("name", "")) for ds in self._discovered_datasets)
                    )

            # 缓存报告控制块
            self._update_progress(self.PHASE_DISCOVERING, 92, "正在发现报告控制块")
            self._discovered_rcbs.clear()
            client = getattr(self, "_client", None)
            if client and getattr(client, "reports", None):
                try:
                    self._discovered_rcbs.extend(client.reports.discover_rcbs())
                    if self._discovered_rcbs and self._log:
                        self._log.info(f"发现 {len(self._discovered_rcbs)} 个报告控制块")
                except Exception as e:
                    if self._log:
                        self._log.warning(f"缓存 RCB 失败: {e}")

            # 通知上层发现的测点
            self._update_progress(self.PHASE_DISCOVERING, 96, "正在刷新测点")
            if self._on_points_discovered:
                discovered = self._client.get_discovered_points()
                if discovered:
                    try:
                        self._on_points_discovered(discovered)
                    except Exception as e:
                        if self._log:
                            self._log.error(f"处理发现的测点时出错: {e}")

            self._model_loaded = True
            self._finish_progress(True, "远程模型发现完成")
            return True
        except Exception as e:
            self._finish_progress(False, str(e))
            if self._log:
                self._log.error(f"远程发现模型时出错: {e}")
            return False

    def _begin_progress(self, operation: str, phase: str, progress: int, message: str) -> None:
        """开始一轮连接、发现或批读进度，重置计时和操作标识。"""
        self._progress_operation_id += 1
        self._progress_operation = operation
        self._progress_error_code = ""
        self._progress_active = True
        self._progress_started_at = time.monotonic()
        self._progress_elapsed_seconds = 0
        self._update_progress(phase, progress, message)

    def _update_progress(self, phase: str, progress: int, message: str = "") -> None:
        """更新可供前端轮询的进度快照。"""
        self._connect_phase = phase
        self._connect_progress = min(max(int(progress), 0), 100)
        self._progress_message = message

    def _finish_progress(self, success: bool, message: str = "") -> None:
        """结束进度并保留最终快照，避免前端读到重置后的 0%。"""
        if self._progress_started_at is not None:
            self._progress_elapsed_seconds = max(0, int(time.monotonic() - self._progress_started_at))
        self._progress_active = False
        self._progress_started_at = None
        final_phase = self.PHASE_DONE if success else self.PHASE_FAILED
        final_progress = 100 if success else self._connect_progress
        self._update_progress(final_phase, final_progress, message)

    async def stop(self) -> bool:
        """停止客户端（断开连接）"""
        self.disconnect()
        return True

    def connect(self) -> bool:
        """同步连接方法（仅连接 MMS 服务器，不自动发现模型）

        v2.0: 模型发现与连接分离。连接后调用 remote_discover_model() 或
        load_model_from_icd() 来加载模型。

        注意：此方法会阻塞调用线程，不建议在事件循环中直接调用。
        通常应使用 async start() 方法（后台线程执行连接）。
        """
        if not self._client:
            self._connect_phase = self.PHASE_FAILED
            return False

        self._connect_phase = self.PHASE_CONNECTING
        self._connect_progress = 10
        if not self._start_tls_bridge():
            self._connect_phase = self.PHASE_FAILED
            self._connect_progress = 0
            self._progress_error_code = "tls_bridge_start_failed"
            self._progress_message = "启动 IEC61850 TLS 客户端桥接器失败"
            return False
        self._ensure_mms_capture_started()
        is_connected = self._client.connect(auto_discover=False)  # 仅连接，不自动发现
        self._is_running = is_connected

        if not is_connected:
            tls_error = self._stop_tls_bridge_after_connect_failure()
            self._connect_phase = self.PHASE_FAILED
            self._connect_progress = 0
            self._progress_error_code = "connection_failed"
            if tls_error:
                self._progress_message = f"IEC61850 TLS 握手失败: {tls_error}"
            else:
                self._progress_message = "无法连接 IEC61850 服务端，请检查 IP、端口和服务状态"
            return False

        # 离线模型只能在主 MMS association 建立后确认它
        # 是否仍属于当前服务端。失败时不能带着旧点表进入运行态。
        if self._client.offline_model_requires_validation:
            if not self._client.validate_loaded_offline_model():
                self.clear_cache()
                self._client.disconnect()
                self._is_running = False
                self._connect_phase = self.PHASE_FAILED
                self._connect_progress = 0
                self._progress_error_code = "model_mismatch"
                self._progress_message = "离线模型与当前 IEC61850 服务端不匹配，请重新加载正确模型或在线发现"
                if self._log:
                    self._log.error(self._progress_message)
                return False

            # 离线模型确认匹配后，才在当前 association 上恢复 RCB 目录状态。
            reports = getattr(self._client, "reports", None)
            if reports and hasattr(reports, "restore_cached_rcbs"):
                restored = reports.restore_cached_rcbs(self._discovered_rcbs)
                if not restored and self._log:
                    self._log.warning("离线模型匹配，但部分 RCB 目录预热失败")

        self._connect_progress = 100
        self._connect_phase = self.PHASE_DONE
        return is_connected

    def _connect_background(self):
        """在后台线程中执行连接（避免 IedConnection_connect 持有 GIL 阻塞事件循环）"""
        try:
            self.connect()
        except Exception as e:
            self._progress_error_code = "connection_exception"
            self._progress_message = f"连接 IEC61850 服务端异常: {e}"
            if self._log:
                self._log.error(f"连接 IEC 61850 服务器失败: {e}")
            self._is_running = False
            self._connect_phase = self.PHASE_FAILED
            self._connect_progress = 0
        finally:
            self._connecting = False
            self._finish_progress(self._connect_phase == self.PHASE_DONE, self._progress_message)

    def get_connect_progress(self) -> dict:
        """获取连接进度信息

        Returns:
            {"phase": str, "progress": int, "connecting": bool, "active": bool, ...}
            phase: idle/connecting/discovering/reading/done/failed
            progress: 0-100
            connecting: 是否正在连接中
        """
        elapsed_seconds = self._progress_elapsed_seconds
        if self._progress_active and self._progress_started_at is not None:
            elapsed_seconds = max(0, int(time.monotonic() - self._progress_started_at))
        return {
            "phase": self._connect_phase,
            "progress": self._connect_progress,
            "connecting": self._connecting,
            "active": self._progress_active,
            "operation": self._progress_operation,
            "operation_id": self._progress_operation_id,
            "elapsed_seconds": elapsed_seconds,
            "message": self._progress_message,
            "error_code": self._progress_error_code,
        }

    def disconnect(self) -> None:
        """断开连接（仅关闭 MMS 连接，保留模型缓存）

        断开连接不会清除模型缓存、测点列表、GOOSE 控制块、
        DataSet 列表和报告控制块。如需清除，请调用 clear_cache()。
        """
        self._connecting = False
        self._progress_active = False
        self._progress_operation = "idle"
        self._progress_started_at = None
        self._progress_elapsed_seconds = 0
        self._progress_message = ""
        self._progress_error_code = ""
        self._connect_phase = self.PHASE_IDLE
        self._connect_progress = 0
        if self._client:
            self._client.disconnect()
        if self._tls_bridge:
            self._tls_bridge.stop()
        if self._mms_capture:
            self._mms_capture.stop()
        self._is_running = False

    @property
    def is_running(self) -> bool:
        """检测客户端的真实连接状态"""
        if self._connecting:
            return False  # 连接中，尚未成功
        if not self._is_running:
            return False
        if not self._client:
            return False
        return self._client.is_connected

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值"""
        if not self._client or not self.is_running:
            if self._log:
                self._log.error("IEC 61850 客户端未连接")
            return None

        fc = getattr(point, "fc", "") or ""
        real_val = self._client.read_point(address=point.address, fc=fc)
        if real_val is None:
            if self._log:
                self._log.error("IEC 61850 客户端读取测点值失败")
            return None

        # 遥测点需根据系数反向换算
        if isinstance(point, Yc):
            try:
                return int((real_val - point.add_coe) / point.mul_coe)
            except (ZeroDivisionError, TypeError):
                if self._log:
                    self._log.error("IEC 61850 客户端系数计算失败")
                return None
        return real_val

    def read_metadata(self, point: BasePoint) -> dict:
        """按需读取测点的品质(q)与时标(t)元数据

        Args:
            point: 测点对象 (需含 address 属性)

        Returns:
            {"quality": {...}, "timestamp": {...}} 字典，可直接返回前端
        """
        if not self._client or not self.is_running:
            if self._log:
                self._log.error("IEC 61850 客户端未连接")
            return {"quality": {}, "timestamp": {}}

        fc = getattr(point, "fc", "") or ""
        meta = self._client.read_metadata(address=str(point.address), fc=fc)
        return meta.to_dict()

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值（发送命令）

        底层 Iec61850Writer.write() 已内置断线重连逻辑，
        因此此处不拦截 is_running 检查，让 writer 自行处理重连。
        """
        if not self._client:
            return False
        # 连接尚未就绪（后台线程仍在连接中），不能写入
        if self._connecting:
            return False

        real_to_send = value

        try:
            fc = getattr(point, "fc", "") or ""
            if isinstance(point, (Yc, Yt)):
                real_to_send = value * point.mul_coe + point.add_coe
                return self._client.write_point(
                    address=point.address,
                    value=float(real_to_send),
                    fc=fc,
                )
            elif isinstance(point, (Yx, Yk)):
                return self._client.write_point(
                    address=point.address,
                    value=bool(real_to_send),
                    fc=fc,
                )
        except Exception as e:
            if self._log:
                self._log.error(f"IEC 61850 客户端写入失败: {e}")
            return False

        return False

    def read_points_batch(
        self,
        points: Sequence[BasePoint],
        *,
        track_progress: bool = False,
    ) -> dict[str, Any]:
        """批量读取测点值

        优先按远端 DataSet 批量读取，并保持 point.code 映射和遥测系数换算。
        ``track_progress`` 用于 HTTP 批读场景，把每个 DataSet 的完成情况写入
        统一进度快照，供前端在请求执行期间轮询。

        Args:
            points: 测点列表

        Returns:
            {point.code: value} 字典，读取失败的测点不包含在结果中
        """
        if not self._client or not self.is_running:
            return {}

        # 连接/发现任务正在运行时不覆盖它们的进度；批读本身仍可按原逻辑执行。
        owns_progress = track_progress and not self._progress_active
        if owns_progress:
            self._begin_progress("read", self.PHASE_READING, 1, "正在规划 DataSet 批量读取")

        def on_read_progress(phase: str, current: int, total: int, message: str) -> None:
            """把协议层分段进度映射到稳定、单调递增的前端百分比。"""
            if not owns_progress:
                return
            safe_total = max(int(total), 1)
            ratio = min(max(int(current), 0), safe_total) / safe_total
            if phase == "planning":
                percent = 3
            elif phase in {"dataset", "retry"}:
                percent = 5 + round(ratio * 85)
            elif phase == "fallback":
                percent = 90 + round(ratio * 9)
            else:
                percent = self._connect_progress
            # 重连重规划可能重新从第一个 DataSet 开始，进度条不能倒退。
            percent = max(self._connect_progress, min(percent, 99))
            self._update_progress(self.PHASE_READING, percent, message)

        try:
            # 构建地址列表和 FC 映射。
            addresses = []
            fc_map = {}
            addr_to_code = {}  # address -> point.code (用于结果映射)
            point_map = {}  # address -> point (用于系数换算)

            for point in points:
                addr = str(point.address)
                addresses.append(addr)
                fc = getattr(point, "fc", "") or ""
                if fc:
                    fc_map[addr] = fc
                addr_to_code[addr] = point.code
                point_map[addr] = point

            # 非进度场景不传新关键字，兼容外部测试替身和旧客户端适配器。
            if owns_progress:
                raw_results = self._client.read_points_batch(addresses, fc_map, progress=on_read_progress)
            else:
                raw_results = self._client.read_points_batch(addresses, fc_map)

            # 系数换算（遥测点需反向换算）。
            results: dict[str, Any] = {}
            for addr, value in raw_results.items():
                point = point_map.get(addr)
                code = addr_to_code.get(addr, addr)
                if point and isinstance(point, Yc):
                    # 遥测点只接受数值，跳过字符串值（如 dU 的描述文本），
                    # 避免后续 point.value 赋值时引发 int() 转换错误。
                    if isinstance(value, str):
                        continue
                    try:
                        results[code] = int((value - point.add_coe) / point.mul_coe)
                    except (ZeroDivisionError, TypeError):
                        results[code] = value
                else:
                    results[code] = value

            if owns_progress:
                failed = max(len(points) - len(results), 0)
                self._finish_progress(True, f"DataSet 批量读取完成：成功 {len(results)}，失败 {failed}")
            return results
        except Exception as exc:
            if owns_progress:
                self._finish_progress(False, f"DataSet 批量读取失败：{exc}")
            raise

    async def read_value_async(self, point: BasePoint) -> Any:
        """异步读取测点值"""
        return self.read_value(point)

    async def read_metadata_async(self, point: BasePoint) -> dict:
        """异步按需读取测点的品质(q)与时标(t)元数据"""
        return self.read_metadata(point)

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        """异步写入测点值"""
        return self.write_value(point, value)

    def add_points(self, points: list[BasePoint]) -> None:
        """注册测点到 IEC 61850 客户端"""
        if not self._client:
            return

        for point in points:
            fc = getattr(point, "fc", "") or ""
            self._client.add_point(
                address=point.address,
                frame_type=point.frame_type,
                fc=fc,
            )

    def get_discovered_datasets(self) -> list[dict[str, Any]]:
        """获取发现的 DataSet 列表"""
        return list(self._discovered_datasets)

    def get_discovered_rcbs(self) -> list[dict[str, Any]]:
        """获取连接时缓存的报告控制块列表"""
        return list(self._discovered_rcbs)

    def set_discovered_rcbs(self, rcbs: list[dict[str, Any]]) -> None:
        """更新 RCB 缓存 (供首次现场发现成功后回写)"""
        self._discovered_rcbs = list(rcbs)

    def update_discovered_rcb(self, rcb_ref: str, updated: dict[str, Any]) -> None:
        """更新缓存中单个 RCB 记录 (使能/禁用/GI 等操作后局部刷新)"""
        for i, rcb in enumerate(self._discovered_rcbs):
            if rcb.get("ref") == rcb_ref:
                self._discovered_rcbs[i] = updated
                return

    def read_dataset_values(self, dataset_ref: str) -> dict[str, Any]:
        """通过 DataSet 批量读取所有成员值

        Args:
            dataset_ref: DataSet 引用路径，如 "LD0/LLN0$dsGOOSE1"

        Returns:
            {fcda_ref: value} 字典
        """
        if not self._client or not self.is_running:
            return {}
        return self._client.read_dataset_values(dataset_ref)

    @property
    def client(self):
        """获取底层客户端对象"""
        return self._client

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取捕获的报文列表"""
        return self._mms_capture.get_messages(limit) if self._mms_capture else []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._mms_capture:
            self._mms_capture.clear()

    def get_avg_time(self) -> dict:
        """获取平均收发时间"""
        return self._mms_capture.get_avg_time() if self._mms_capture else {}
