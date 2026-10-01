"""Per-server SDK extension points for real sessions and service summaries."""

from datetime import UTC, datetime
import time

from asyncua.server.internal_server import InternalServer
from asyncua.server.internal_session import InternalSession

from src.proto.opcua.core.diagnostics import observed


class ObservedSession(InternalSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.diagnostics = self.iserver.diagnostics
        self._record = None
        self._opened = time.monotonic()

    async def create_session(self, params, sockname=None):
        try:
            result = await super().create_session(params, sockname)
        except Exception as exc:
            self.diagnostics.sessions.append(
                {
                    "state": "rejected",
                    "reason": type(exc).__name__,
                    "application_uri": params.ClientDescription.ApplicationUri,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            raise
        self._record = {
            "session_id": self.session_id.to_string(),
            "name": self.name,
            "state": "created",
            "application_uri": params.ClientDescription.ApplicationUri,
            "timestamp": datetime.now(UTC).isoformat(),
            "address": None,
            "bytes_sent": None,
            "bytes_received": None,
        }
        self.diagnostics.sessions.append(self._record)
        return result

    def activate_session(self, params, peer_certificate):
        try:
            result = super().activate_session(params, peer_certificate)
        except Exception as exc:
            if self._record:
                self._record.update(state="rejected", reason=type(exc).__name__)
            raise
        if self._record:
            self._record.update(state="active", username=self.user.name, role=self.user.role.name)
        return result

    async def close_session(self, delete_subs=True):
        try:
            return await super().close_session(delete_subs)
        finally:
            if self._record:
                self._record.update(
                    state="closed",
                    closed_at=datetime.now(UTC).isoformat(),
                    duration_s=round(time.monotonic() - self._opened, 3),
                )

    @observed("Read")
    async def read(self, params):
        return await super().read(params)

    @observed("Write")
    async def write(self, params):
        return await super().write(params)

    @observed("Browse")
    async def browse(self, params):
        return await super().browse(params)

    @observed("HistoryRead")
    async def history_read(self, params):
        return await super().history_read(params)


class ObservedInternalServer(InternalServer):
    def __init__(self, diagnostics, user_manager=None):
        super().__init__(user_manager=user_manager)
        self.diagnostics = diagnostics

    def create_session(self, name, user=None, external=False):
        if not external:
            return (
                super().create_session(name, external=external)
                if user is None
                else super().create_session(name, user=user, external=external)
            )
        kwargs = {} if user is None else {"user": user}
        return ObservedSession(self, self.aspace, self.subscription_service, name, external=external, **kwargs)
