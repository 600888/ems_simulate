"""IEC 60870-5-101 controlling station (master)."""

from __future__ import annotations

from collections.abc import Callable
import threading
import time
from typing import Any

from src.proto.iec101.ft12 import ControlField, FT12Frame, PrimaryFunction, SecondaryFunction
from src.proto.iec101.serial_io import SerialFT12Endpoint
from src.proto.iec60870.asdu import ASDU, ASDUCodec, ASDUCodecError, InformationObject


class IEC101Master(SerialFT12Endpoint):
    """Unbalanced FT1.2 master with background class-1/class-2 polling."""

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
        poll_interval_ms: int = 200,
        balanced: bool = False,
        general_interrogation_on_connect: bool = True,
        originator_address: int = 0,
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
        self.link_addresses = list(dict.fromkeys(link_addresses or [1]))
        self.common_addresses = list(dict.fromkeys(common_addresses or self.link_addresses))
        if len(self.common_addresses) != len(self.link_addresses):
            raise ValueError("common_addresses and link_addresses must have the same length")
        self.station_links = dict(zip(self.common_addresses, self.link_addresses, strict=True))
        self.poll_interval = max(0.01, poll_interval_ms / 1000.0)
        self.balanced = balanced
        self.general_interrogation_on_connect = general_interrogation_on_connect
        self.originator_address = originator_address
        self._fcb = {address: False for address in self.link_addresses}
        self._transaction_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._poll_thread: threading.Thread | None = None
        self._on_asdu: Callable[[ASDU], None] | None = None
        self._cache: dict[tuple[int, int], InformationObject] = {}

    def set_asdu_callback(self, callback: Callable[[ASDU], None] | None) -> None:
        self._on_asdu = callback

    def start(self) -> bool:
        self.open()
        self._stop_event.clear()
        for address in self.link_addresses:
            self.reset_link(address)
        if self.general_interrogation_on_connect:
            for common_address, link_address in self.station_links.items():
                self.interrogate(common_address, link_address=link_address, wait_for_data=False)
        self._poll_thread = threading.Thread(target=self._poll_loop, name="iec101-master", daemon=True)
        self._poll_thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=max(1.0, self.response_timeout * 2))
        self._poll_thread = None
        self.close()

    def _exchange(self, raw: bytes, *, timeout: float | None = None) -> FT12Frame | None:
        with self._transaction_lock:
            self.write_frame(raw)
            frames = self.read_frames(timeout)
            if not frames:
                return None
            for _raw, frame in frames:
                self._process_received_frame(frame)
            return frames[0][1]

    def _process_received_frame(self, frame: FT12Frame) -> None:
        if not frame.user_data or frame.control is None:
            return
        try:
            asdu = self.asdu_codec.decode(frame.user_data)
        except ASDUCodecError:
            return
        self._consume_asdu(asdu)
        if (
            self.balanced
            and frame.control.primary
            and frame.control.function == PrimaryFunction.SEND_CONFIRMED_USER_DATA
        ):
            acknowledgement = ControlField(SecondaryFunction.ACK, primary=False)
            self.write_frame(self.codec.encode_fixed(acknowledgement, frame.link_address))

    def reset_link(self, link_address: int) -> bool:
        control = ControlField(PrimaryFunction.RESET_REMOTE_LINK, primary=True)
        response = self._exchange(self.codec.encode_fixed(control, link_address))
        success = bool(
            response
            and (
                response.single_char_ack
                or response.user_data
                or response.control
                and not response.control.primary
                and response.control.function == SecondaryFunction.ACK
            )
        )
        if success:
            self._fcb[link_address] = False
        return success

    def send_asdu(self, asdu: ASDU, *, link_address: int | None = None, confirmed: bool = True) -> bool:
        link_address = asdu.common_address if link_address is None else link_address
        function = PrimaryFunction.SEND_CONFIRMED_USER_DATA if confirmed else PrimaryFunction.SEND_UNCONFIRMED_USER_DATA
        fcb = self._fcb.setdefault(link_address, False)
        control = ControlField(function, primary=True, fcb_acd=fcb, fcv_dfc=confirmed)
        raw = self.codec.encode_variable(control, link_address, self.asdu_codec.encode(asdu))
        if not confirmed:
            with self._transaction_lock:
                self.write_frame(raw)
            return True
        response = self._exchange(raw)
        success = bool(response and (response.single_char_ack or response.control and response.control.function == 0))
        if success:
            self._fcb[link_address] = not fcb
        return success

    def poll(self, link_address: int, *, class_one: bool) -> ASDU | None:
        function = PrimaryFunction.REQUEST_CLASS_1 if class_one else PrimaryFunction.REQUEST_CLASS_2
        control = ControlField(function, primary=True)
        response = self._exchange(self.codec.encode_fixed(control, link_address))
        if not response or response.single_char_ack or not response.user_data:
            return None
        if not response.control or response.control.primary or response.control.function != SecondaryFunction.USER_DATA:
            return None
        try:
            return self.asdu_codec.decode(response.user_data)
        except ASDUCodecError:
            return None

    def _consume_asdu(self, asdu: ASDU) -> None:
        for obj in asdu.objects:
            self._cache[(asdu.common_address, obj.io_address)] = obj
        if self._on_asdu:
            self._on_asdu(asdu)

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            if self.balanced:
                try:
                    with self._transaction_lock:
                        for _raw, frame in self.read_frames(0.05):
                            self._process_received_frame(frame)
                except (OSError, ConnectionError):
                    pass
                self._stop_event.wait(self.poll_interval)
                continue
            for address in self.link_addresses:
                if self._stop_event.is_set():
                    break
                try:
                    self.poll(address, class_one=True)
                    self.poll(address, class_one=False)
                except (OSError, ConnectionError):
                    pass
            self._stop_event.wait(self.poll_interval)

    def interrogate(
        self,
        common_address: int,
        link_address: int | None = None,
        *,
        wait_for_data: bool = True,
    ) -> bool:
        link_address = self.station_links.get(common_address, common_address) if link_address is None else link_address
        request = ASDU(
            100,
            6,
            common_address,
            [InformationObject(0, 20)],
            originator_address=self.originator_address,
        )
        success = self.send_asdu(request, link_address=link_address)
        if success and wait_for_data and not self.balanced:
            deadline = time.monotonic() + self.response_timeout
            while time.monotonic() < deadline:
                response = self.poll(link_address, class_one=True) or self.poll(link_address, class_one=False)
                if response and response.type_id == 100 and response.cause == 10:
                    break
        return success

    def read(self, common_address: int, io_address: int, link_address: int | None = None) -> Any:
        link_address = self.station_links.get(common_address, common_address) if link_address is None else link_address
        previous = self._cache.get((common_address, io_address))
        request = ASDU(
            102,
            5,
            common_address,
            [InformationObject(io_address)],
            originator_address=self.originator_address,
        )
        if not self.send_asdu(request, link_address=link_address):
            return None
        deadline = time.monotonic() + self.response_timeout
        while time.monotonic() < deadline:
            if not self.balanced:
                self.poll(link_address, class_one=False)
            cached = self._cache.get((common_address, io_address))
            if cached is not None and cached is not previous:
                return cached.value
        return None

    def cached_value(self, common_address: int, io_address: int) -> Any:
        obj = self._cache.get((common_address, io_address))
        return None if obj is None else obj.value

    def command(
        self,
        *,
        common_address: int,
        io_address: int,
        type_id: int,
        value: Any,
        select: bool = False,
        link_address: int | None = None,
    ) -> bool:
        link_address = self.station_links.get(common_address, common_address) if link_address is None else link_address
        return self.send_asdu(
            ASDU(
                type_id,
                6,
                common_address,
                [InformationObject(io_address, value, select=select)],
                originator_address=self.originator_address,
            ),
            link_address=link_address,
        )

    def clock_sync(self, common_address: int, link_address: int | None = None) -> bool:
        link_address = self.station_links.get(common_address, common_address) if link_address is None else link_address
        return self.send_asdu(
            ASDU(
                103,
                6,
                common_address,
                [InformationObject(0, timestamp=None)],
                originator_address=self.originator_address,
            ),
            link_address=link_address,
        )
