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
