"""Instance-scoped asyncua socket hooks for the shared connection monitor."""

from collections.abc import Callable
import socket
from uuid import uuid4

from asyncua import Server, ua
from asyncua.crypto import uacrypto
from asyncua.server.binary_server_asyncio import BinaryServer, OPCUAProtocol

ConnectionObserver = Callable[..., None]


class _ObservedTransport:
    def __init__(self, transport, protocol):
        self._transport = transport
        self._protocol = protocol

    def __getattr__(self, name):
        return getattr(self._transport, name)

    def write(self, data):
        self._transport.write(data)
        self._protocol.emit("activity", tx_bytes=len(data), tx_messages=1)


class ObservedProtocol(OPCUAProtocol):
    def __init__(self, *args, observer: ConnectionObserver, **kwargs):
        super().__init__(*args, **kwargs)
        self.observer = observer
        self.connection_key = uuid4().hex
        self.close_reason = "remote_closed"
        self.close_detail = None
        self._connection_info = None

    def emit(self, event, **data):
        self.observer(event, self.connection_key, **data)

    def connection_made(self, transport):
        self.emit(
            "opened",
            remote_endpoint=transport.get_extra_info("peername"),
            local_endpoint=transport.get_extra_info("sockname"),
        )
        super().connection_made(transport)
        if self.processor is None:
            self.close_reason = "max_connections_rejected"
            return
        self.processor._transport = _ObservedTransport(transport, self)
        send_response = self.processor.send_response

        def observed_response(requesthandle, seqhdr, response, msgtype=ua.MessageType.SecureMessage):
            status = response.ResponseHeader.ServiceResult
            if status.is_bad():
                self.emit("activity", errors=1)
                if status.name in {"BadUserAccessDenied", "BadIdentityTokenInvalid", "BadIdentityTokenRejected"}:
                    session = self.processor.session
                    if session is None or not session.is_activated():
                        self.close_reason = "authentication_failed"
                        self.close_detail = status.name
            return send_response(requesthandle, seqhdr, response, msgtype)

        self.processor.send_response = observed_response

    def data_received(self, data):
        self.emit("activity", rx_bytes=len(data))
        super().data_received(data)
        if self.transport is not None and self.transport.is_closing() and self.close_reason == "remote_closed":
            self.close_reason = "protocol_error"
            self.emit("activity", errors=1)

    async def _activation_watchdog(self):
        await super()._activation_watchdog()
        if self.transport is not None and self.transport.is_closing() and self.close_reason == "remote_closed":
            self.close_reason = "idle_timeout"

    async def _process_one_msg(self, header, buf):
        self.emit("activity", rx_messages=1)
        try:
            await super()._process_one_msg(header, buf)
        except Exception as exc:
            self.close_reason = "protocol_error"
            # Store the status type only; SDK exception text may contain client data.
            self.close_detail = type(exc).__name__
            self.emit("activity", errors=1)
            raise
        if self.processor is None:
            return
        policy = self.processor._connection.security_policy
        mode = policy.Mode.name.replace("None_", "None")
        security = {
            "tls": False,
            "encrypted": mode == "SignAndEncrypt",
            "mode": mode,
            "policy_uri": policy.URI,
            "cipher": policy.URI.rsplit("#", 1)[-1],
        }
        identity = {}
        session = self.processor.session
        if session is not None:
            identity = {"ua_session_id": session.session_id.to_string()}
            record = getattr(session, "_record", None)
            if record:
                identity.update(application_uri=record["application_uri"])
                identity.update({name: record[name] for name in ("username", "role") if name in record})
            if session.is_activated():
                identity.update(username=session.user.name, role=session.user.role.name)
        info = (security, identity)
        if info != self._connection_info:
            self._connection_info = info
            self.emit("updated", security=security, client_identity=identity)

    def connection_lost(self, exc):
        if exc is not None and self.close_reason == "remote_closed":
            self.close_reason = "network_reset"
            self.close_detail = type(exc).__name__
            self.emit("activity", errors=1)
        self.emit("closed", reason=self.close_reason, detail=self.close_detail)
        super().connection_lost(exc)


class ObservedBinaryServer(BinaryServer):
    def __init__(self, *args, observer: ConnectionObserver, **kwargs):
        super().__init__(*args, **kwargs)
        self.observer = observer

    def _make_protocol(self):
        return ObservedProtocol(
            self.iserver, self._policies, self.clients, self.closing_tasks, self.limits, observer=self.observer
        )

    async def stop(self):
        for client in self.clients:
            client.close_reason = "server_stopped"
        await super().stop()


class ObservedServer(Server):
    def __init__(self, *args, observer: ConnectionObserver, **kwargs):
        super().__init__(*args, **kwargs)
        self.observer = observer

    async def start(self):
        # asyncua 2.0.1 constructs BinaryServer directly in Server.start; keep its
        # startup order while using a per-instance factory (no SDK global patch).
        if self.iserver.certificate is not None:
            uacrypto.check_certificate(self.iserver.certificate, self._application_uri, socket.gethostname())
        await self._setup_server_nodes()
        await self.iserver.start()
        try:
            host, port = self._get_bind_socket_info()
            self.bserver = ObservedBinaryServer(self.iserver, host, port, self.limits, observer=self.observer)
            self.bserver.set_policies(self._policies)
            await self.bserver.start()
        except BaseException:
            await self.iserver.stop()
            raise
