"""GOOSE Publisher Ethernet transport regression tests."""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from src.proto.iec61850.plugins.goose import publisher as publisher_module
from src.proto.iec61850.plugins.goose.publisher import GoosePublisher
from src.proto.iec61850.plugins.goose.types import GooseDataSetEntry, IecDataType, PublisherConfig


class _CommParameters:
    def __init__(self):
        self.appId = 0
        self.vlanId = 0
        self.vlanPriority = 0
        self.dstAddress = None


def test_entry_update_time_changes_only_when_its_value_changes(monkeypatch):
    monkeypatch.setattr(
        publisher_module, "time", SimpleNamespace(time=Mock(side_effect=[1000.123, 2000.456, 3000.789]))
    )
    publisher = GoosePublisher(PublisherConfig(interface="eth-test"))
    publisher.add_entry(GooseDataSetEntry("stVal", False))
    publisher.add_entry(GooseDataSetEntry("other", True))

    assert publisher.get_entries()[0]["last_update"] == 1000.123
    assert publisher.update_entry(0, False) is False
    assert publisher.get_entries()[0]["last_update"] == 1000.123
    assert publisher.update_entry(0, True) is True
    assert [entry["last_update"] for entry in publisher.get_entries()] == [3000.789, 2000.456]
    publisher.remove_entry(0)
    assert publisher.get_entries()[0]["last_update"] == 2000.456


@pytest.mark.parametrize(("vlan_id", "vlan_prio"), [(0, 0), (0, 4), (100, 6), (4094, 7)])
def test_native_create_receives_configured_ethernet_parameters(monkeypatch, vlan_id, vlan_prio):
    create_calls = []
    mac_calls = []
    fake_iec61850 = SimpleNamespace(
        CommParameters=_CommParameters,
        CommParameters_setDstAddress=lambda params, *mac: mac_calls.append((params, mac)),
        GoosePublisher_create=lambda params, interface: create_calls.append((params, interface)) or object(),
    )
    monkeypatch.setattr(publisher_module, "iec61850", fake_iec61850, raising=False)
    monkeypatch.setattr(publisher_module.platform, "system", lambda: "Linux")
    publisher = GoosePublisher(
        PublisherConfig(interface="eth-test", app_id=0x2001, vlan_id=vlan_id, vlan_prio=vlan_prio)
    )

    publisher._create_publisher()

    params, interface = create_calls[0]
    assert interface == "eth-test"
    assert params.appId == 0x2001
    assert params.vlanId == vlan_id
    assert params.vlanPriority == vlan_prio
    assert mac_calls == [(params, (0x01, 0x0C, 0xCD, 0x01, 0x20, 0x01))]


def test_start_fails_when_first_real_publish_fails(monkeypatch):
    publisher = GoosePublisher(PublisherConfig(interface="eth-test"))
    monkeypatch.setattr(publisher, "_create_publisher", lambda: setattr(publisher, "_publisher", object()))
    monkeypatch.setattr(publisher, "publish", lambda: False)
    destroyed = []
    monkeypatch.setattr(publisher, "_destroy_publisher", lambda: destroyed.append(True))

    assert publisher.start() is False
    assert publisher.is_running is False
    assert destroyed == [True]


def test_windows_npcap_payload_is_valid_goose(monkeypatch):
    from src.proto.iec61850.plugins.goose.capture import GooseCaptureEngine

    publisher = GoosePublisher(
        PublisherConfig(
            go_cb_ref="TESTLD/LLN0$GO$gocb1",
            go_id="gocb1",
            data_set_ref="TESTLD/LLN0$ds1",
            app_id=0x2001,
            simulation=False,
        )
    )
    publisher.add_entry(GooseDataSetEntry("stVal", True, IecDataType.BOOLEAN))
    payload = publisher._build_goose_payload()
    ethernet_frame = bytes.fromhex("010ccd012001 020304050607 88b8") + payload

    capture = GooseCaptureEngine(interface="test")
    capture._process_packet(ethernet_frame)

    packets = capture.get_packets()
    assert len(packets) == 1
    assert packets[0]["app_id"] == 0x2001
    assert packets[0]["go_cb_ref"] == "TESTLD/LLN0$GO$gocb1"
    assert packets[0]["data_set_ref"] == "TESTLD/LLN0$ds1"
    assert packets[0]["data_values"][0]["type"] == "boolean"
    assert packets[0]["data_values"][0]["value"] is True
    assert packets[0]["data_values"][0]["raw_value"] == "83 01 FF"


