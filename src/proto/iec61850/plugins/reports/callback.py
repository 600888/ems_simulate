"""报告回调处理模块

封装 C 回调注册/注销，ClientReport 解析与数据缓存。
回调在 libIEC61850 的接收线程中执行，使用 queue 异步处理避免阻塞。
"""

from collections import deque
from collections.abc import Callable
import contextlib
from dataclasses import dataclass, field
import datetime
import threading
import time
from typing import Any

from ...core.mms_value import mms_value_to_python
from ...defs.constants import HAS_IEC61850
from ...defs.types import ReportDataEntry
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


# 全局回调映射表: rcb_ref -> callback_info
# C 回调无法绑定到实例方法，需通过静态函数 + 全局字典分发
_CALLBACK_REGISTRY: dict[str, "_CallbackInfo"] = {}
_CALLBACK_LOCK = threading.Lock()
_PENDING_GI_ROUTES: dict[str, tuple[set[str], float]] = {}
# 常规报告 round-robin 分发计数器: rpt_id -> 当前索引
_ROUND_ROBIN_INDEX: dict[str, int] = {}
# 全局稳定递增 ID，用作环状缓冲区 entry_id
_ENTRY_SEQUENCE: int = 0
MAX_REPORT_VALUES_PER_ENTRY = 512


def _get_next_entry_uid() -> int:
    """获取全局唯一递增 ID，用于环状缓冲区条目标识"""
    global _ENTRY_SEQUENCE
    _ENTRY_SEQUENCE += 1
    return _ENTRY_SEQUENCE


@dataclass
class _CallbackInfo:
    """回调注册信息"""

    rcb_ref: str
    handler: Any = None  # _PyRCBHandler 实例 (保持引用防 GC)
    subscriber: Any = None  # RCBSubscriber 实例 (保持引用防 GC)
    on_report: Callable | None = None  # Python 回调函数
    data_cache: deque = field(default_factory=lambda: deque(maxlen=1000))
    max_cache: int = 1000
    enabled_at: str = ""
    mms_ref: str = ""
    rpt_id: str = ""
    dataset_members: list[str] = field(default_factory=list)  # 数据集成员引用列表，用于索引到引用的映射

    def __post_init__(self):
        """确保 data_cache 的 maxlen 与 max_cache 一致"""
        if self.data_cache.maxlen != self.max_cache:
            self.data_cache = deque(self.data_cache, maxlen=self.max_cache)


def _normalize_ref(rcb_ref: str, rcb_type: str = "") -> str:
    """Normalize an RCB ref for report handler registration.

    libIEC61850 uses dot FC form for IedConnection_installReportHandler,
    e.g. LD/LLN0.RP.EventsRCB. BRCB instances keep their 01/02 suffix so
    multiple buffered reports can subscribe independently. Indexed URCB
    instances still use the base report-handler reference when required.
    """
    if not rcb_ref or "/" not in rcb_ref:
        return rcb_ref

    ref = rcb_ref.replace("$", ".")
    if "." not in ref:
        return ref

    ln_part, name = ref.rsplit(".", 1)
    parts = ln_part.split(".")
    if len(parts) >= 2 and parts[-1] in ("BR", "RP"):
        fc = parts[-1]
        ln_only = ".".join(parts[:-1])
    else:
        ln_only = ln_part
        normalized_type = (rcb_type or "").upper()
        if normalized_type == "BRCB":
            fc = "BR"
        elif normalized_type == "URCB":
            fc = "RP"
        else:
            low = name.lower()
            fc = "RP" if (low.startswith("rp") or low.startswith("urcb")) else "BR"

    normalized_type = (rcb_type or "").upper()
    callback_name = _strip_report_instance_suffix(name) if normalized_type == "URCB" else name
    return f"{ln_only}.{fc}.{callback_name}"


def _strip_report_instance_suffix(name: str) -> str:
    """Strip RptEnabled instance suffix like 01 from report handler refs."""
    if len(name) > 2 and name[-2:].isdigit():
        return name[:-2]
    return name


