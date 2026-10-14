"""Application adapter over dlt698's managed asyncio API; no protocol engine here."""

import asyncio
from collections import deque
from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from dlt698 import (
    AsyncClient,
    AsyncServer,
    ClientOptions,
    Device,
    DeviceOptions,
    ServerOptions,
    SessionOptions,
    model,
    protocol,
    standard,
    transport,
)
from dlt698.errors import Dlt698Error
from dlt698.protocol.link import ServerAddress
from dlt698.session import Role
from src.device.auto_read import AutoReadConfig, AutoReadTaskManager, CycleResult
from src.enums.points.change_tracker import ChangeSource, track_change
from src.proto.dlt698.catalog import default_data, layout
from src.proto.dlt698.codec import address_text, from_native, oad, omd, to_native
from src.proto.dlt698.schema import TYPE_NAMES, Data, Dlt698Config, Operation, RecordQuery


def now():
    return datetime.now(UTC).isoformat()


def record_query(query: RecordQuery, config: Dlt698Config):
    oi, columns, device_layout = int(query.oad[:4], 16), [oad(value) for value in query.columns], layout(config)
    if query.selector in ("at", "between"):
        start = model.DateTimeS(value=to_native(Data(type="DateTimeS", value=query.start)).value)
        if query.selector == "at":
            request = standard.record_at(oi, start, columns, device_layout)
        else:
            end = model.DateTimeS(value=to_native(Data(type="DateTimeS", value=query.end)).value)
            request = standard.record_between(oi, start, end, columns, device_layout)
    elif query.selector == "sequences":
        request = standard.record_sequences(oi, int(query.start), int(query.end), columns, device_layout)
    else:
        selector = model.SelectAll() if query.selector == "all" else model.Selector9(previous=query.latest)
        request = standard.make_record_query(oi, selector, columns, device_layout)
    request.attribute = oad(query.oad)
    return request


def record_result(result):
    columns = [{"oad": address_text(column), "name": address_text(column)} for column in result.columns]
    value = result.result
    # Managed API returns an assembled result without a wire block count.
    return {
        "columns": columns,
        "rows": [] if isinstance(value, int) else [[from_native(cell) for cell in row] for row in value],
        "blocks": None,
        **({"dar": value} if isinstance(value, int) else {}),
    }


