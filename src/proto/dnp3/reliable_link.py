"""DNP3 link confirmation state machine layered over the pinned framing library."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from pydnp3_pure.link.constants import BROADCAST_ALL, BROADCAST_CONFIRM, BROADCAST_NO_CONFIRM
from pydnp3_pure.link.frame import LinkFrame

ACK = 0
NACK = 1
RESET_LINK_STATES = 0
CONFIRMED_USER_DATA = 3
UNCONFIRMED_USER_DATA = 4
REQUEST_LINK_STATUS = 9
LINK_STATUS = 11

_BROADCASTS = {BROADCAST_NO_CONFIRM, BROADCAST_CONFIRM, BROADCAST_ALL}


@dataclass(slots=True)
class _QueuedFrame:
    frame: LinkFrame
    retries: int = 0


class ReliableLinkEndpoint:
    """Serialize confirmed frames and process FCB/FCV, ACK/NACK and link status."""

    def __init__(
        self,
        *,
        enabled: bool,
        local_is_master: bool,
        write_frame: Callable[[LinkFrame], None],
        deliver_frame: Callable[[LinkFrame], None],
        timeout_seconds: float = 1.0,
        max_retries: int = 2,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.enabled = enabled
        self._local_is_master = local_is_master
        self._write_frame = write_frame
        self._deliver_frame = deliver_frame
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._on_error = on_error
        self._queue: deque[_QueuedFrame] = deque()
        self._timer: asyncio.Task[None] | None = None
        self._tx_fcb = False
        self._expected_rx_fcb = False

    def reset(self) -> None:
        """复位链路确认状态机：清空队列、取消定时器并复位 FCB。"""
        if self._timer:
            self._timer.cancel()
        self._timer = None
        self._queue.clear()
        self._tx_fcb = False
        self._expected_rx_fcb = False

    def send(self, frame: LinkFrame) -> None:
        """发送链路帧：启用确认时转为确认帧入队等待应答。"""
        if (
            not self.enabled
            or not frame.header.primary
            or frame.header.function != UNCONFIRMED_USER_DATA
            or frame.header.destination in _BROADCASTS
        ):
            self._write_frame(frame)
            return
        confirmed = LinkFrame.create(
            destination=frame.header.destination,
            source=frame.header.source,
            primary=True,
            function=CONFIRMED_USER_DATA,
            user_data=frame.user_data,
            direction=frame.header.direction,
            fcb=self._tx_fcb,
            fcv=True,
        )
        self._queue.append(_QueuedFrame(confirmed))
        if len(self._queue) == 1:
            self._transmit_head()

    def request_link_status(self, destination: int, source: int) -> None:
        """发送请求链路状态（REQUEST_LINK_STATUS）帧。"""
        self._write_frame(
            LinkFrame.create(
                destination,
                source,
                True,
                REQUEST_LINK_STATUS,
                direction=self._local_is_master,
            )
        )

    def reset_remote_link(self, destination: int, source: int) -> None:
        """重置对端链路状态（RESET_LINK_STATES）帧。"""
        self._write_frame(
            LinkFrame.create(
                destination,
                source,
                True,
                RESET_LINK_STATES,
                direction=self._local_is_master,
            )
        )

    def on_frame(self, frame: LinkFrame) -> None:
        """处理接收到的链路帧：应答确认、重试或向传输层投递数据。"""
        header = frame.header
        if not header.primary:
            if header.function == ACK:
                self._acknowledge()
            elif header.function == NACK:
                self._retry_head("NACK")
            return

        if header.function == RESET_LINK_STATES:
            self._expected_rx_fcb = False
            self._send_secondary(frame, ACK)
            return
        if header.function == REQUEST_LINK_STATUS:
            self._send_secondary(frame, LINK_STATUS)
            return
        if header.function == CONFIRMED_USER_DATA:
            self._send_secondary(frame, ACK)
            if not header.fcv or header.fcb != self._expected_rx_fcb:
                return
            self._expected_rx_fcb = not self._expected_rx_fcb
            self._deliver_frame(frame)
            return
        self._deliver_frame(frame)

    def _send_secondary(self, received: LinkFrame, function: int) -> None:
        """构造并发送从站方向的应答链路帧。"""
        self._write_frame(
            LinkFrame.create(
                destination=received.header.source,
                source=received.header.destination,
                primary=False,
                function=function,
                direction=self._local_is_master,
            )
        )

    def _transmit_head(self) -> None:
        """发送队首确认帧并启动等待应答的超时定时器。"""
        if not self._queue:
            return
        self._write_frame(self._queue[0].frame)
        if self._timer:
            self._timer.cancel()
        self._timer = asyncio.create_task(self._wait_for_ack())

    async def _wait_for_ack(self) -> None:
        """等待确认超时后触发队首重试。"""
        try:
            await asyncio.sleep(self._timeout_seconds)
            self._retry_head("timeout")
        except asyncio.CancelledError:
            return

    def _acknowledge(self) -> None:
        """处理收到 ACK：出队队首帧、翻转 FCB 并发送下一帧。"""
        if not self._queue:
            return
        if self._timer:
            self._timer.cancel()
            self._timer = None
        self._queue.popleft()
        self._tx_fcb = not self._tx_fcb
        if self._queue:
            queued = self._queue[0]
            queued.frame.header.fcb = self._tx_fcb
            self._transmit_head()

    def _retry_head(self, reason: str) -> None:
        """重发队首帧；超过重试上限则放弃并在有队尾时继续发送。"""
        if not self._queue:
            return
        queued = self._queue[0]
        if queued.retries >= self._max_retries:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            self._queue.popleft()
            if self._on_error:
                self._on_error(f"DNP3链路确认失败: {reason}")
            if self._queue:
                self._transmit_head()
            return
        queued.retries += 1
        self._transmit_head()
