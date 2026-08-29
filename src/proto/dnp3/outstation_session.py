"""Reliability features layered over the pinned pydnp3-pure OutstationSession."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import time
from typing import Any

from pydnp3_pure.app.constants import IIN1, IIN2, FunctionCode, Qualifier
from pydnp3_pure.app.fragment import ObjectData, build_response
from pydnp3_pure.app.object_header import ObjectHeader
from pydnp3_pure.objects import get_handler
from pydnp3_pure.objects.types import AnalogPoint, BinaryPoint, DNP3Timestamp
from pydnp3_pure.outstation.event_buffer import Event
from pydnp3_pure.outstation.session import OutstationSession

from src.proto.dnp3.objects import DelayValue

_DEFAULT_VARIATIONS = {1: 2, 2: 2, 10: 2, 20: 1, 21: 1, 30: 5, 32: 7, 40: 3}


@dataclass(slots=True)
class _PendingEventResponse:
    sequence: int
    unsolicited: bool
    fragment: bytes
    event_ids: frozenset[int]
    retries: int = 0
    timer: asyncio.Task[None] | None = None


def _qualifier_for_indexes(indexes: list[int]) -> Qualifier:
    """根据索引是否连续及范围大小选择合适的限定词。"""
    contiguous = indexes == list(range(indexes[0], indexes[-1] + 1))
    if contiguous:
        return Qualifier.RANGE_8_START_STOP if indexes[-1] <= 0xFF else Qualifier.RANGE_16_START_STOP
    return Qualifier.INDEX_8 if indexes[-1] <= 0xFF else Qualifier.INDEX_16


def _object_for_points(group: int, variation: int, points: list[Any]) -> ObjectData | None:
    """将一组测点组装为一个 DNP3 对象（含对象头与排序限定词）。"""
    if not points:
        return None
    points = sorted(points, key=lambda point: point.index)
    indexes = [int(point.index) for point in points]
    qualifier = _qualifier_for_indexes(indexes)
    handler = get_handler(group)
    if variation == 0 or handler is None or variation not in handler.supported_variations:
        variation = _DEFAULT_VARIATIONS[group]
    return ObjectData(
        header=ObjectHeader(
            group=group,
            variation=variation,
            qualifier=qualifier,
            start=indexes[0],
            stop=indexes[-1],
            count=len(points),
        ),
        points=points,
    )


class ReliableOutstationSession(OutstationSession):
    """Correct reads, event acknowledgement, timestamps, overflow and unsolicited data."""

    def __init__(
        self,
        *args,
        app_confirm: bool = True,
        confirm_timeout_seconds: float = 5.0,
        max_confirm_retries: int = 2,
        request_unsolicited_send=None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._app_confirm = app_confirm
        self._confirm_timeout_seconds = confirm_timeout_seconds
        self._max_confirm_retries = max_confirm_retries
        self._request_unsolicited_send = request_unsolicited_send
        self._pending_event_responses: dict[tuple[bool, int], _PendingEventResponse] = {}
        self._unsolicited_sequence = 0
        self._unsolicited_enabled = bool(self._config.enable_unsolicited)
        self._clock_offset_ms = 0

    @property
    def outstation_time_ms(self) -> int:
        """返回含时钟偏移补偿的当前 Unix 毫秒时间。"""
        return int(time.time() * 1000) + self._clock_offset_ms

    def on_message(self, message) -> None:
        """处理接收到的应用层请求，冻结类请求单独拦截处理。"""
        if message.function in {
            FunctionCode.FREEZE,
            FunctionCode.FREEZE_NO_ACK,
            FunctionCode.FREEZE_CLEAR,
            FunctionCode.FREEZE_CLEAR_NO_ACK,
            FunctionCode.FREEZE_AT_TIME,
            FunctionCode.FREEZE_AT_TIME_NO_ACK,
        }:
            self._handle_freeze_request(message)
            return
        super().on_message(message)

    def close(self) -> None:
        """关闭会话，取消所有待确认事件响应的定时器。"""
        for pending in self._pending_event_responses.values():
            if pending.timer:
                pending.timer.cancel()
        self._pending_event_responses.clear()

    def on_connection_opened(self) -> None:
        """连接建立时复位状态，并在使能未请求上报时发送空响应。"""
        self.close()
        if self._unsolicited_enabled:
            self.send_unsolicited(null_response=True)

    def _handle_read(self, message) -> None:
        """处理读请求：组装静态点、事件响应并跟踪需要确认的事件。"""
        response_objects: list[ObjectData] = []
        event_classes: set[int] = set()
        for requested in message.objects:
            header = requested.header
            if header.group == 60:
                if header.variation == 1:
                    response_objects.extend(self._read_class0())
                elif header.variation in (2, 3, 4):
                    event_classes.add(header.variation - 1)
                continue
            points = self._read_requested_points(header)
            response = _object_for_points(header.group, header.variation, points)
            if response is not None:
                response_objects.append(response)

        event_objects, event_ids = self._event_objects(event_classes)
        response_objects.extend(event_objects)
        self._update_iin_event_flags()
        sequence = message.header.control.seq
        confirm = bool(event_ids and self._app_confirm)
        fragment = build_response(
            seq=sequence,
            iin=self._iin,
            objects=response_objects,
            confirm=confirm,
        )
        self._send(fragment)
        self._track_or_remove_events(sequence, False, fragment, event_ids, confirm)

    def _handle_write(self, message) -> None:
        """处理写请求：时间同步写与内部指示（IIN）复位。"""
        for obj in message.objects:
            if obj.header.group == 50 and obj.header.variation == 1 and obj.points:
                timestamp = obj.points[0]
                if isinstance(timestamp, DNP3Timestamp):
                    self._clock_offset_ms = timestamp.ms_since_epoch - int(time.time() * 1000)
                    self._iin.iin1 &= ~IIN1.NEED_TIME
            elif obj.header.group == 80 and obj.header.variation == 1:
                for bit_index, value in obj.points:
                    if bit_index == 7 and not value:
                        self._iin.device_restart = False
        self._send(build_response(message.header.control.seq, self._iin, []))

    def _handle_delay_measure(self, message) -> None:
        """处理延时测量请求：返回处理耗时作为精细时延。"""
        started = time.monotonic()
        delay_ms = max(0, min(0xFFFF, int((time.monotonic() - started) * 1000)))
        obj = ObjectData(
            ObjectHeader(52, 2, Qualifier.COUNT_8, 0, 0, 1),
            [DelayValue(delay_ms)],
        )
        self._send(build_response(message.header.control.seq, self._iin, [obj]))

    def _handle_restart(self, message, cold: bool) -> None:
        """处理冷/热重启请求：置设备重启标志并返回延迟秒数。"""
        delay_seconds = self._handler.on_cold_restart() if cold else self._handler.on_warm_restart()
        self._iin.device_restart = True
        obj = ObjectData(
            ObjectHeader(52, 1, Qualifier.COUNT_8, 0, 0, 1),
            [DelayValue(max(0, min(0xFFFF, int(delay_seconds))))],
        )
        self._send(build_response(message.header.control.seq, self._iin, [obj]))

    def _handle_freeze_request(self, message) -> None:
        """处理冻结请求：冻结/清零计数器并视配置决定是否应答。"""
        clear = message.function in {
            FunctionCode.FREEZE_CLEAR,
            FunctionCode.FREEZE_CLEAR_NO_ACK,
        }
        no_ack = message.function in {
            FunctionCode.FREEZE_NO_ACK,
            FunctionCode.FREEZE_CLEAR_NO_ACK,
            FunctionCode.FREEZE_AT_TIME_NO_ACK,
        }
        selectors = [obj.header for obj in message.objects if obj.header.group == 20]
        if not selectors:
            selectors = [ObjectHeader(20, 0, Qualifier.ALL_POINTS, 0, 0, 0)]
        for selector in selectors:
            counters = self._db.get_counters(
                start=None if selector.qualifier == Qualifier.ALL_POINTS else selector.start,
                stop=None if selector.qualifier == Qualifier.ALL_POINTS else selector.stop,
            )
            for counter in counters:
                self._db.freeze_counter(counter.index)
                if clear:
                    self._db.update_counter(counter.index, 0, flags=counter.flags)
        self._handler.on_freeze()
        if not no_ack:
            self._send(build_response(message.header.control.seq, self._iin, []))

    def _read_requested_points(self, header: ObjectHeader) -> list[Any]:
        """按对象组读取所请求范围的测点。"""
        bounds = {} if header.qualifier == Qualifier.ALL_POINTS else {"start": header.start, "stop": header.stop}
        readers = {
            1: self._db.get_binary_inputs,
            10: self._db.get_binary_outputs,
            20: self._db.get_counters,
            21: self._db.get_frozen_counters,
            30: self._db.get_analog_inputs,
            40: self._db.get_analog_outputs,
        }
        reader = readers.get(header.group)
        return reader(**bounds) if reader is not None else []

    def _read_class0(self) -> list[ObjectData]:
        """读取全部 Class 0 静态点并按测点配置的变体组织成对象。"""
        configured = (
            (1, self._db.get_binary_inputs(), self._db._bi_config),
            (10, 2, self._db.get_binary_outputs()),
            (30, self._db.get_analog_inputs(), self._db._ai_config),
            (40, 3, self._db.get_analog_outputs()),
            (20, 1, self._db.get_counters()),
            (21, 1, self._db.get_frozen_counters()),
        )
        result: list[ObjectData] = []
        for entry in configured:
            if len(entry) == 3 and isinstance(entry[1], list):
                group, points, configs = entry
                by_variation: dict[int, list[Any]] = {}
                for point in points:
                    config = configs.get(point.index)
                    variation = config.default_variation if config else _DEFAULT_VARIATIONS[group]
                    by_variation.setdefault(variation, []).append(point)
                result.extend(
                    obj
                    for variation, selected in by_variation.items()
                    if (obj := _object_for_points(group, variation, selected))
                )
            else:
                group, variation, points = entry
                if obj := _object_for_points(group, variation, points):
                    result.append(obj)
        return result

    def _events_in_flight(self) -> set[int]:
        """返回当前正在等待确认的事件 id 集合。"""
        result: set[int] = set()
        for pending in self._pending_event_responses.values():
            result.update(pending.event_ids)
        return result

    def _event_objects(self, event_classes: set[int]) -> tuple[list[ObjectData], set[int]]:
        """取指定类的事件并组装为响应对象，返回对象列表与事件 id 集合。"""
        excluded = self._events_in_flight()
        events = [
            event
            for event_class in sorted(event_classes)
            for event in self._events.get_class_events(event_class)
            if id(event) not in excluded
        ]
        buckets: dict[tuple[int, int], list[Any]] = {}
        for event in events:
            timestamp = datetime.fromtimestamp(event.timestamp_ms / 1000, tz=UTC) if event.timestamp_ms else None
            if event.group == 30:
                group = 32
                point = AnalogPoint(event.index, event.value, event.flags, timestamp)
            elif event.group == 1:
                group = 2
                point = BinaryPoint(event.index, event.value, event.flags, timestamp)
            else:
                continue
            buckets.setdefault((group, event.variation), []).append(point)
        objects = [
            obj
            for (group, variation), points in buckets.items()
            if (obj := _object_for_points(group, variation, points))
        ]
        return objects, {id(e) for e in events}

    def _track_or_remove_events(
        self,
        sequence: int,
        unsolicited: bool,
        fragment: bytes,
        event_ids: set[int],
        confirm: bool,
    ) -> None:
        """视是否要求确认：跟踪事件等待确认，否则立即删除已发送事件。"""
        if not event_ids and not (confirm and unsolicited):
            return
        if not confirm:
            self._remove_events(event_ids)
            return
        key = (unsolicited, sequence)
        pending = _PendingEventResponse(
            sequence=sequence,
            unsolicited=unsolicited,
            fragment=fragment,
            event_ids=frozenset(event_ids),
        )
        self._pending_event_responses[key] = pending
        pending.timer = asyncio.create_task(self._confirm_timeout(key))

    async def _confirm_timeout(self, key: tuple[bool, int]) -> None:
        """在确认超时后重发待确认的事件响应直到达到重试上限。"""
        try:
            while True:
                await asyncio.sleep(self._confirm_timeout_seconds)
                pending = self._pending_event_responses.get(key)
                if pending is None:
                    return
                if pending.retries >= self._max_confirm_retries:
                    self._pending_event_responses.pop(key, None)
                    return
                pending.retries += 1
                self._send(pending.fragment)
        except asyncio.CancelledError:
            return

    def _handle_confirm(self, message) -> None:
        """处理应用层确认：删除对应事件并按需继续发送未请求上报。"""
        key = (bool(message.header.control.uns), message.header.control.seq)
        pending = self._pending_event_responses.pop(key, None)
        if pending is None:
            return
        if pending.timer:
            pending.timer.cancel()
        self._remove_events(set(pending.event_ids))
        if pending.unsolicited and self._events.has_events and self._request_unsolicited_send:
            self._request_unsolicited_send()

    def _remove_events(self, event_ids: set[int]) -> None:
        """从事件缓冲中移除已确认的事件并更新 IIN 标志。"""
        for event_class, buffer in self._events._buffers.items():
            retained = [event for event in buffer if id(event) not in event_ids]
            buffer.clear()
            buffer.extend(retained)
            if not buffer:
                self._events.confirm_class(event_class)
        if not self._events.has_events:
            self._events._overflow = False
        self._update_iin_event_flags()

    def _handle_enable_unsolicited(self, message) -> None:
        """使能未请求上报并在有事件时立即发送。"""
        self._unsolicited_enabled = True
        super()._handle_enable_unsolicited(message)
        if self._request_unsolicited_send:
            self._request_unsolicited_send()

    def _handle_disable_unsolicited(self, message) -> None:
        """禁止未请求上报。"""
        self._unsolicited_enabled = False
        super()._handle_disable_unsolicited(message)

    def send_unsolicited(self, *, null_response: bool = False) -> bool:
        """发送未请求上报：有事件或空响应模式下立即构造并发送。"""
        if not self._unsolicited_enabled:
            return False
        if any(key[0] for key in self._pending_event_responses):
            return False
        objects, event_ids = self._event_objects({1, 2, 3})
        if not null_response and not event_ids:
            return False
        sequence = self._unsolicited_sequence
        self._unsolicited_sequence = (self._unsolicited_sequence + 1) & 0x0F
        self._update_iin_event_flags()
        confirm = self._app_confirm
        fragment = build_response(
            seq=sequence,
            iin=self._iin,
            objects=objects,
            unsolicited=True,
            confirm=confirm,
        )
        self._send(fragment)
        self._track_or_remove_events(sequence, True, fragment, event_ids, confirm)
        return True

    def _on_database_event(self, group: int, index: int, point: object) -> None:
        """测点变化时生成事件并入缓冲，按配置决定是否触发未请求上报。"""
        if isinstance(point, AnalogPoint):
            config = self._db._ai_config.get(index)
        else:
            config = self._db._bi_config.get(index)
        if config is not None and not getattr(config, "event_enabled", True):
            return
        variation = getattr(config, "event_variation", 7 if isinstance(point, AnalogPoint) else 2)
        event_class = config.event_class if config else 1
        self._events.add(
            Event(
                group=group,
                variation=variation,
                index=index,
                value=point.value,
                flags=point.flags,
                event_class=event_class,
                timestamp_ms=(
                    int(time.time() * 1000) if config is None or getattr(config, "timestamp_enabled", True) else 0
                ),
            )
        )
        self._update_iin_event_flags()
        if self._unsolicited_enabled and self._request_unsolicited_send:
            self._request_unsolicited_send()

    def _update_iin_event_flags(self) -> None:
        """根据事件缓冲状态更新 IIN 中的事件与溢出标志。"""
        super()._update_iin_event_flags()
        if self._events.overflow:
            self._iin.iin2 |= IIN2.EVENT_BUFFER_OVERFLOW
        else:
            self._iin.iin2 &= ~IIN2.EVENT_BUFFER_OVERFLOW
