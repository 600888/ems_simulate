"""
GOOSE 抓包 WebSocket 实时推送

提供基于 WebSocket 的 GOOSE 报文推送服务，替代前端轮询。
使用观察者模式管理多个 WebSocket 连接。

设计模式:
- 单例模式 (WebSocketSessionManager): 全局统一管理会话
- 观察者模式 (WebSocket -> GooseCapture 回调): 报文到达时自动推送

消息协议 (JSON):
  Client → Server:
    {"type":"command", "action":"start", "params":{...}}
    {"type":"command", "action":"stop"}
    {"type":"command", "action":"clear"}
    {"type":"command", "action":"list", "params":{"count":0}}
    {"type":"command", "action":"status"}

  Server → Client:
    {"type":"packet", "data":{...}}        ← 实时报文推送
    {"type":"response", "command":"...", "success":true, "data":{...}}
    {"type":"error", "message":"..."}
    {"type":"statistics", "data":{...}}    ← 统计更新
"""

import asyncio
import contextlib
import json
import threading
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.web.log import log


def _get_event_loop():
    """获取当前运行的事件循环，适应多线程环境"""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


# ===== 消息类型常量 =====


class MsgType:
    COMMAND = "command"
    PACKET = "packet"
    RESPONSE = "response"
    ERROR = "error"
    STATISTICS = "statistics"


class Action:
    START = "start"
    STOP = "stop"
    CLEAR = "clear"
    LIST = "list"
    STATUS = "status"


# ===== WebSocket 会话管理器 (单例) =====