def test_npcap_payload_keeps_event_time_until_data_changes(monkeypatch):
    from src.proto.iec61850.plugins.goose.capture import GooseCaptureEngine

    clock = Mock(return_value=1000.125)
    monkeypatch.setattr(publisher_module, "time", SimpleNamespace(time=clock, monotonic=lambda: 0))
    publisher = GoosePublisher(PublisherConfig(go_cb_ref="TESTLD/LLN0$GO$gocb1"))
    publisher.add_entry(GooseDataSetEntry("stVal", False))
    capture = GooseCaptureEngine(interface="test")
    ethernet_header = bytes.fromhex("010ccd010001 020304050607 88b8")

    def send():
        capture._process_packet(ethernet_header + publisher._build_goose_payload())
        return True

    monkeypatch.setattr(publisher_module.platform, "system", lambda: "Windows")
    monkeypatch.setitem(sys.modules, "scapy.all", SimpleNamespace(sendp=Mock()))
    monkeypatch.setattr(publisher, "_publish_with_npcap", send)
    monkeypatch.setattr(publisher_module, "threading", SimpleNamespace(Thread=Mock()))

    clock.return_value = 2000.250
    assert publisher.start()
    clock.return_value = 3000.375
    assert not publisher.update_entry(0, False)
    assert publisher.publish()
    clock.return_value = 4000.500
    assert publisher.update_entry(0, True)
    clock.return_value = 5000.625
    assert publisher.publish()
    publisher.stop()
    clock.return_value = 6000.750
    assert publisher.start()
    publisher.stop()

    packets = capture.get_packets()
    assert [(p["st_num"], p["sq_num"], p["send_timestamp"]) for p in packets] == [
        (1, 0, 2000.250),
        (1, 1, 2000.250),
        (2, 0, 4000.500),
        (2, 1, 4000.500),
        (3, 0, 6000.750),
    ]
    assert packets[-1]["event_timestamp"] == 6000.750


def test_bitstring_round_trips_through_native_and_npcap_encoders():
    from pyiec61850 import pyiec61850 as iec61850

    from src.device.core.message.parsers.goose import parse_goose
    from src.proto.iec61850.plugins.goose.subscriber import _DataSetParser

    publisher = GoosePublisher(PublisherConfig(go_cb_ref="TESTLD/LLN0$GO$gocb1"))
    publisher.add_entry(GooseDataSetEntry("q", 5, IecDataType.BITSTRING))
    ethernet_header = bytes.fromhex("010ccd010001 020304050607 88b8")
    assert publisher.update_entry(0, "2")
    native = publisher._entry_to_mms_value(publisher._entries[0])
    try:
        assert iec61850.MmsValue_getBitStringBit(native, 2)
        assert _DataSetParser._parse_element(native, 0)["value"] == 2
    finally:
        iec61850.MmsValue_delete(native)
    packet = parse_goose(ethernet_header + publisher._build_goose_payload())
    assert packet["objects"][0]["raw_value"] == "84 02 04 20"
    assert packet["objects"][0]["value"] == 2


def test_native_publisher_refreshes_event_time_once_even_if_send_fails(monkeypatch):
    native = object()
    binding = SimpleNamespace(
        GoosePublisher_create=Mock(return_value=native),
        GoosePublisher_increaseStNum=Mock(),
        GoosePublisher_setStNum=Mock(),
        GoosePublisher_setSqNum=Mock(),
        GoosePublisher_setTimeAllowedToLive=Mock(),
        GoosePublisher_publish=Mock(side_effect=[0, 0, -1, 0, 0]),
        LinkedList_create=Mock(return_value=object()),
        LinkedList_add=Mock(),
        LinkedList_destroyDeep=Mock(),
        MmsValue_newBoolean=Mock(),
        MmsValue_delete=Mock(),
    )
    monkeypatch.setattr(publisher_module, "iec61850", binding, raising=False)
    monkeypatch.setattr(publisher_module.platform, "system", lambda: "Linux")
    publisher = GoosePublisher(PublisherConfig())
    publisher.add_entry(GooseDataSetEntry("stVal", False))
    monkeypatch.setattr(publisher, "_create_comm_parameters", lambda: None)
    publisher._create_publisher()
    publisher._is_running = True

    assert publisher.publish()
    assert not publisher.update_entry(0, False)
    assert publisher.publish()
    binding.GoosePublisher_increaseStNum.assert_not_called()
    assert publisher.update_entry(0, True)
    binding.GoosePublisher_increaseStNum.assert_called_once_with(native)
    assert publisher.publish()
    assert publisher.publish()

    binding.GoosePublisher_increaseStNum.assert_called_once_with(native)
    assert [call.args[1] for call in binding.GoosePublisher_setSqNum.call_args_list] == [0, 0, 1, 0, 0, 1]
    assert binding.GoosePublisher_setStNum.call_args.args == (native, 2)


