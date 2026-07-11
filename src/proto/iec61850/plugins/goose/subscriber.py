"""GOOSE 接收器/订阅者 - 基于 pyiec61850 实现 GOOSE 报文接收

管理单个网络接口上的 GOOSE 报文接收和多个订阅。
"""

from __future__ import annotations

from collections.abc import Callable
import threading
import time
from typing import Any

from pyiec61850 import pyiec61850 as iec61850

from ...defs.constants import HAS_IEC61850
from ...log import log
from .types import GooseState, GooseSubscriptionInfo, MmsType, ReceiverConfig


class _PyGooseHandler(iec61850.GooseHandler):
    """GooseHandler SWIG director 子类，将 C++ trigger() 回调转发到 Python"""

    def __init__(self, receiver: GooseReceiver):
        super().__init__()
        self._receiver = receiver

    def trigger(self):
        """C++ 层收到 GOOSE 报文时调用"""
        try:
            subscriber = self._libiec61850_goose_subscriber
            self._receiver._on_goose_message(subscriber)
        except Exception as e:
            log.error(f"GOOSE handler 异常: {e}")


class _DataSetParser:
    """GOOSE 数据集值解析策略类

    将数据集解析逻辑从 GooseReceiver 中分离，
    便于测试和未来扩展不同解析方式。
    """

    @staticmethod
    def parse(subscriber: Any) -> list[dict[str, Any]]:
        """解析 GOOSE 数据集值"""
        values: list[dict[str, Any]] = []
        try:
            dataset = iec61850.GooseSubscriber_getDataSetValues(subscriber)
            if not dataset:
                return values

            array_size = iec61850.MmsValue_getArraySize(dataset)
            for i in range(array_size):
                element = iec61850.MmsValue_getElement(dataset, i)
                if not element:
                    continue

                entry = _DataSetParser._parse_element(element, i)
                values.append(entry)
        except Exception as e:
            log.error(f"解析 GOOSE 数据集失败: {e}")

        return values

    @staticmethod
    def _parse_element(element: Any, index: int) -> dict[str, Any]:
        """解析单个 MMS 数据元素"""
        entry: dict[str, Any] = {"index": index, "type": "unknown", "value": None}

        mms_type = iec61850.MmsValue_getType(element)

        if mms_type == MmsType.BOOLEAN:
            entry["type"] = "boolean"
            entry["value"] = bool(iec61850.MmsValue_getBoolean(element))
        elif mms_type == MmsType.INTEGER:
            entry["type"] = "integer"
            entry["value"] = int(iec61850.MmsValue_toInt32(element))
        elif mms_type == MmsType.UNSIGNED:
            entry["type"] = "unsigned"
            entry["value"] = int(iec61850.MmsValue_toUint32(element))
        elif mms_type == MmsType.FLOAT:
            entry["type"] = "float"
            entry["value"] = float(iec61850.MmsValue_toFloat(element))
        elif mms_type == MmsType.VISIBLE_STRING:
            entry["type"] = "string"
            entry["value"] = str(iec61850.MmsValue_toString(element) or "")
        elif mms_type == MmsType.UTC_TIME:
            entry["type"] = "timestamp"
            entry["value"] = int(iec61850.MmsValue_getUtcTimeInMs(element))
        elif mms_type == MmsType.BIT_STRING:
            entry["type"] = "bitstring"
            entry["value"] = int(iec61850.MmsValue_getBitStringAsInteger(element))

        return entry


