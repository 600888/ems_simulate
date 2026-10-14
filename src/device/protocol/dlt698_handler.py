"""Bridge the managed dlt698 adapter into the existing Device lifecycle."""

from src.device.core.message.message_capture import MessageCapture
from src.device.protocol.base_handler import ProtocolHandler


class Dlt698Handler(ProtocolHandler):
    def __init__(self):
        super().__init__()
        self.runtime = None
        self.last_error = ""
        self.set_message_capture(MessageCapture())

    def initialize(self, config):
        self._config = dict(config)
        # Builder may run on a worker thread. Async objects are created only in start().

    def get_runtime(self):
        if self.runtime is None:
            from src.data.service.dlt698_service import Dlt698Service
            from src.proto.dlt698.runtime import Dlt698Runtime
            from src.proto.dlt698.schema import Dlt698Config

            self.runtime = Dlt698Runtime(
                Dlt698Config.model_validate(self._config["runtime"]),
                self._config,
                Dlt698Service.points(self._config["channel_id"]),
                self.message_capture,
            )
        return self.runtime

    async def start(self):
        try:
            self._is_running = await self.get_runtime().start()
            self.last_error = ""
            return self._is_running
        except Exception as error:
            self.last_error = str(error)
            self._is_running = False
            raise

    async def stop(self):
        try:
            if self.runtime:
                await self.runtime.stop()
            return True
        finally:
            self._is_running = False

    def read_value(self, point):
        raise TypeError("DL/T 698 使用有类型的异步测点接口")

    def write_value(self, point, value):
        raise TypeError("DL/T 698 写入需要明确的 OAD 和 Data 类型")

    def add_points(self, points):
        if points:
            raise TypeError("DL/T 698 测点使用独立的有类型定义")

    def clear_captured_messages(self):
        if self.message_capture:
            self.message_capture.clear()

    def get_captured_messages(self, limit=100):
        return self.message_capture.get_messages(limit)

    def status(self):
        runtime = self.get_runtime()
        client = runtime.config.role == "client"
        supported = {"points", "config", "import"}
        supported.update(
            {"get", "set", "action", "auto_read", "records", "reports", "md5", "then_get"}
            if client
            else {"get", "local_values"}
        )
        features = {
            name: {"supported": name in supported}
            for name in (
                "points",
                "config",
                "import",
                "get",
                "set",
                "action",
                "auto_read",
                "records",
                "reports",
                "md5",
                "then_get",
                "local_values",
                "proxy",
                "routes",
                "mapping",
                "history",
                "simulation",
            )
        }
        for feature in features.values():
            if not feature["supported"]:
                feature["reason"] = "当前适配器使用 dlt698 1.0 托管 API，尚未接入此扩展能力"
        return {
            "available": True,
            "state": runtime.state,
            "features": features,
            "sessions": list(runtime.sessions.values()),
            "auto_read": runtime.auto_status(),
            "security_backend": False,
            "actual_port": runtime.actual_port,
            "last_error": runtime.error or self.last_error,
        }
