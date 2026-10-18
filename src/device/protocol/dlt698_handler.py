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
            self.last_error = (self.runtime.error if self.runtime else "") or str(error) or type(error).__name__
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
        return point.value

    def write_value(self, point, value):
        # Dlt698PointState.set_real_value publishes before accepting a new value.
        if self.get_runtime().config.role != "server":
            raise ValueError("DL/T 698 客户端写入请使用有类型的 SET 接口")
        return True

    def bind_points(self, device):
        from src.enums.point_data import SimulateMethod
        from src.proto.dlt698.point_state import Dlt698PointState

        runtime = self.get_runtime()
        for definition in runtime.definitions.values():
            point = Dlt698PointState(definition, runtime.publish)
            runtime.point_states[point.code] = point
            device.point_manager.add_point(1, point)
            if point.scalar and runtime.config.role == "server":
                device.simulation_controller.add_point(point, SimulateMethod.Random, 1, is_running=True)

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
        supported = {"points", "config", "import", "history"}
        if not client:
            supported.update({"mapping", "simulation"})
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