class WebSocketSessionManager:
    """WebSocket 会话管理器

    单例模式，统一管理所有 GOOSE 抓包 WebSocket 连接。
    将捕获到的 GOOSE 报文实时推送给所有连接的客户端。
    """

    _instance: Optional["WebSocketSessionManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._connections: set[WebSocket] = set()
        self._lock = threading.Lock()
        self._capture_instance: Any | None = None
        self._capture_callback_registered = False
        self._capture_started = False

    # ---- 连接管理 ----

    async def connect(self, ws: WebSocket) -> bool:
        """接受并注册一个新的 WebSocket 连接"""
        try:
            await ws.accept()
            with self._lock:
                self._connections.add(ws)
            log.info(f"GOOSE WebSocket 客户端已连接, 当前连接数: {len(self._connections)}")
            return True
        except Exception as e:
            log.error(f"WebSocket 连接接受失败: {e}")
            return False

    async def disconnect(self, ws: WebSocket):
        """断开并移除一个 WebSocket 连接"""
        with self._lock:
            self._connections.discard(ws)
            log.info(f"GOOSE WebSocket 客户端已断开, 当前连接数: {len(self._connections)}")

    # ---- 消息广播 ----

    async def broadcast(self, message: dict[str, Any]):
        """向所有已连接的客户端广播消息"""
        if not self._connections:
            return
        payload = json.dumps(message, ensure_ascii=False, default=str)
        disconnected = []
        with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_text(payload)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                self._connections.discard(ws)

    async def send_to(self, ws: WebSocket, message: dict[str, Any]):
        """向指定客户端发送消息"""
        try:
            payload = json.dumps(message, ensure_ascii=False, default=str)
            await ws.send_text(payload)
        except Exception as e:
            log.warning(f"WebSocket 发送消息失败: {e}")
            await self.disconnect(ws)

    # ---- 报文回调 — 从捕获引擎接收实时报文 ----

    def _on_packet_captured(self, packet_dict: dict[str, Any]):
        """GOOSE 报文捕获回调 (在捕获引擎的线程中调用)

        由于回调在非异步线程中执行，使用 run_coroutine_threadsafe
        将广播任务调度到主事件循环中执行。
        """
        try:
            loop = _get_event_loop()
            if loop is None or loop.is_closed():
                log.warning("事件循环不可用，跳过 GOOSE 报文推送")
                return

            asyncio.run_coroutine_threadsafe(
                self.broadcast(
                    {
                        "type": MsgType.PACKET,
                        "data": packet_dict,
                    }
                ),
                loop,
            )
        except Exception as e:
            log.warning(f"推送 GOOSE 报文失败: {e}")

    # ---- 指令处理 ----

    async def handle_command(self, ws: WebSocket, message: dict[str, Any]):
        """处理来自客户端的指令"""
        action = message.get("action", "")
        params = message.get("params", {})

        try:
            from src.proto.iec61850.plugins.goose.capture import GooseCaptureEngine

            if action == Action.START:
                await self._handle_start(ws, params, GooseCaptureEngine)
            elif action == Action.STOP:
                await self._handle_stop(ws)
            elif action == Action.CLEAR:
                await self._handle_clear(ws)
            elif action == Action.LIST:
                await self._handle_list(ws, params)
            elif action == Action.STATUS:
                await self._handle_status(ws)
            else:
                await self.send_to(
                    ws,
                    {
                        "type": MsgType.ERROR,
                        "message": f"未知指令: {action}",
                    },
                )
        except Exception as e:
            log.error(f"处理指令 {action} 异常: {e}")
            await self.send_to(
                ws,
                {
                    "type": MsgType.ERROR,
                    "message": f"指令处理失败: {e}",
                },
            )

    async def _handle_start(self, ws: WebSocket, params: dict[str, Any], GooseCaptureEngine):
        """启动 GOOSE 抓包"""
        from src.web.api.channel.goose import GOOSE_CAPTURE_INSTANCES

        interface = params.get("interface", "")
        max_packets = params.get("max_packets", 500)
        filter_app_id = params.get("filter_app_id")

        # 获取或创建捕获器
        key = interface or "__default__"
        capture = GOOSE_CAPTURE_INSTANCES.get(key)

        if capture is None:
            capture = GooseCaptureEngine(interface=interface)
            GOOSE_CAPTURE_INSTANCES[key] = capture

        capture._max_packets = max_packets
        if filter_app_id is not None:
            capture.set_app_id_filter(filter_app_id)

        # 注册回调 — 用于实时推送（只需注册一次）
        if not self._capture_callback_registered:
            capture.set_callback(self._on_packet_captured)
            self._capture_callback_registered = True
            self._capture_instance = capture

        success = capture.start()
        if success:
            self._capture_started = True
            log.info(f"WebSocket 启动 GOOSE 抓包: interface={interface or 'auto'}")
            await self.send_to(
                ws,
                {
                    "type": MsgType.RESPONSE,
                    "command": Action.START,
                    "success": True,
                    "data": {"interface": interface or "auto", "is_running": True},
                },
            )
        else:
            await self.send_to(
                ws,
                {
                    "type": MsgType.RESPONSE,
                    "command": Action.START,
                    "success": False,
                    "message": "启动失败 (可能需要管理员/root 权限)",
                },
            )

    async def _handle_stop(self, ws: WebSocket):
        """停止 GOOSE 抓包

        使用 signal_stop() 非阻塞停止，不等待捕获线程退出，
        避免 thread.join() 阻塞事件循环导致 WebSocket 响应发不出去。
        """
        from src.web.api.channel.goose import GOOSE_CAPTURE_INSTANCES

        for capture in GOOSE_CAPTURE_INSTANCES.values():
            if capture.is_running:
                # 先移除回调，防止停止过程中推送残留报文
                with contextlib.suppress(Exception):
                    capture.set_callback(None)
                # 非阻塞停止 — 仅设标记，不 join 线程
                capture.signal_stop()

        self._capture_started = False
        log.info("WebSocket 停止 GOOSE 抓包")
        await self.send_to(
            ws,
            {
                "type": MsgType.RESPONSE,
                "command": Action.STOP,
                "success": True,
                "data": {},
            },
        )

    async def _handle_clear(self, ws: WebSocket):
        """清空捕获的报文"""
        from src.web.api.channel.goose import GOOSE_CAPTURE_INSTANCES

        for capture in GOOSE_CAPTURE_INSTANCES.values():
            capture.clear()

        await self.send_to(
            ws,
            {
                "type": MsgType.RESPONSE,
                "command": Action.CLEAR,
                "success": True,
                "data": {},
            },
        )

    async def _handle_list(self, ws: WebSocket, params: dict[str, Any]):
        """获取捕获的报文列表"""
        from src.web.api.channel.goose import GOOSE_CAPTURE_INSTANCES

        count = params.get("count", 0)
        filter_app_id = params.get("filter_app_id")

        capture = None
        for c in GOOSE_CAPTURE_INSTANCES.values():
            if c.is_running:
                capture = c
                break

        if not capture:
            await self.send_to(
                ws,
                {
                    "type": MsgType.RESPONSE,
                    "command": Action.LIST,
                    "success": False,
                    "message": "没有正在运行的 GOOSE 抓包会话",
                },
            )
            return

        packets = capture.get_packets(count=count, filter_app_id=filter_app_id)
        stats = capture.get_statistics()
        status = capture.get_status()

        await self.send_to(
            ws,
            {
                "type": MsgType.RESPONSE,
                "command": Action.LIST,
                "success": True,
                "data": {
                    "packets": packets,
                    "statistics": stats,
                    "status": status,
                },
            },
        )

    async def _handle_status(self, ws: WebSocket):
        """获取抓包状态"""
        from src.web.api.channel.goose import GOOSE_CAPTURE_INSTANCES

        results = []
        for capture in GOOSE_CAPTURE_INSTANCES.values():
            results.append(capture.get_status())

        await self.send_to(
            ws,
            {
                "type": MsgType.RESPONSE,
                "command": Action.STATUS,
                "success": True,
                "data": {"captures": results},
            },
        )

    # ---- 属性 ----

    @property
    def is_capture_running(self) -> bool:
        return self._capture_started


# ===== WebSocket 路由 =====

ws_router = APIRouter(tags=["goose-websocket"])


@ws_router.websocket("/goose/capture/ws")
async def goose_capture_websocket(ws: WebSocket):
    """GOOSE 抓包 WebSocket 端点

    通过 WebSocket 实现:
    - 实时接收 GOOSE 报文推送
    - 通过指令控制抓包 (start/stop/clear/list/status)
    - 避免前端频繁轮询 HTTP 接口
    """
    manager = WebSocketSessionManager()

    # 接受连接
    connected = await manager.connect(ws)
    if not connected:
        return

    try:
        while True:
            # 接收客户端消息
            raw = await ws.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_to(
                    ws,
                    {
                        "type": MsgType.ERROR,
                        "message": "无效的 JSON 消息",
                    },
                )
                continue

            msg_type = message.get("type", "")

            if msg_type == MsgType.COMMAND:
                await manager.handle_command(ws, message)
            else:
                await manager.send_to(
                    ws,
                    {
                        "type": MsgType.ERROR,
                        "message": f"不支持的消息类型: {msg_type}",
                    },
                )

    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception as e:
        log.warning(f"WebSocket 连接异常: {e}")
        await manager.disconnect(ws)
