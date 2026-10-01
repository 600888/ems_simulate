"""Bounded summaries of actual service calls, with no credentials or values."""

from collections import deque
from datetime import UTC, datetime
from functools import wraps
import time


class CallLog:
    def __init__(self):
        self.calls = deque(maxlen=1000)
        self.sessions = deque(maxlen=100)
        self.started_at = None

    def record(self, service, started, status="Good", node_id=None, session_id=None):
        self.calls.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "service": service,
                "duration_ms": round((time.monotonic() - started) * 1000, 3),
                "status_code": str(status)[:256],
                "node_id": str(node_id)[:512] if node_id else None,
                "session_id": session_id,
            }
        )

    def snapshot(self):
        return {
            "calls": list(self.calls),
            "sessions": list(self.sessions),
            "started_at": self.started_at,
            "bytes_sent": None,
            "bytes_received": None,
        }


def observed(service):
    def decorate(method):
        @wraps(method)
        async def invoke(self, *args, **kwargs):
            started = time.monotonic()
            status = "Good"
            try:
                result = await method(self, *args, **kwargs)
                if isinstance(result, dict):
                    status = result.get("status_code", "Good")
                elif isinstance(result, list):
                    for item in result:
                        code = getattr(item, "StatusCode", item)
                        if hasattr(code, "is_bad") and code.is_bad():
                            status = code.name
                            break
                return result
            except Exception as exc:
                status = type(exc).__name__
                raise
            finally:
                session = getattr(self, "session_id", None)
                self.diagnostics.record(
                    service,
                    started,
                    status,
                    args[0] if args and isinstance(args[0], str) else None,
                    session.to_string() if session else None,
                )

        return invoke

    return decorate