class GooseReceiver:
    """IEC 61850 GOOSE 接收器

    管理单个网络接口上的 GOOSE 报文接收和多个订阅。

    典型用法:
        config = ReceiverConfig(interface="eth0")
        receiver = GooseReceiver(config)
        receiver.add_subscription("LD0/LLN0$GO$gcb1", app_id=0x0001)
        receiver.set_callback(my_callback)
        receiver.start()
        ...
        receiver.stop()
    """

    def __init__(self, config: ReceiverConfig):
        if not HAS_IEC61850:
            raise RuntimeError("pyiec61850 未安装，无法创建 GOOSE Receiver")

        self._config = config
        self._subscriptions: dict[str, GooseSubscriptionInfo] = {}
        self._is_running = False
        self._callback: Callable[[dict[str, Any]], None] | None = None
        self._lock = threading.Lock()

        # 底层
        self._receiver: Any = None
        self._subscriber_handles: list[Any] = []

        # SWIG director handler (防止 GC)
        self._goose_handlers: list[Any] = []
        self._goose_subscriber_py_list: list[Any] = []

        # 状态监控
        self._monitor_stop = threading.Event()
        self._monitor_thread: threading.Thread | None = None

    @property
    def config(self) -> ReceiverConfig:
        return self._config

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def interface(self) -> str:
        return self._config.interface

    # ===== 订阅管理 =====

    def add_subscription(
        self,
        go_cb_ref: str,
        app_id: int | None = None,
        dst_mac: list[int] | None = None,
        description: str = "",
        data_set_ref: str = "",
        conf_rev: int = 0,
    ) -> GooseSubscriptionInfo:
        """添加 GOOSE 订阅"""
        with self._lock:
            if go_cb_ref in self._subscriptions:
                return self._subscriptions[go_cb_ref]

            sub = GooseSubscriptionInfo(
                go_cb_ref=go_cb_ref,
                app_id=app_id,
                dst_mac=dst_mac,
                description=description,
                data_set_ref=data_set_ref,
                conf_rev=conf_rev,
            )
            self._subscriptions[go_cb_ref] = sub
            return sub

    def remove_subscription(self, go_cb_ref: str) -> bool:
        """移除 GOOSE 订阅"""
        with self._lock:
            if go_cb_ref in self._subscriptions:
                del self._subscriptions[go_cb_ref]
                return True
            return False

    def get_subscriptions(self) -> list[dict[str, Any]]:
        """获取所有订阅信息"""
        with self._lock:
            return [sub.to_dict() for sub in self._subscriptions.values()]

    def get_subscription(self, go_cb_ref: str) -> dict[str, Any] | None:
        """获取指定订阅信息"""
        with self._lock:
            sub = self._subscriptions.get(go_cb_ref)
            return sub.to_dict() if sub else None

    def set_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """设置 GOOSE 报文接收回调"""
        self._callback = callback

    # ===== 报文处理 =====

    def _on_goose_message(self, subscriber: Any) -> None:
        """GOOSE 报文接收回调 (底层 C 回调的 Python 包装)"""
        try:
            go_cb_ref = iec61850.GooseSubscriber_getGoCbRef(subscriber) or ""

            with self._lock:
                sub = self._subscriptions.get(go_cb_ref)
                if not sub:
                    return

                # 读取报文字段
                sub.go_id = iec61850.GooseSubscriber_getGoId(subscriber) or ""
                sub.data_set_ref = iec61850.GooseSubscriber_getDataSet(subscriber) or ""
                sub.conf_rev = iec61850.GooseSubscriber_getConfRev(subscriber)
                sub.st_num = iec61850.GooseSubscriber_getStNum(subscriber)
                sub.sq_num = iec61850.GooseSubscriber_getSqNum(subscriber)
                sub.time_allowed_to_live = iec61850.GooseSubscriber_getTimeAllowedToLive(subscriber)
                sub.timestamp = iec61850.GooseSubscriber_getTimestamp(subscriber)

                # 检查有效性
                is_valid = iec61850.GooseSubscriber_isValid(subscriber)

                sub.state = GooseState.CONNECTED if is_valid else GooseState.ERROR
                sub.last_update = time.time()

                # 解析数据集值
                sub.data_values = _DataSetParser.parse(subscriber)

            # 触发上层回调
            if self._callback:
                try:
                    self._callback(sub.to_dict())
                except Exception as e:
                    log.error(f"GOOSE 回调执行失败: {e}")

        except Exception as e:
            log.error(f"GOOSE 报文处理异常: {e}")

    # ===== 生命周期 =====

    def start(self) -> bool:
        """启动 GOOSE Receiver"""
        if self._is_running:
            return True

        try:
            self._receiver = iec61850.GooseReceiver_create()
            if not self._receiver:
                raise RuntimeError("GooseReceiver_create 失败")

            iec61850.GooseReceiver_setInterfaceId(self._receiver, self._config.interface)

            # 添加所有订阅者
            with self._lock:
                for go_cb_ref, sub in self._subscriptions.items():
                    # v1.6.1.0+ dataSetValues 必须非 NULL，使用空数组
                    create_empty_array = getattr(iec61850, "MmsValue_createEmptyArray", None)
                    empty_ds = create_empty_array(0) if create_empty_array else None
                    subscriber = iec61850.GooseSubscriber_create(go_cb_ref, empty_ds)
                    if not subscriber:
                        log.warning(f"GooseSubscriber_create 失败: {go_cb_ref}")
                        continue

                    if sub.app_id is not None:
                        iec61850.GooseSubscriber_setAppId(subscriber, sub.app_id)
                    if sub.dst_mac:
                        iec61850.GooseSubscriber_setDstMac(subscriber, sub.dst_mac)

                    # 使用 SWIG director 机制设置 Python 回调
                    # (GooseSubscriber_setListener 在 pyiec61850-ng 中不可用)
                    if hasattr(iec61850, "GooseSubscriberForPython"):
                        goose_handler = _PyGooseHandler(self)
                        goose_subscriber_py = iec61850.GooseSubscriberForPython()
                        goose_subscriber_py.setLibiec61850GooseSubscriber(subscriber)
                        goose_subscriber_py.setEventHandler(goose_handler)
                        goose_subscriber_py.subscribe()
                        self._goose_handlers.append(goose_handler)
                        self._goose_subscriber_py_list.append(goose_subscriber_py)
                    else:
                        # 兼容旧版 libiec61850 绑定及轻量测试替身。
                        iec61850.GooseSubscriber_setListener(
                            subscriber, lambda sub, _parameter=None: self._on_goose_message(sub), None
                        )

                    iec61850.GooseReceiver_addSubscriber(self._receiver, subscriber)
                    self._subscriber_handles.append(subscriber)

            # 启动接收线程
            iec61850.GooseReceiver_start(self._receiver)
            self._is_running = True

            # 启动状态监控线程
            self._monitor_stop.clear()
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()

            log.info(f"GOOSE Receiver 已启动: interface={self._config.interface}, 订阅数={len(self._subscriptions)}")
            return True
        except Exception as e:
            log.error(f"GOOSE Receiver 启动失败: {e}")
            self._is_running = False
            self._subscriber_handles.clear()
            self._goose_handlers.clear()
            self._goose_subscriber_py_list.clear()
            return False

    def stop(self) -> None:
        """停止 GOOSE Receiver"""
        self._is_running = False
        self._monitor_stop.set()

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)

        # 先切断 SWIG director 链接，再销毁 C++ 对象
        for py_sub in self._goose_subscriber_py_list:
            try:
                py_sub.deleteEventHandler()
            except Exception:
                pass

        if self._receiver:
            try:
                iec61850.GooseReceiver_stop(self._receiver)
                iec61850.GooseReceiver_destroy(self._receiver)
            except Exception as e:
                log.error(f"GOOSE Receiver 停止异常: {e}")
            self._receiver = None
        self._subscriber_handles.clear()

        # 防止 SWIG 对已释放的 C++ handler 调用析构函数
        for handler in self._goose_handlers:
            if hasattr(handler, "thisown"):
                handler.thisown = 0
        self._goose_handlers.clear()
        self._goose_subscriber_py_list.clear()

        # 清理订阅状态
        with self._lock:
            for sub in self._subscriptions.values():
                sub.state = GooseState.INIT

        log.info("GOOSE Receiver 已停止")

    def _monitor_loop(self) -> None:
        """状态监控循环 - 检测超时订阅"""
        while not self._monitor_stop.is_set():
            try:
                now = time.time()
                with self._lock:
                    for sub in self._subscriptions.values():
                        if sub.last_update > 0 and sub.time_allowed_to_live > 0:
                            elapsed = (now - sub.last_update) * 1000  # ms
                            if elapsed > sub.time_allowed_to_live:
                                if sub.state != GooseState.LOST:
                                    sub.state = GooseState.LOST
                                    log.warning(f"GOOSE 订阅超时: {sub.go_cb_ref}")
            except Exception as e:
                log.error(f"GOOSE 状态监控异常: {e}")

            self._monitor_stop.wait(1.0)

    def get_status(self) -> dict[str, Any]:
        """获取 Receiver 状态"""
        return {
            "interface": self._config.interface,
            "is_running": self._is_running,
            "subscription_count": len(self._subscriptions),
            "subscriptions": self.get_subscriptions(),
        }
