"""Bounded background persistence for connection lifecycle callbacks."""

from datetime import datetime
from queue import Empty, Full, Queue
import threading
import time

from src.data.dao.connection_session_dao import ConnectionSessionDao
from src.data.log import log

from .models import ConnectionSnapshot, ConnectionState, utc_now
from .registry import connection_registry


class ConnectionPersistenceWorker:
    def __init__(self) -> None:
        self._lifecycle: Queue[tuple[str, ConnectionSnapshot]] = Queue(maxsize=4096)
        self._activity: Queue[tuple[str, ConnectionSnapshot]] = Queue(maxsize=1024)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._history_cleared_at: dict[int, datetime] = {}
        self.dropped_events = 0
        self.failed_batches = 0
        self.written_events = 0
        self.last_write_latency_ms = 0

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            recovered = ConnectionSessionDao.reconcile_incomplete()
            if recovered:
                log.warning(f"已恢复 {recovered} 条因上次进程退出而未闭合的客户端连接")
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="connection-history-writer", daemon=True)
            self._thread.start()
            connection_registry.set_event_sink(self.enqueue)

    def enqueue(self, event: str, snapshot: ConnectionSnapshot) -> None:
        target = self._activity if event == "activity" else self._lifecycle
        try:
            target.put_nowait((event, snapshot))
        except Full:
            with self._lock:
                self.dropped_events += 1
            if event != "activity":
                log.error(f"连接历史持久化队列已满，事件未写入: {event} {snapshot.session_id}")

    def _next_event(self) -> tuple[str, ConnectionSnapshot] | None:
        try:
            return self._lifecycle.get_nowait()
        except Empty:
            pass
        try:
            return self._activity.get(timeout=0.2)
        except Empty:
            return None

    def _run(self) -> None:
        while not self._stop_event.is_set() or not self._lifecycle.empty() or not self._activity.empty():
            item = self._next_event()
            if item is None:
                continue
            batch = [item]
            while len(batch) < 64:
                try:
                    batch.append(self._lifecycle.get_nowait())
                    continue
                except Empty:
                    pass
                try:
                    batch.append(self._activity.get_nowait())
                except Empty:
                    break
            self._write_batch([snapshot for _, snapshot in batch])

    def clear_history(self, channel_id: int) -> int:
        """Serialize clearing with writes and discard delayed snapshots of deleted history."""
        with self._write_lock:
            cutoff = utc_now()
            active_ids = [snapshot.session_id for snapshot in connection_registry.current(channel_id)]
            deleted = ConnectionSessionDao.clear_history(channel_id, active_session_ids=active_ids)
            self._history_cleared_at[channel_id] = cutoff
            return deleted

    def _should_persist(self, snapshot: ConnectionSnapshot) -> bool:
        cutoff = self._history_cleared_at.get(snapshot.channel_id)
        if cutoff is None:
            return True
        if snapshot.state in (ConnectionState.CLOSED, ConnectionState.ABNORMAL):
            return (snapshot.disconnected_at or snapshot.last_activity_at) > cutoff
        return (
            snapshot.transport_connected_at > cutoff
            or connection_registry.get_current(snapshot.channel_id, snapshot.session_id) is not None
        )

    def _write_batch(self, snapshots: list[ConnectionSnapshot]) -> None:
        with self._write_lock:
            snapshots = [snapshot for snapshot in snapshots if self._should_persist(snapshot)]
            if not snapshots:
                return
            started_ns = time.monotonic_ns()
            for attempt, backoff_seconds in enumerate((0.0, 0.05, 0.2), start=1):
                if backoff_seconds:
                    self._stop_event.wait(backoff_seconds)
                try:
                    ConnectionSessionDao.save_snapshots(snapshots)
                    with self._lock:
                        self.written_events += len(snapshots)
                        self.last_write_latency_ms = max(0, (time.monotonic_ns() - started_ns) // 1_000_000)
                    break
                except Exception as exc:
                    if attempt < 3:
                        log.warning(f"连接历史批量写入失败，将重试: attempt={attempt}, error={exc}")
                        continue
                    with self._lock:
                        self.failed_batches += 1
                    session_ids = ",".join(snapshot.session_id for snapshot in snapshots[:3])
                    log.exception(
                        f"连接历史批量写入重试耗尽: count={len(snapshots)}, sessions={session_ids}, error={exc}"
                    )

    def metrics(self) -> dict[str, int]:
        with self._lock:
            return {
                "lifecycle_queue_depth": self._lifecycle.qsize(),
                "activity_queue_depth": self._activity.qsize(),
                "dropped_events": self.dropped_events,
                "failed_batches": self.failed_batches,
                "written_events": self.written_events,
                "last_write_latency_ms": self.last_write_latency_ms,
            }

    def stop(self, timeout: float = 5.0) -> None:
        connection_registry.set_event_sink(None)
        with self._lock:
            thread = self._thread
            if thread is None:
                return
            self._stop_event.set()
        thread.join(timeout=max(0.1, timeout))
        if thread.is_alive():
            log.error("连接历史持久化线程未能在限定时间内退出")
        with self._lock:
            self._thread = None


connection_persistence = ConnectionPersistenceWorker()
