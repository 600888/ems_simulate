"""IEC 60870-5-101 controlled station (slave)."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
import threading
from typing import Any

from src.proto.iec101.ft12 import ControlField, FT12Frame, PrimaryFunction, SecondaryFunction
from src.proto.iec101.serial_io import SerialFT12Endpoint
from src.proto.iec60870.asdu import ASDU, ASDUCodec, ASDUCodecError, InformationObject


class IEC101Slave(SerialFT12Endpoint):
    def __init__(
        self,
        *,
        port: str,
        link_addresses: list[int] | None = None,
        common_addresses: list[int] | None = None,
        link_address_size: int = 1,
        cause_size: int = 2,
        common_address_size: int = 2,
        io_address_size: int = 3,
        response_timeout_ms: int = 1000,
        balanced: bool = False,
        **serial_options: Any,
    ) -> None:
        super().__init__(
            port=port,
            link_address_size=link_address_size,
            response_timeout_ms=response_timeout_ms,
            **serial_options,
        )
        self.asdu_codec = ASDUCodec(
            cause_size=cause_size,
            common_address_size=common_address_size,
            io_address_size=io_address_size,
        )
        link_address_list = list(dict.fromkeys(link_addresses or [1]))
        self.link_addresses = set(link_address_list)
        self.common_addresses = list(dict.fromkeys(common_addresses or link_address_list))
        if len(self.common_addresses) != len(link_address_list):
            raise ValueError("common_addresses and link_addresses must have the same length")
        self.station_links = dict(zip(self.common_addresses, link_address_list, strict=True))
        self.balanced = balanced
        self._class1: dict[int, deque[ASDU]] = defaultdict(deque)
        self._class2: dict[int, deque[ASDU]] = defaultdict(deque)
        self._points: dict[tuple[int, int], tuple[int, Callable[[], tuple[Any, int]]]] = {}
        self._on_command: Callable[[ASDU, InformationObject], bool] | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_fcb: dict[int, bool] = {}

    def add_point(
        self,
        common_address: int,
        io_address: int,
        type_id: int,
        provider: Callable[[], tuple[Any, int]],
    ) -> None:
        if common_address not in self.station_links:
            self.common_addresses.append(common_address)
            self.station_links[common_address] = common_address
            self.link_addresses.add(common_address)
        self._points[(common_address, io_address)] = (type_id, provider)

    def set_command_callback(self, callback: Callable[[ASDU, InformationObject], bool] | None) -> None:
        self._on_command = callback

    def start(self) -> bool:
        self.open()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._serve, name="iec101-slave", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(1.0, self.response_timeout * 2))
        self._thread = None
        self.close()

    def _serve(self) -> None:
        while not self._stop_event.is_set() and self.is_open:
            try:
                frames = self.read_frames(0.1)
                for _raw, frame in frames:
                    response = self.handle_frame(frame)
                    if response:
                        self.write_frame(response)
                if self.balanced:
                    self._flush_balanced()
            except (OSError, ConnectionError):
                if not self._stop_event.is_set():
                    self._stop_event.wait(0.05)

    def handle_frame(self, frame: FT12Frame) -> bytes | None:
        control = frame.control
        if frame.single_char_ack or control is None or not control.primary:
            return None
        address = frame.link_address
        if address not in self.link_addresses and address not in (0, 0xFF, 0xFFFF):
            return None
        if control.function in (PrimaryFunction.RESET_REMOTE_LINK, PrimaryFunction.RESET_USER_PROCESS):
            self._last_fcb.pop(address, None)
            self._class1[address].clear()
            return self.codec.encode_ack()
        if control.function == PrimaryFunction.REQUEST_LINK_STATUS:
            response_control = ControlField(SecondaryFunction.LINK_STATUS, primary=False, direction=True)
            return self.codec.encode_fixed(response_control, address)
        if control.function in (PrimaryFunction.REQUEST_CLASS_1, PrimaryFunction.REQUEST_CLASS_2):
            queue = (
                self._class1[address] if control.function == PrimaryFunction.REQUEST_CLASS_1 else self._class2[address]
            )
            if not queue:
                # E5 is a positive acknowledgement, not a valid response to a
                # class-data request.  An empty class must be reported with
                # secondary function 9; ACD still advertises pending class-1 data.
                response_control = ControlField(
                    SecondaryFunction.NO_DATA,
                    primary=False,
                    direction=True,
                    fcb_acd=bool(self._class1[address]),
                )
                return self.codec.encode_fixed(response_control, address)
            asdu = queue.popleft()
            response_control = ControlField(
                SecondaryFunction.USER_DATA,
                primary=False,
                direction=True,
                fcb_acd=bool(self._class1[address]),
            )
            return self.codec.encode_variable(response_control, address, self.asdu_codec.encode(asdu))
        if control.function in (PrimaryFunction.SEND_CONFIRMED_USER_DATA, PrimaryFunction.SEND_UNCONFIRMED_USER_DATA):
            if control.fcv_dfc and control.function == PrimaryFunction.SEND_CONFIRMED_USER_DATA:
                previous = self._last_fcb.get(address)
                if previous is not None and previous == control.fcb_acd:
                    return self._encode_link_ack(address)
                self._last_fcb[address] = control.fcb_acd
            self._handle_user_data(address, frame.user_data)
            return (
                self._encode_link_ack(address) if control.function == PrimaryFunction.SEND_CONFIRMED_USER_DATA else None
            )
        return self.codec.encode_fixed(ControlField(SecondaryFunction.NACK, primary=False, direction=True), address)

    def _encode_link_ack(self, address: int) -> bytes:
        """Use E5 only when no ACD/DFC status bits need to be reported."""
        if not self._class1[address]:
            return self.codec.encode_ack()
        control = ControlField(
            SecondaryFunction.ACK,
            primary=False,
            direction=True,
            fcb_acd=True,
        )
        return self.codec.encode_fixed(control, address)

    def _handle_user_data(self, link_address: int, data: bytes) -> None:
        try:
            asdu = self.asdu_codec.decode(data)
        except ASDUCodecError:
            return
        common_address = asdu.common_address
        if asdu.type_id == 100:
            self._class1[link_address].append(self._confirmation(asdu, cause=7))
            grouped: dict[int, list[InformationObject]] = defaultdict(list)
            for (ca, ioa), (type_id, provider) in self._points.items():
                if ca != common_address or type_id >= 45:
                    continue
                value, quality = provider()
                grouped[type_id].append(InformationObject(ioa, value, quality))
            for type_id, objects in grouped.items():
                self._queue_objects(self._class2[link_address], type_id, 20, common_address, objects)
            self._class1[link_address].append(self._confirmation(asdu, cause=10))
            return
        if asdu.type_id == 102 and asdu.objects:
            requested = asdu.objects[0].io_address
            registered = self._points.get((common_address, requested))
            if registered:
                type_id, provider = registered
                value, quality = provider()
                self._class2[link_address].append(
                    ASDU(type_id, 5, common_address, [InformationObject(requested, value, quality)])
                )
            return
        if asdu.type_id == 103:
            self._class1[link_address].append(self._confirmation(asdu, cause=7))
            return
        if 45 <= asdu.type_id <= 64:
            accepted = True
            for obj in asdu.objects:
                if self._on_command:
                    accepted = bool(self._on_command(asdu, obj)) and accepted
            confirmation = self._confirmation(asdu, cause=7)
            confirmation.negative = not accepted
            self._class1[link_address].append(confirmation)
            if accepted and not any(obj.select for obj in asdu.objects):
                self._class1[link_address].append(self._confirmation(asdu, cause=10))

    @staticmethod
    def _confirmation(request: ASDU, *, cause: int) -> ASDU:
        return ASDU(
            request.type_id,
            cause,
            request.common_address,
            list(request.objects),
            originator_address=request.originator_address,
        )

    def _queue_objects(
        self,
        queue: deque[ASDU],
        type_id: int,
        cause: int,
        common_address: int,
        objects: list[InformationObject],
    ) -> None:
        """Split a response so every ASDU still fits one FT1.2 frame."""
        maximum_user_data = 254 - self.codec.link_address_size
        batch: list[InformationObject] = []
        for obj in objects:
            candidate = ASDU(type_id, cause, common_address, [*batch, obj])
            if batch and (len(candidate.objects) > 127 or len(self.asdu_codec.encode(candidate)) > maximum_user_data):
                queue.append(ASDU(type_id, cause, common_address, batch))
                batch = [obj]
            else:
                batch.append(obj)
        if batch:
            queue.append(ASDU(type_id, cause, common_address, batch))

    def queue_spontaneous(
        self,
        *,
        common_address: int,
        io_address: int,
        type_id: int,
        value: Any,
        quality: int = 0,
        link_address: int | None = None,
    ) -> None:
        link_address = self.station_links.get(common_address, common_address) if link_address is None else link_address
        self._class1[link_address].append(
            ASDU(type_id, 3, common_address, [InformationObject(io_address, value, quality)])
        )

    def _flush_balanced(self) -> None:
        """Transmit queued ASDUs directly when both stations are link peers."""
        for address in tuple(self.link_addresses):
            for queue in (self._class1[address], self._class2[address]):
                while queue:
                    asdu = queue.popleft()
                    control = ControlField(
                        PrimaryFunction.SEND_UNCONFIRMED_USER_DATA,
                        primary=True,
                        direction=True,
                    )
                    self.write_frame(self.codec.encode_variable(control, address, self.asdu_codec.encode(asdu)))