def _ref_aliases(rcb_ref: str, rcb_type: str = "") -> set[str]:
    """Build equivalent cache lookup keys for one RCB reference."""
    aliases = set()
    if not rcb_ref:
        return aliases

    raw = rcb_ref.strip()
    aliases.add(raw)
    aliases.add(raw.replace("$", "."))

    dotted = raw.replace("$", ".")
    if "/" not in dotted or "." not in dotted:
        return {a for a in aliases if a}

    ln_part, name = dotted.rsplit(".", 1)
    if name in ("BR", "RP"):
        return {a for a in aliases if a}

    fc = ""
    ln_only = ln_part
    if "." in ln_part:
        maybe_ln, maybe_fc = ln_part.rsplit(".", 1)
        if maybe_fc in ("BR", "RP"):
            ln_only = maybe_ln
            fc = maybe_fc

    normalized_type = (rcb_type or "").upper()
    if not fc:
        if normalized_type == "BRCB":
            fc = "BR"
        elif normalized_type == "URCB":
            fc = "RP"
        else:
            low = name.lower()
            fc = "RP" if (low.startswith("rp") or low.startswith("urcb")) else "BR"

    aliases.add(f"{ln_only}.{name}")
    aliases.add(f"{ln_only}.{fc}.{name}")
    aliases.add(f"{ln_only}${fc}${name}")
    return {a for a in aliases if a}


def _find_registered_info(rcb_ref: str) -> tuple[str, "_CallbackInfo"] | tuple[None, None]:
    """Find callback info by exact key first, then by normalized reference aliases."""
    info = _CALLBACK_REGISTRY.get(rcb_ref)
    if info:
        return rcb_ref, info

    query_aliases = _ref_aliases(rcb_ref)
    for key, candidate in _CALLBACK_REGISTRY.items():
        candidate_aliases = _ref_aliases(key) | _ref_aliases(candidate.mms_ref)
        if query_aliases & candidate_aliases:
            return key, candidate
    return None, None


def _route_keys_for_info(rcb_ref: str, info: "_CallbackInfo") -> set[str]:
    """基于 RCB 实例引用的路由键，不包含 RptId 以避免跨实例混淆。"""
    keys = set()
    keys.update(_ref_aliases(rcb_ref))
    keys.update(_ref_aliases(info.mms_ref))
    return {key for key in keys if key}