@pytest.mark.parametrize(("vlan_id", "vlan_prio"), [(0, 0), (0, 4), (100, 6), (4094, 7)])
@pytest.mark.parametrize("interface", ["以太网 2", r"\Device\NPF_{12345678-1234-1234-1234-123456789ABC}"])
def test_npcap_sends_linux_compatible_vlan_header_and_subscription_receives_it(
    monkeypatch, vlan_id, vlan_prio, interface
):
    import scapy.config as scapy_config

    # Serialize real Scapy layers without enumerating or opening host adapters.
    monkeypatch.setattr(scapy_config, "_set_conf_sockets", Mock())
    from scapy.layers.l2 import Dot1Q, Ether
    from scapy.packet import Raw

    from src.proto.iec61850.plugins.goose.capture import GooseCaptureEngine
    from src.proto.iec61850.plugins.goose.subscriber import GooseReceiver
    from src.proto.iec61850.plugins.goose.types import ReceiverConfig

    sent = []
    send = Mock(side_effect=lambda frame, **kwargs: sent.append(bytes(frame)))
    scapy = ModuleType("scapy.all")
    scapy.Ether = Ether
    scapy.Dot1Q = Dot1Q
    scapy.Raw = Raw
    scapy.sendp = send
    scapy.get_if_hwaddr = Mock(return_value="02:03:04:05:06:07")
    # An unspecified source must not fall back to the default route's adapter.
    monkeypatch.setattr(Ether, "route", Mock(side_effect=AssertionError("Default adapter used for source MAC")))
    monkeypatch.setitem(sys.modules, "scapy.all", scapy)
    ref = "TESTLD/LLN0$GO$gocb1"
    publisher = GoosePublisher(
        PublisherConfig(
            interface=interface,
            go_cb_ref=ref,
            data_set_ref="TESTLD/LLN0$ds1",
            app_id=0x2001,
            vlan_id=vlan_id,
            vlan_prio=vlan_prio,
        )
    )
    publisher.add_entry(GooseDataSetEntry("stVal", True, IecDataType.BOOLEAN))

    assert publisher._publish_with_npcap()
    scapy.get_if_hwaddr.assert_called_once_with(interface)
    send.assert_called_once()
    assert send.call_args.kwargs == {"iface": interface, "count": 1, "verbose": False}
    raw = sent[0]
    assert raw[0:6] == bytes(publisher.dst_mac)
    assert raw[6:12] == bytes.fromhex("020304050607")
    # Match the Linux native publisher: TPID, PCP/DEI/VID, then GOOSE EtherType.
    assert raw[12:18] == b"\x81\x00" + ((vlan_prio << 13) | vlan_id).to_bytes(2, "big") + b"\x88\xb8"
    assert raw[18:20] == b"\x20\x01"
    assert int.from_bytes(raw[20:22], "big") == len(raw) - 18

    receiver = GooseReceiver(ReceiverConfig(interface="eth-test"))
    receiver.add_subscription(ref, app_id=0x2001, dst_mac=publisher.dst_mac)
    capture = GooseCaptureEngine(interface="eth-test")
    capture.set_callback(receiver._on_captured_packet)
    capture._process_packet(raw)

    packet = capture.get_packets()[0]
    assert packet["has_vlan"] is True
    assert packet["vlan_id"] == vlan_id
    assert packet["vlan_prio"] == vlan_prio
    subscription = receiver.get_subscription(ref)
    assert subscription["state"] == "connected"
    assert subscription["message_count"] == 1
    assert subscription["data_values"][0]["value"] is True


@pytest.mark.parametrize("mac", [None, "", "00:00:00:00:00:00"])
def test_npcap_does_not_send_when_selected_adapter_has_no_mac(monkeypatch, mac):
    scapy = ModuleType("scapy.all")
    scapy.Ether = Mock()
    scapy.Dot1Q = Mock()
    scapy.Raw = Mock()
    scapy.sendp = Mock()
    scapy.get_if_hwaddr = Mock(return_value=mac)
    monkeypatch.setitem(sys.modules, "scapy.all", scapy)
    publisher = GoosePublisher(PublisherConfig(interface="以太网 2"))

    assert publisher._publish_with_npcap() is False
    scapy.get_if_hwaddr.assert_called_once_with("以太网 2")
    scapy.sendp.assert_not_called()


def test_npcap_does_not_send_when_selected_adapter_cannot_be_resolved(monkeypatch):
    scapy = ModuleType("scapy.all")
    scapy.Ether = Mock()
    scapy.Dot1Q = Mock()
    scapy.Raw = Mock()
    scapy.sendp = Mock()
    scapy.get_if_hwaddr = Mock(side_effect=ValueError("Interface not found"))
    monkeypatch.setitem(sys.modules, "scapy.all", scapy)
    publisher = GoosePublisher(PublisherConfig(interface="missing-adapter"))

    assert publisher._publish_with_npcap() is False
    scapy.get_if_hwaddr.assert_called_once_with("missing-adapter")
    scapy.sendp.assert_not_called()