class Dlt698Runtime:
    """Compose the library client/server with EMS snapshots and its existing poll scheduler."""

    def __init__(self, config: Dlt698Config, network: dict, points=(), capture=None):
        self.config, self.network, self.capture = config, network, capture
        self.definitions = {point["code"]: deepcopy(point) for point in points}
        self.snapshots, self.sessions = {}, {}
        self.reports = deque(maxlen=500)
        self.client: AsyncClient | None = None
        self.server: AsyncServer | None = None
        self.device: Device | None = None
        self.state, self.error = "stopped", ""
        self.auto_read = AutoReadTaskManager(self._read_cycle)
        self.auto_codes = []
        self.point_states = {}
        self.value_lock = RLock()

    def publish(self, address, data, index=0):
        """Shared manual, mapping and simulation writes keep typed validation."""
        if self.config.role != "server":
            raise ValueError("只有服务端可以发布本地值")
        with self.value_lock:
            matches = [point for point in self.definitions.values() if point["oad"] == address]
            if not matches:
                raise ValueError("本地发布 OAD 未配置")
            data = Data.model_validate(data)
            if any(point["data_type"] != data.type for point in matches):
                raise ValueError("发布 Data 类型必须与测点定义一致")
            if self.device is None:
                self.device = self._make_device()
            attr, value = oad(address), to_native(data)
            (self.device.set_element if attr.index else self.device.set)(attr, value)
            result = self.result(index, address, value)
            # Updating a whole array also updates its independently configured elements.
            for point in self.definitions.values():
                if point["oad"][:6] == address[:6]:
                    current = self.device.get(oad(point["oad"]))
                    if isinstance(current, int):
                        continue
                    typed = from_native(current)
                    point["initial_value"] = typed
                    self.snapshots[point["code"]] = {
                        "last_good": typed,
                        "last_good_at": now(),
                        "result": self.result(index, point["oad"], current),
                    }
                    if point["code"] in self.point_states:
                        self.point_states[point["code"]].accept(typed)
            return result

    @property
    def running(self):
        return self.client is not None or self.server is not None

    @property
    def actual_port(self):
        return self.server.local_port if self.server else None

    def options(self):
        c = self.config
        options = SessionOptions(
            role=getattr(Role, c.role),
            request_timeout=c.request_timeout_ms / 1000,
            server=ServerAddress(bytes=bytes.fromhex(c.server_address), logical=c.logical_address),
            client_address=c.client_address,
            heartbeat_seconds=c.heartbeat_interval_s,
            preset_association=c.association == "preestablished",
        )
        parameters = options.parameters
        for key, value in {
            "version": c.protocol_version,
            "send_frame_bytes": c.send_frame_max,
            "receive_frame_bytes": c.receive_frame_max,
            "receive_window": c.receive_window,
            "apdu_bytes": c.apdu_max,
            "timeout_seconds": c.association_timeout_s,
        }.items():
            setattr(parameters, key, value)
        options.parameters = parameters
        return options

    def _serial(self):
        parity = self.network.get("parity", "E").upper()
        if parity not in ("N", "E", "O") or self.network.get("stopbits", 1) not in (1, 2):
            raise ValueError("串口仅支持 N/E/O 校验及 1/2 停止位")
        return transport.SerialOptions(
            baud_rate=self.network.get("baudrate", 9600),
            data_bits=self.network.get("databits", 8),
            parity=getattr(transport.SerialParity, {"N": "none", "E": "even", "O": "odd"}[parity]),
            stop_bits=transport.SerialStopBits.two
            if self.network.get("stopbits", 1) == 2
            else transport.SerialStopBits.one,
        )

    def _make_device(self):
        from dlt698.service import AttributeSchema, ObjectSchema

        device = Device(DeviceOptions(layout=layout(self.config)))
        custom = {}
        for point in self.definitions.values():
            attr = oad(point["oad"])
            if point["writable"]:
                raise ValueError("dlt698 1.0 托管服务端只发布只读属性，远端可写属性需专家服务接口")
            if not standard.find_object(attr.oi):
                kind = model.DataType.array if attr.index else getattr(model.DataType, TYPE_NAMES[point["data_type"]])
                custom.setdefault(attr.oi, {})[attr.attribute] = AttributeSchema(
                    number=attr.attribute, type=kind, readable=True
                )
        for oi, attributes in custom.items():
            device.define(ObjectSchema(oi=oi, attributes=list(attributes.values())))
        # Publish complete attributes before independently configured array elements.
        points = sorted(self.definitions.values(), key=lambda point: int(point["oad"][6:], 16))
        for point in points:
            attr, value = oad(point["oad"]), to_native(point["initial_value"])
            if attr.index:
                whole = model.Oad(oi=attr.oi, attribute=attr.attribute)
                if isinstance(device.get(whole), int):
                    definition = standard.find_attribute(attr)
                    if definition is None:
                        raise ValueError("自定义数组元素需要先配置完整数组属性")
                    count = 0
                    for index in range(1, 256):
                        try:
                            standard.validate_oad(
                                model.Oad(oi=attr.oi, attribute=attr.attribute, index=index), layout(self.config)
                            )
                            count = index
                        except (ValueError, Dlt698Error):
                            break
                    device.set(whole, default_data(definition.type, count, definition.element_type))
                device.set_element(attr, value)
            else:
                device.set(attr, value)
        return device

    async def start(self):
        from dlt698 import ConnectionProfile

        if self.running:
            return True
        conn = self.network["conn_type"]
        if (self.config.role == "client" and conn not in (0, 1)) or (
            self.config.role == "server" and conn not in (2, 3)
        ):
            raise ValueError("托管 API 支持 TCP/串口主站客户端与 TCP/串口从站服务端；反向拨号需专家接口")
        profile = (
            ConnectionProfile.local_preset
            if self.config.association == "preestablished"
            else ConnectionProfile.remote_public
        )
        self.state, self.error = "associating", ""
        try:
            if self.config.role == "client":
                timeout = self.config.request_timeout_ms / 1000
                self.client = AsyncClient(
                    ClientOptions(protocol=self.options(), transport_timeout=timeout, login_timeout=timeout),
                    on_event=self._event,
                )
                if conn == 0:
                    await self.client.open_serial_configured(
                        self.network["serial_port"], self._serial(), transport.SerialLinkOptions(), profile
                    )
                else:
                    await self.client.connect_tcp(self.network["ip"], self.network["port"], profile)
                self.sessions["1"] = {"id": "1", "address": self.config.server_address, "associated": True}
                self.state = "associated"
            else:
                self.device = self.device or self._make_device()
                self.server = AsyncServer(
                    self.device,
                    ServerOptions(protocol=self.options(), heartbeat_seconds=self.config.heartbeat_interval_s),
                    on_event=self._event,
                )
                if conn == 3:
                    await self.server.start_serial_configured(
                        self.network["serial_port"], self._serial(), transport.SerialLinkOptions(), profile
                    )
                else:
                    await self.server.start_tcp(self.network.get("ip") or "0.0.0.0", self.network["port"], profile)
                self.state = "listening"
            return True
        except BaseException as error:
            await self.stop()
            self.error = str(error)
            raise

    async def stop(self):
        await self.auto_read.shutdown()
        client, server = self.client, self.server
        self.client = self.server = None
        try:
            if client:
                await client.aclose()
            if server:
                await server.aclose()
        finally:
            self.state = "stopped"
            self.sessions.clear()
        return True

    def _event(self, completion):
        event = getattr(completion, "traffic", None) or completion
        if getattr(event, "kind", "") in ("send", "receive") and self.capture:
            callback = self.capture.add_tx if event.kind == "send" else self.capture.add_rx
            callback(event.bytes, {"protocol": "DL/T 698", "session_id": str(event.connection)})
        if getattr(completion, "kind", "") == "closed":
            self.sessions.clear()
            self.state = "lost"
        if getattr(completion, "kind", "") == "report" and completion.message:
            message = completion.message
            report = {
                "id": uuid4().hex,
                "time": now(),
                "session_id": "1",
                "kind": "normal",
                "piid_acd": str(message.piid_acd),
                "acknowledgement": "协议库自动确认",
            }
            if isinstance(message.payload, list):
                report["items"] = [
                    {
                        "oad": address_text(value.attribute),
                        **(
                            {"dar": value.result}
                            if isinstance(value.result, int)
                            else {"data": from_native(value.result)}
                        ),
                    }
                    for value in message.payload
                ]
            elif hasattr(message.payload, "columns"):
                report.update(kind="record", record=record_result(message.payload))
            self.reports.appendleft(report)

    def require_client(self):
        if self.client is None or not self.sessions:
            raise ConnectionError("请先连接 DL/T 698 客户端")
        return self.client

    async def _request(self, operation):
        self.state = "requesting"
        try:
            result = await operation
            self.state, self.error = "associated", ""
            return result
        except asyncio.CancelledError:
            self.state = "cancelled"
            self.sessions.clear()
            raise
        except Dlt698Error as error:
            self.state = "timeout" if isinstance(error, TimeoutError) else "lost"
            self.error = str(error)
            raise

    def result(self, index, text, value):
        result = {"index": index, "oad": text, "updated_at": now()}
        if isinstance(value, int):
            return {**result, "kind": "dar", "dar": value}
        data = from_native(value)
        if standard.find_attribute(oad(text)):
            try:
                standard.validate_value(oad(text), value, layout(self.config))
            except (ValueError, Dlt698Error) as error:
                return {**result, "kind": "validation_error", "data": data, "message": str(error)}
        return {**result, "kind": "data", "data": data}

    async def read(self, addresses, codes=None):
        results = []
        async with self.auto_read.read_lock:
            for index, text in enumerate(addresses):
                try:
                    if self.config.role == "server":
                        with self.value_lock:
                            if self.device is None:
                                self.device = self._make_device()
                            value = self.device.get(oad(text))
                    else:
                        response = await self._request(self.require_client().get(oad(text)))
                        value = response.data if response.data is not None else response.dar
                    result = self.result(index, text, value)
                except (Dlt698Error, ConnectionError, ValueError, TypeError) as error:
                    result = {"index": index, "oad": text, "kind": "transport_error", "message": str(error)}
                results.append(result)
                if codes:
                    snapshot = self.snapshots.setdefault(codes[index], {})
                    snapshot["result"] = result
                    if result["kind"] == "data":
                        snapshot.update(last_good=result["data"], last_good_at=result["updated_at"])
                        state = self.point_states.get(codes[index])
                        if state is not None:
                            with track_change(ChangeSource.CLIENT_READ, "DL/T 698 GET", self.network.get("ip", "")):
                                state.accept(result["data"])
        return results

    async def probe(self, addresses):
        async with self.auto_read.read_lock:
            points = await self._request(self.require_client().probe_points([oad(text) for text in addresses]))
            results = []
            for index, point in enumerate(points):
                value = point.outcome
                if isinstance(value, (int, model.Data)):
                    result = self.result(index, addresses[index], value)
                    if point.validation_error:
                        result.update(kind="validation_error", message=str(point.validation_error))
                else:
                    result = {"index": index, "oad": addresses[index], "kind": "transport_error", "message": str(value)}
                results.append(result)
            return results

    async def _read_cycle(self, config, stop, progress):
        results = []
        for code in self.auto_codes:
            if stop.is_set():
                break
            results.extend(await self.read([self.definitions[code]["oad"]], [code]))
            success = sum(item["kind"] == "data" for item in results)
            progress(len(results), len(self.auto_codes), success, len(results) - success)
        success = sum(item["kind"] == "data" for item in results)
        return CycleResult(success=success, fail=len(results) - success, total=len(results))

    async def set_auto(self, running, interval_ms=1000, codes=()):
        if running:
            self.require_client()
            if not codes or any(code not in self.definitions for code in codes):
                raise ValueError("请选择有效测点")
            if self.auto_read.is_running():
                raise ValueError("请先停止当前自动读取任务")
            self.auto_codes = list(codes)
            await self.auto_read.start(AutoReadConfig(cycle_interval_ms=interval_ms))
        else:
            await self.auto_read.shutdown()
        return self.auto_status()

    def auto_status(self):
        config = self.auto_read.current_config()
        return {
            "running": self.auto_read.is_running(),
            "interval_ms": config.cycle_interval_ms if config else 1000,
            "codes": list(self.auto_codes),
        }

    async def query_records(self, query):
        async with self.auto_read.read_lock:
            return record_result(
                await self._request(self.require_client().get_record(record_query(query, self.config)))
            )

    async def operate(self, operation: Operation):
        if operation.session_id not in (None, "", "1"):
            raise ValueError("托管客户端只有会话 1")
        if not operation.items:
            raise ValueError("操作项不能为空")
        if operation.service == "local_values":
            if self.config.role != "server":
                raise ValueError("只有服务端可以发布本地值")
            if self.device is None:
                self.device = self._make_device()
            results = []
            for index, item in enumerate(operation.items):
                if not item.oad or item.data is None:
                    raise ValueError("本地发布需要 OAD 和 Data")
                if not any(point["oad"] == item.oad for point in self.definitions.values()):
                    raise ValueError("本地发布 OAD 未配置")
                with track_change(ChangeSource.MANUAL, "DL/T 698 本地赋值"):
                    results.append(self.publish(item.oad, item.data, index))
            return results
        async with self.auto_read.read_lock:
            client = self.require_client()
            results = []
            for index, item in enumerate(operation.items):
                text = item.oad or item.omd
                if operation.service in ("set", "action", "then_get") and item.data is None:
                    raise ValueError("操作需要 Data 参数")
                if operation.service == "set":
                    value = await self._request(client.set(oad(item.oad), to_native(item.data)))
                    result = self.result(index, text, value)
                elif operation.service == "action":
                    value = await self._request(client.action(omd(item.omd), to_native(item.data)))
                    result = self.result(index, text, value.dar)
                    if value.data is not None:
                        result["data"] = from_native(value.data)
                elif operation.service == "md5":
                    value = (
                        await self._request(client.exchange(protocol.GetMd5Request(attribute=oad(item.oad))))
                    ).message.result
                    result = (
                        self.result(index, text, value)
                        if isinstance(value, int)
                        else {"index": index, "oad": text, "kind": "data", "md5": value.hex().upper()}
                    )
                elif operation.service == "then_get":
                    read = oad(item.get_oad)
                    if operation.options.get("operation", "set") == "set":
                        request = protocol.SetThenGetRequest(
                            items=[
                                protocol.SetThenGet(
                                    set=protocol.SetAttribute(attribute=oad(item.oad), value=to_native(item.data)),
                                    read=read,
                                    delay_seconds=item.delay_s,
                                )
                            ]
                        )
                        value = (await self._request(client.exchange(request))).message.items[0]
                        dar = value.set.dar
                    else:
                        request = protocol.ActionThenGetRequest(
                            items=[
                                protocol.ActionThenGet(
                                    action=protocol.ActionMethod(method=omd(item.omd), parameter=to_native(item.data)),
                                    read=read,
                                    delay_seconds=item.delay_s,
                                )
                            ]
                        )
                        value = (await self._request(client.exchange(request))).message.items[0]
                        dar = value.action.dar
                    result = {
                        "index": index,
                        "oad": text,
                        "kind": "data",
                        "children": [self.result(0, text, dar), self.result(1, item.get_oad, value.read.result)],
                    }
                else:
                    raise ValueError("该服务需要 dlt698 专家 API，当前托管适配器未启用")
                results.append(result)
            return results