def _expire_pending_gi_routes(now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    expired = [key for key, (_, deadline) in _PENDING_GI_ROUTES.items() if deadline <= now]
    for key in expired:
        log.debug(f"Expiring pending GI route for key={key!r}")
        _PENDING_GI_ROUTES.pop(key, None)


def _resolve_pending_gi_route(rcb_ref: str, entry: ReportDataEntry) -> tuple[set[str], bool]:
    """基于 RCB 实例引用路由 GI 报告，C++ 层按 RptId 路由时用 RptId 回查。

    libIEC61850 的 C++ 层 EventSubscriber 使用 RptId 匹配入站报告，
    同一 RptId 的所有报告会到达最先注册的 subscriber。
    因此当 ref 别名匹配失败时，用 RptId 回查 _PENDING_GI_ROUTES，
    将报告重路由到实际触发 GI 的 RCB 实例。

    Returns:
        (目标 ref 集合, 是否通过 GI 路由匹配)
    """
    now = time.monotonic()
    _expire_pending_gi_routes(now)

    targets: set[str] = set()

    # 1. 先尝试用 RCB 实例引用精确匹配
    _, current_info = _find_registered_info(rcb_ref)
    route_keys: set[str] = set()
    if current_info:
        route_keys.update(_route_keys_for_info(rcb_ref, current_info))

    for key in route_keys:
        pending = _PENDING_GI_ROUTES.get(key)
        if not pending:
            continue
        target_set, _ = pending
        for target_ref in target_set:
            matched_key, target_info = _find_registered_info(target_ref)
            if target_info:
                targets.add(matched_key or target_ref)

    # 2. 引用匹配失败时，用 RptId 回查
    if entry.rpt_id:
        pending = _PENDING_GI_ROUTES.get(entry.rpt_id)
        if pending:
            target_set, _ = pending
            for target_ref in target_set:
                matched_key, target_info = _find_registered_info(target_ref)
                if target_info:
                    targets.add(matched_key or target_ref)

    if targets:
        if len(targets) > 1 or next(iter(targets)) != rcb_ref:
            log.info(f"GI 报告重路由: from={rcb_ref}, to_count={len(targets)}, rpt_id={entry.rpt_id!r}")
        return targets, True

    return {rcb_ref}, False


class ReportCallbackHandler:
    """报告回调管理器

    管理 C 级别报告回调的注册/注销，以及报告数据的解析与缓存。
    线程安全：C 回调在 libIEC61850 的接收线程中执行，
    通过 _CALLBACK_LOCK 保护注册表和缓存。
    """

    @staticmethod
    def install(
        connection,
        rcb_ref: str,
        on_report: Callable[[ReportDataEntry], None] | None = None,
        max_cache: int = 1000,
        rpt_id: str = "",
        rcb_type: str = "",
        dataset_members: list[str] | None = None,
    ) -> bool:
        """安装报告回调

        基于 RCB 实例引用（rcb_ref）进行精确的订阅管理与回调绑定。
        每个 RCB 实例有独立唯一标识，不受 RptId 属性影响。

        Args:
            connection: Iec61850Connection 实例
            rcb_ref: RCB 引用路径
            on_report: 可选 Python 回调，收到报告时调用
            max_cache: 最大缓存条数
            rpt_id: 报告 ID (可空, 空表示接受任意)
            dataset_members: 数据集成员引用列表，用于报告数据引用映射

        Returns:
            bool 是否成功
        """
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            log.warning(f"安装报告回调失败: 连接不可用, ref={rcb_ref}")
            return False

        # 如果已注册，先注销
        # 注意：不能在锁内调用 uninstall，因为 uninstall 需要在锁外调用 C 层注销
        with _CALLBACK_LOCK:
            already_registered = rcb_ref in _CALLBACK_REGISTRY
        if already_registered:
            ReportCallbackHandler.uninstall(connection, rcb_ref)

        # 查找同 RptId 的旧订阅 — 复用而非注销
        # libIEC61850 的 EventSubscriber 在 C++ 层用 RptId 匹配 subscriber，
        # 同一 RptId 只能有一个 C++ 订阅。当多个 RCB 实例共享同一 RptId 时，
        # 复用已有 subscriber，将新 RCB 注册到 _CALLBACK_REGISTRY 由
        # _resolve_pending_gi_route 路由报告到正确缓存。
        stale_rcb_ref = None
        if rpt_id:
            with _CALLBACK_LOCK:
                for existing_ref, existing_info in list(_CALLBACK_REGISTRY.items()):
                    if existing_info.rpt_id == rpt_id and existing_ref != rcb_ref:
                        stale_rcb_ref = existing_ref
                        break

        with _CALLBACK_LOCK:
            try:
                nref = _normalize_ref(rcb_ref, rcb_type)
                log.info(f"安装报告回调: rcb_ref={rcb_ref}, mms_ref={nref}, rpt_id={rpt_id!r}, rcb_type={rcb_type}")

                if stale_rcb_ref:
                    # 同 RptId 的旧订阅仍活跃，复用其 C++ subscriber
                    # libIEC61850 的 EventSubscriber 按 RptId 匹配，
                    # 同一 RptId 只能有一个 C++ 订阅。复用旧订阅实例，
                    # 将新 RCB 注册到 _CALLBACK_REGISTRY，报告通过
                    # _resolve_pending_gi_route 按 RptId 路由到正确缓存。
                    stale_info = _CALLBACK_REGISTRY.get(stale_rcb_ref)
                    if not stale_info:
                        log.warning(f"复用旧订阅失败: 注册表中未找到 {stale_rcb_ref}")
                        return False

                    _CALLBACK_REGISTRY[rcb_ref] = _CallbackInfo(
                        rcb_ref=rcb_ref,
                        handler=stale_info.handler,
                        subscriber=stale_info.subscriber,
                        on_report=on_report,
                        max_cache=max_cache,
                        enabled_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        mms_ref=nref,
                        rpt_id=rpt_id or "",
                        dataset_members=dataset_members or [],
                    )
                    log.info(f"报告回调已复用: new={rcb_ref} (复用 {stale_rcb_ref} 的订阅), rpt_id={rpt_id!r}")
                    return True

                # 警告：RptId 为空时，部分版本的 libIEC61850 RCBSubscriber
                effective_rpt_id = rpt_id or ""
                if not effective_rpt_id:
                    log.warning(
                        f"RptId 为空，报告回调可能无法匹配服务器推送的报告！"
                        f"请检查 IED 的 RCB 配置中是否设置了 RptId。rcb_ref={rcb_ref}"
                    )

                handler = _PyRCBHandler(rcb_ref)
                subscriber = iec61850.RCBSubscriber()
                subscriber.setIedConnection(conn)
                subscriber.setRcbReference(nref)
                subscriber.setRcbRptId(effective_rpt_id)
                subscriber.setEventHandler(handler)

                log.debug(f"RCBSubscriber.subscribe() 调用: ref={nref}, rpt_id={effective_rpt_id!r}")
                subscribe_ok = subscriber.subscribe()
                if not subscribe_ok:
                    log.warning(
                        f"RCBSubscriber.subscribe() 返回失败: ref={nref}, rpt_id={effective_rpt_id!r}, "
                        f"rcb_ref={rcb_ref}"
                    )
                    with contextlib.suppress(Exception):
                        subscriber.deleteEventHandler()
                    return False

                log.info(f"RCBSubscriber.subscribe() 成功: ref={nref}, rpt_id={effective_rpt_id!r}")

                _CALLBACK_REGISTRY[rcb_ref] = _CallbackInfo(
                    rcb_ref=rcb_ref,
                    handler=handler,
                    subscriber=subscriber,
                    on_report=on_report,
                    max_cache=max_cache,
                    enabled_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    mms_ref=nref,
                    rpt_id=effective_rpt_id,
                    dataset_members=dataset_members or [],
                )
                log.info(f"报告回调已安装: {rcb_ref} (mms_ref={nref}, rpt_id={effective_rpt_id!r})")
                return True
            except Exception as e:
                log.error(f"安装报告回调异常: {rcb_ref}, {e}", exc_info=True)
                return False

    @staticmethod
    def uninstall(connection, rcb_ref: str) -> bool:
        """注销报告回调

        RCBSubscriber 没有 unsubscribe 方法，正确的注销顺序:
        1. 锁内从注册表移除，阻止 _dispatch_report 继续分发
        2. 锁外调用 subscriber.deleteEventHandler() 断开 SWIG director 链接，
           使 C++ 接收线程不再回调 Python trigger()
        3. 调用 IedConnection_uninstallReportHandler 按 rcbReference 注销 C++ 侧订阅，
           确保再次 subscribe() 时不会报 "already registered"
        4. 释放 subscriber/handler 的 Python 引用，让 GC 销毁 C++ 对象

        注意: 不能在持有 _CALLBACK_LOCK 时调用 C 层操作，
        否则与 _dispatch_report 中的锁形成死锁导致程序崩溃。
        """
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            return False

        # 1. 锁内从注册表移除，并取出 subscriber/handler 引用
        #    这样 _dispatch_report 不再分发该 RCB 的报告
        with _CALLBACK_LOCK:
            if rcb_ref not in _CALLBACK_REGISTRY:
                return True
            info = _CALLBACK_REGISTRY.pop(rcb_ref)

        subscriber = info.subscriber
        handler = info.handler
        nref = info.mms_ref or _normalize_ref(rcb_ref)

        # 2. 锁外断开 SWIG director 链接 (C++ 不再回调 Python)
        if subscriber is not None:
            try:
                subscriber.deleteEventHandler()
            except Exception as e:
                log.debug(f"deleteEventHandler 异常 (非致命): {rcb_ref}, {e}")

        # 3. 按 rcbReference 注销 C++ 侧订阅记录 (确保可重新订阅)
        try:
            iec61850.IedConnection_uninstallReportHandler(conn, nref)
        except Exception as e:
            log.debug(f"uninstallReportHandler 异常 (非致命): {rcb_ref}, {e}")

        # 4. 释放 Python 引用，让 GC 回收 C++ 对象
        info.subscriber = None
        info.handler = None

        # 防止 SWIG 在 C++ 已释放后再次调用析构 (参考 GOOSE thisown=0)
        if handler is not None and hasattr(handler, "thisown"):
            try:
                handler.thisown = 0
            except Exception:
                pass

        log.info(f"报告回调已注销: {rcb_ref}")
        return True

    @staticmethod
    def get_cache(rcb_ref: str) -> list[dict[str, Any]]:
        """获取指定 RCB 的缓存报告数据"""
        with _CALLBACK_LOCK:
            matched_key, info = _find_registered_info(rcb_ref)
            if not info:
                log.debug(f"报告缓存未命中: query={rcb_ref}, registered={list(_CALLBACK_REGISTRY.keys())}")
                return []
            if matched_key != rcb_ref:
                log.debug(f"报告缓存通过别名命中: query={rcb_ref}, matched={matched_key}")
            return [ReportCallbackHandler._entry_to_dict(entry) for entry in info.data_cache]

    @staticmethod
    def get_cache_summaries(rcb_ref: str, limit: int = 100) -> list[dict[str, Any]]:
        """获取轻量报告摘要，不复制报告值和原因字典。"""
        with _CALLBACK_LOCK:
            _, info = _find_registered_info(rcb_ref)
            if not info:
                return []

            entries = list(info.data_cache)
            start_index = max(0, len(entries) - limit) if limit > 0 else 0
            return [
                ReportCallbackHandler._entry_to_summary(entry, index)
                for index, entry in enumerate(entries[start_index:], start=start_index)
            ]

    @staticmethod
    def get_cache_entry(
        rcb_ref: str,
        *,
        uid: int | None = None,
        latest: bool = True,
    ) -> dict[str, Any] | None:
        """按 uid 获取单条报告；未指定 uid 时返回最新（或最早）一条。"""
        with _CALLBACK_LOCK:
            _, info = _find_registered_info(rcb_ref)
            if not info or not info.data_cache:
                return None

            if uid is not None:
                entry = next((item for item in info.data_cache if item.uid == uid), None)
            else:
                entry = info.data_cache[-1] if latest else info.data_cache[0]
            return ReportCallbackHandler._entry_to_dict(entry) if entry is not None else None

    @staticmethod
    def get_cache_state(rcb_ref: str) -> tuple[int, int]:
        """Return cache size and latest uid without serializing report values."""
        with _CALLBACK_LOCK:
            _, info = _find_registered_info(rcb_ref)
            if not info or not info.data_cache:
                return 0, 0
            return len(info.data_cache), info.data_cache[-1].uid

    @staticmethod
    def clear_cache(rcb_ref: str) -> None:
        """清除指定 RCB 的缓存"""
        with _CALLBACK_LOCK:
            _, info = _find_registered_info(rcb_ref)
            if info:
                info.data_cache.clear()

    @staticmethod
    def append_cache_entry(rcb_ref: str, entry: ReportDataEntry) -> bool:
        """Append one report entry to the matching RCB cache."""
        with _CALLBACK_LOCK:
            matched_key, info = _find_registered_info(rcb_ref)
            if not info:
                log.warning(f"报告缓存写入失败: RCB 未注册, ref={rcb_ref}")
                return False
            entry.uid = _get_next_entry_uid()
            info.data_cache.append(entry)
            log.info(f"报告缓存已写入: rcb_ref={matched_key}, cache_size={len(info.data_cache)}")
            return True

    @staticmethod
    def is_active(rcb_ref: str) -> bool:
        """检查指定 RCB 是否有活跃回调"""
        with _CALLBACK_LOCK:
            _, info = _find_registered_info(rcb_ref)
            return info is not None

    @staticmethod
    def mark_pending_gi(rcb_ref: str, ttl: float = 3.0) -> None:
        """记录 GI 触发目标，供 _dispatch_report 将入站报告重路由到正确的 RCB。

        libIEC61850 的 C++ 层 EventSubscriber 使用 RptId 匹配入站报告，
        同一 RptId 的所有报告会到达最先注册的 subscriber。
        因此除了用 RCB 实例引用注册外，额外用 RptId 注册，
        当报告被 C++ 路由到同 RptId 的另一个 subscriber 时仍能找回正确的实例。

        注意：同一 RptId 可能有多个 RCB 实例同时触发 GI（如批量应用），
        _PENDING_GI_ROUTES 按 key 存储目标集合，避免互相覆盖。
        """
        log_message = ""
        with _CALLBACK_LOCK:
            matched_key, info = _find_registered_info(rcb_ref)
            if not info:
                log_message = f"GI 待路由未记录: RCB 未注册, ref={rcb_ref}"
            else:
                target_ref = matched_key or rcb_ref
                deadline = time.monotonic() + ttl
                _expire_pending_gi_routes()
                for key in _route_keys_for_info(target_ref, info):
                    existing = _PENDING_GI_ROUTES.get(key)
                    if existing:
                        existing[0].add(target_ref)
                    else:
                        _PENDING_GI_ROUTES[key] = ({target_ref}, deadline)
                if info.rpt_id:
                    rpt_key = info.rpt_id
                    existing = _PENDING_GI_ROUTES.get(rpt_key)
                    if existing:
                        existing[0].add(target_ref)
                    else:
                        _PENDING_GI_ROUTES[rpt_key] = ({target_ref}, deadline)
                log_message = f"GI 待路由已记录: target={target_ref}, rpt_id={info.rpt_id!r}"
        if log_message:
            log.debug(log_message)

    @staticmethod
    def get_active_rcbs() -> list[dict[str, Any]]:
        """获取所有活跃回调信息"""
        with _CALLBACK_LOCK:
            return [
                {
                    "rcb_ref": info.rcb_ref,
                    "enabled_since": info.enabled_at,
                    "cache_size": len(info.data_cache),
                }
                for info in _CALLBACK_REGISTRY.values()
            ]

    @staticmethod
    def shutdown_all(connection) -> None:
        """关闭所有回调（插件关闭时调用）

        采用与 uninstall 相同的清理模式:
        1. 锁内清空注册表
        2. 锁外逐个 deleteEventHandler 断开 director 链 + uninstallReportHandler 注销 C++ 订阅
        3. 释放引用，防止 SWIG 重复析构
        """
        conn = connection.connection if connection else None

        # 1. 锁内取出所有 rcb_ref 并清空注册表
        with _CALLBACK_LOCK:
            refs = list(_CALLBACK_REGISTRY.keys())
            infos = [_CALLBACK_REGISTRY.pop(ref) for ref in refs]

        # 2. 锁外逐个清理
        for ref, info in zip(refs, infos, strict=True):
            subscriber = info.subscriber
            handler = info.handler
            if subscriber is not None:
                try:
                    subscriber.deleteEventHandler()
                except Exception:
                    pass
            if conn is not None:
                try:
                    iec61850.IedConnection_uninstallReportHandler(conn, info.mms_ref or _normalize_ref(ref))
                except Exception:
                    pass
            # 防止 SWIG 重复析构
            if handler is not None and hasattr(handler, "thisown"):
                try:
                    handler.thisown = 0
                except Exception:
                    pass

        # 3. 释放引用
        for info in infos:
            info.subscriber = None
            info.handler = None
        log.info("所有报告回调已关闭")

    @staticmethod
    def _entry_to_dict(entry: ReportDataEntry) -> dict[str, Any]:
        """将 ReportDataEntry 转为字典"""
        return {
            "seq_num": entry.seq_num,
            "time_stamp": entry.time_stamp,
            "reason_codes": entry.reason_codes,
            "data_values": entry.data_values,
            "entry_id": entry.entry_id.hex() if entry.entry_id else None,
            "conf_rev": entry.conf_rev,
            "data_set": entry.data_set,
            "rpt_id": entry.rpt_id,
            "received_at": entry.received_at,
            "uid": entry.uid,
        }

    @staticmethod
    def _entry_to_summary(entry: ReportDataEntry, index: int) -> dict[str, Any]:
        """将 ReportDataEntry 转为历史列表所需的轻量摘要。"""
        return {
            "entry_key": f"uid:{entry.uid}",
            "index": index,
            "seq_num": entry.seq_num,
            "time_stamp": entry.time_stamp,
            "received_at": entry.received_at,
            "data_set": entry.data_set,
            "rpt_id": entry.rpt_id,
            "conf_rev": entry.conf_rev,
            "entry_id": entry.entry_id.hex() if entry.entry_id else None,
            "value_count": len(entry.data_values),
            "uid": entry.uid,
        }


def _dispatch_report(rcb_ref: str, report) -> None:
    """解析并分发一条报告 (由 _PyRCBHandler.trigger 调用)

    注意: 不能在持有 _CALLBACK_LOCK 时做耗时的 C 层解析，
    否则 uninstall 中的 IedConnection_uninstallReportHandler 会等待
    接收线程完成，而接收线程持锁解析报告时 C 层对象可能已被销毁，
    导致段错误崩溃。
    """
    log.info(f"_dispatch_report 进入: rcb_ref={rcb_ref}, report={report}")

    # 1. 锁内快速检查是否已注册，取出 dataset_members 和 on_report 回调
    with _CALLBACK_LOCK:
        info = _CALLBACK_REGISTRY.get(rcb_ref)
        if not info:
            log.warning(
                f"_dispatch_report: rcb_ref={rcb_ref} 未在注册表中找到, "
                f"当前注册表 keys={list(_CALLBACK_REGISTRY.keys())}"
            )
            return
        on_report = info.on_report
        dataset_members = info.dataset_members

    # 2. 锁外解析报告 (耗时 C 层操作，不持锁)
    entry = _parse_client_report(report, rcb_ref, dataset_members)
    if entry is None:
        log.warning(f"_dispatch_report: 解析报告失败返回 None, rcb_ref={rcb_ref}")
        return

    log.info(
        f"_dispatch_report: 解析成功, rcb_ref={rcb_ref}, "
        f"seq_num={entry.seq_num}, data_values_count={len(entry.data_values)}"
    )

    # 3. 锁内写入缓存
    with _CALLBACK_LOCK:
        target_refs, is_gi_route = _resolve_pending_gi_route(rcb_ref, entry)

        if is_gi_route:
            # GI 报告 — 写入所有触发 GI 的目标 RCB 实例
            written = 0
            on_report = None
            if not entry.uid:
                entry.uid = _get_next_entry_uid()
            for target_ref in target_refs:
                info = _CALLBACK_REGISTRY.get(target_ref)
                if not info:
                    continue
                info.data_cache.append(entry)
                if on_report is None:
                    on_report = info.on_report
                written += 1
            if written > 0:
                log.info(f"_dispatch_report: GI 报告已写入 {written} 个 RCB 实例, rpt_id={entry.rpt_id!r}")
        else:
            # 常规报告（变化上送）：C++ 层按 RptId 路由，所有报告集中到
            # 第一个 subscriber（brcbDin01）。用 round-robin 分发到共享
            # 同一 RptId 的所有 RCB 实例，确保各实例均分报告。
            on_report = None
            instances = (
                sorted(
                    [(r, i) for r, i in _CALLBACK_REGISTRY.items() if i.rpt_id == entry.rpt_id and i.rpt_id],
                    key=lambda x: x[0],
                )
                if entry.rpt_id
                else [(rcb_ref, _CALLBACK_REGISTRY.get(rcb_ref))]
            )

            if instances:
                rpt_key = entry.rpt_id or rcb_ref
                idx = _ROUND_ROBIN_INDEX.get(rpt_key, 0) % len(instances)
                target_ref, target_info = instances[idx]
                if not entry.uid:
                    entry.uid = _get_next_entry_uid()
                target_info.data_cache.append(entry)
                on_report = target_info.on_report
                _ROUND_ROBIN_INDEX[rpt_key] = idx + 1
                log.info(
                    f"_dispatch_report: 常规报告已分发, round_robin_idx={idx}, "
                    f"rcb_ref={target_ref}, cache_size={len(target_info.data_cache)}"
                )
            else:
                log.warning(f"_dispatch_report: rcb_ref={rcb_ref} 已被注销")

    # 4. 锁外调用用户回调
    if on_report:
        try:
            on_report(entry)
        except Exception as cb_err:
            log.error(f"报告回调函数异常: {rcb_ref}, {cb_err}")


if HAS_IEC61850:

    class _PyRCBHandler(iec61850.RCBHandler):
        """SWIG director 子类, C++ 收到报告时回调 trigger()"""

        def __init__(self, rcb_ref: str):
            super().__init__()
            self._rcb_ref = rcb_ref

        def trigger(self):
            """C 接收线程回调: 在线程内完成解析"""
            log.info(f"RCBHandler.trigger 被调用: rcb_ref={self._rcb_ref}")
            try:
                cr = self._client_report
                log.info(f"RCBHandler.trigger report: rcb_ref={self._rcb_ref}, report={cr}")
                # 在 trigger 返回前完成解析 (C 层在 trigger 返回后可能释放 report)
                _dispatch_report(self._rcb_ref, cr)
            except Exception as e:
                log.error(f"RCBHandler.trigger 异常: {self._rcb_ref}, {e}", exc_info=True)
else:

    class _PyRCBHandler:  # 占位, 不会被使用
        def __init__(self, rcb_ref: str):
            self._rcb_ref = rcb_ref


def _parse_client_report(report, rcb_ref: str, dataset_members: list[str] | None = None) -> ReportDataEntry | None:
    """Parse ClientReport into a cacheable ReportDataEntry.

    Args:
        report: ClientReport 对象
        rcb_ref: RCB 引用路径
        dataset_members: 数据集成员引用列表，用于将 data[i] 映射为具体引用路径
    """
    try:
        entry = ReportDataEntry()

        try:
            rpt_id = iec61850.ClientReport_getRptId(report)
            if rpt_id:
                entry.rpt_id = str(rpt_id)
        except Exception:
            pass

        for func_name in ("ClientReport_getDataSetName", "ClientReport_getDataSet"):
            func = getattr(iec61850, func_name, None)
            if not func:
                continue
            try:
                ds = func(report)
                if ds:
                    entry.data_set = str(ds)
                    break
            except Exception:
                pass

        with contextlib.suppress(Exception):
            entry.conf_rev = int(iec61850.ClientReport_getConfRev(report))

        with contextlib.suppress(Exception):
            entry.seq_num = int(iec61850.ClientReport_getSeqNum(report))

        for func_name in ("ClientReport_getTimestamp", "ClientReport_getTimeOfEntry"):
            func = getattr(iec61850, func_name, None)
            if not func:
                continue
            try:
                time_ms = func(report)
                if time_ms and int(time_ms) > 0:
                    entry.time_stamp = datetime.datetime.fromtimestamp(int(time_ms) / 1000.0).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    break
            except Exception:
                pass

        entry.received_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        values = None
        for func_name in ("ClientReport_getDataSetValues", "ClientReport_getValues"):
            func = getattr(iec61850, func_name, None)
            if not func:
                continue
            try:
                values = func(report)
                if values:
                    break
            except Exception:
                values = None

        if values:
            array_size = 0
            with contextlib.suppress(Exception):
                array_size = int(iec61850.MmsValue_getArraySize(values))

            if array_size > MAX_REPORT_VALUES_PER_ENTRY:
                log.warning(f"Report has {array_size} values, parsing first {MAX_REPORT_VALUES_PER_ENTRY}: {rcb_ref}")
            parse_count = min(array_size, MAX_REPORT_VALUES_PER_ENTRY)

            for i in range(parse_count):
                element = None
                try:
                    element = iec61850.MmsValue_getElement(values, i)
                except Exception:
                    element = None
                if element is None:
                    continue

                # 优先使用数据引用 (DataReference) 作为键名
                data_ref = _get_data_reference(report, i)
                if data_ref:
                    ref_key = data_ref
                elif dataset_members and i < len(dataset_members):
                    # 其次使用数据集成员引用
                    ref_key = dataset_members[i]
                else:
                    # 最后回退到 data[i] 格式
                    ref_key = f"data[{i}]"

                entry.data_values[ref_key] = mms_value_to_python(element)

                # 获取正确的 reason code
                reason = _get_reason_for_inclusion(report, i)
                entry.reason_codes[ref_key] = reason

            if array_size > parse_count:
                entry.data_values["__truncated__"] = f"{array_size - parse_count} values omitted"
                entry.reason_codes["__truncated__"] = "local-limit"

        return entry
    except Exception as e:
        log.error(f"parse ClientReport failed: {rcb_ref}, {e}")
        return None


def _get_reason_for_inclusion(report, index: int) -> str:
    try:
        reason = iec61850.ClientReport_getReasonForInclusion(report, index)
        try:
            reason_text = iec61850.ReasonForInclusion_getValueAsString(reason)
            if reason_text:
                return str(reason_text)
        except Exception:
            pass
        reason_value = int(reason)
        reason_map = {
            1: "data-change",
            2: "quality-change",
            4: "data-update",
            8: "integrity",
            16: "gi",
        }
        return reason_map.get(reason_value, f"code={reason_value}")
    except Exception:
        log.error(f"get_reason_for_inclusion failed: {report}, {index}")
    return "unknown"


def _get_data_reference(report, index: int) -> str:
    try:
        ref = iec61850.ClientReport_getDataReference(report, index)
        if ref:
            return str(ref)
    except Exception:
        log.error(f"get_data_reference failed: {report}, {index}")
    return ""
