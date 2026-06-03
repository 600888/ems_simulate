"""
IEC 61850 协议处理器
支持 IEC 61850 MMS 服务端和客户端
"""

from typing import Any

from src.device.protocol.base_handler import ClientHandler, ServerHandler
from src.enums.point_data import Yc, Yk, Yt, Yx
from src.enums.points.base_point import BasePoint


class IEC61850ServerHandler(ServerHandler):
    """IEC 61850 服务端处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._server = None
        self._log = log

    def initialize(self, config: dict[str, Any]) -> None:
        """初始化 IEC 61850 服务器

        Args:
            config: 配置字典，包含:
                - ip: 监听 IP（默认 0.0.0.0）
                - port: 监听端口（默认 102）
                - model_name: IED 模型名称
                - ied_name: IED 名称
                - ld_name: 逻辑设备名称
        """
        from src.proto.iec61850.iec61850_server import IEC61850Server

        self._config = config
        ip = config.get("ip", "0.0.0.0")
        port = config.get("port", 102)
        model_name = config.get("model_name")
        ied_name = config.get("ied_name")
        ld_name = config.get("ld_name", "GenericLD")

        # model_name 由 Device._build_protocol_config() 从通道配置传入，
        # 对应 ICD 文件的 IED 名称 (如 "PCS001G")，传给 ied_name 参数
        effective_ied = ied_name or model_name or "EMS"

        self._server = IEC61850Server(
            ip=ip,
            port=port,
            model_name=effective_ied,
            ied_name=effective_ied,
            ld_name=ld_name,
        )

    async def start(self) -> bool:
        """启动 IEC 61850 服务器"""
        try:
            if self._server:
                self._server.start()
                self._is_running = self._server.is_running
                return self._is_running
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"启动 IEC 61850 服务器失败: {e}")
            return False

    async def stop(self) -> bool:
        """停止 IEC 61850 服务器"""
        try:
            if self._server:
                self._server.stop()
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
        if self._server and hasattr(self._server, "browse_datasets"):
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
        # IEC 61850 MMS 目前不支持报文捕获
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        pass

    def get_avg_time(self) -> dict:
        """获取平均收发时间"""
        return {}


class IEC61850ClientHandler(ClientHandler):
    """IEC 61850 客户端处理器"""

    # 连接阶段定义
    PHASE_IDLE = "idle"  # 未开始
    PHASE_CONNECTING = "connecting"  # 正在连接服务器
    PHASE_DISCOVERING = "discovering"  # 正在发现模型
    PHASE_DONE = "done"  # 连接完成
    PHASE_FAILED = "failed"  # 连接失败

    def __init__(self, log=None):
        super().__init__()
        self._client = None
        self._log = log
        self._on_points_discovered = None  # 测点发现回调
        self._connecting = False  # 是否正在连接中（防止重复启动）
        self._connect_phase = self.PHASE_IDLE  # 当前连接阶段
        self._connect_progress = 0  # 连接进度 0-100
        self._discovered_goose_items: list[dict[str, Any]] = []  # 发现的 GOOSE 控制块
        self._discovered_datasets: list[dict[str, Any]] = []  # 发现的 DataSet 列表
        self._discovered_rcbs: list[dict[str, Any]] = []  # 发现的报告控制块 (连接时缓存)

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

        self._client = IEC61850Client(
            ip=ip,
            port=port,
            model_name=model_name,
            ld_name=ld_name,
        )

    async def start(self) -> bool:
        """启动客户端（在后台线程中连接服务器，立即返回）

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

        # 重置连接进度（重新连接时清除上一次的状态）
        self._connect_phase = self.PHASE_IDLE
        self._connect_progress = 0

        self._connecting = True
        import threading

        thread = threading.Thread(target=self._connect_background, daemon=True)
        thread.start()
        return True  # 立即返回，表示连接任务已受理

    async def stop(self) -> bool:
        """停止客户端（断开连接）"""
        self.disconnect()
        return True

    def connect(self) -> bool:
        """同步连接方法（供外部直接调用）

        注意：此方法会阻塞调用线程，不建议在事件循环中直接调用。
        通常应使用 async start() 方法（后台线程执行连接）。
        """
        if not self._client:
            self._connect_phase = self.PHASE_FAILED
            return False

        # 阶段1: 连接服务器
        self._connect_phase = self.PHASE_CONNECTING
        self._connect_progress = 10
        is_connected = self._client.connect(auto_discover=False)  # 仅连接，不自动发现
        self._is_running = is_connected

        if not is_connected:
            self._connect_phase = self.PHASE_FAILED
            self._connect_progress = 0
            return False

        # 阶段2: 发现数据模型
        self._connect_phase = self.PHASE_DISCOVERING
        self._connect_progress = 40
        self._client.discover_model()
        self._connect_progress = 80

        # 阶段3: 保存发现的 GOOSE 控制块和 DataSet（供结构树展示）
        if self._client:
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

            # 缓存报告控制块 (RCB)，避免 structure 接口每次现场探测导致首屏空白
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

        # 阶段4: 通知上层发现的测点
        if self._on_points_discovered:
            discovered = self._client.get_discovered_points()
            if discovered:
                try:
                    self._on_points_discovered(discovered)
                except Exception as e:
                    if self._log:
                        self._log.error(f"处理发现的测点时出错: {e}")

        self._connect_phase = self.PHASE_DONE
        self._connect_progress = 100
        return is_connected

    def _connect_background(self):
        """在后台线程中执行连接（避免 IedConnection_connect 持有 GIL 阻塞事件循环）"""
        try:
            self.connect()
        except Exception as e:
            if self._log:
                self._log.error(f"连接 IEC 61850 服务器失败: {e}")
            self._is_running = False
            self._connect_phase = self.PHASE_FAILED
            self._connect_progress = 0
        finally:
            self._connecting = False

    def get_connect_progress(self) -> dict:
        """获取连接进度信息

        Returns:
            {"phase": str, "progress": int, "connecting": bool}
            phase: idle/connecting/discovering/done/failed
            progress: 0-100
            connecting: 是否正在连接中
        """
        return {
            "phase": self._connect_phase,
            "progress": self._connect_progress,
            "connecting": self._connecting,
        }

    def disconnect(self) -> None:
        """断开连接"""
        self._connecting = False
        self._connect_phase = self.PHASE_IDLE
        self._connect_progress = 0
        self._discovered_goose_items = []
        self._discovered_datasets = []
        if self._client:
            self._client.disconnect()
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

        from src.proto.iec61850.core.metadata import MetadataInfo

        fc = getattr(point, "fc", "") or ""
        meta = self._client.read_metadata(address=point.address, fc=fc)
        return meta.to_dict()

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值（发送命令）"""
        if not self._client or not self.is_running:
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

    def read_points_batch(self, points: list[BasePoint]) -> dict[str, Any]:
        """批量读取测点值

        利用 IEC61850Client 的 read_points_batch 按 iec_type 分组读取，
        减少类型判断开销，连接断开时快速失败。

        Args:
            points: 测点列表

        Returns:
            {point.code: value} 字典，读取失败的测点不包含在结果中
        """
        if not self._client or not self.is_running:
            return {}

        # 构建地址列表和 FC 映射
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

        # 批量读取
        raw_results = self._client.read_points_batch(addresses, fc_map)

        # 系数换算 (遥测点需反向换算)
        results: dict[str, Any] = {}
        for addr, value in raw_results.items():
            point = point_map.get(addr)
            code = addr_to_code.get(addr, addr)
            if point and isinstance(point, Yc):
                try:
                    results[code] = int((value - point.add_coe) / point.mul_coe)
                except (ZeroDivisionError, TypeError):
                    results[code] = value
            else:
                results[code] = value

        return results

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
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        pass

    def get_avg_time(self) -> dict:
        """获取平均收发时间"""
        return {}
