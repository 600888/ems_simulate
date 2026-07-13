"""GOOSE Publisher Ethernet transport regression tests."""

from types import SimpleNamespace

from src.proto.iec61850.plugins.goose import publisher as publisher_module
from src.proto.iec61850.plugins.goose.publisher import GoosePublisher
from src.proto.iec61850.plugins.goose.types import GooseDataSetEntry, IecDataType, PublisherConfig


class _CommParameters:
    def __init__(self):
        self.appId = 0
        self.vlanId = 0
        self.vlanPriority = 0
        self.dstAddress = None


def test_native_create_receives_configured_ethernet_parameters(monkeypatch):
    create_calls = []
    mac_calls = []
    fake_iec61850 = SimpleNamespace(
        CommParameters=_CommParameters,
        CommParameters_setDstAddress=lambda params, *mac: mac_calls.append((params, mac)),
        GoosePublisher_create=lambda params, interface: create_calls.append((params, interface)) or object(),
    )
    monkeypatch.setattr(publisher_module, "iec61850", fake_iec61850, raising=False)
    monkeypatch.setattr(publisher_module.platform, "system", lambda: "Linux")
    publisher = GoosePublisher(PublisherConfig(interface="eth-test", app_id=0x2001, vlan_id=100, vlan_prio=6))

    publisher._create_publisher()

    params, interface = create_calls[0]
    assert interface == "eth-test"
    assert params.appId == 0x2001
    assert params.vlanId == 100
    assert params.vlanPriority == 6
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
