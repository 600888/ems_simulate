import pytest

from src.common.mac_address import format_mac_address, normalize_mac_address
from src.proto.iec61850.plugins.goose.subscriber import GooseReceiver
from src.proto.iec61850.plugins.goose.types import GooseSubscriptionInfo, ReceiverConfig


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("01:0C:CD:01:10:04", [1, 12, 205, 1, 16, 4]),
        ("01-0c-cd-01-10-04", [1, 12, 205, 1, 16, 4]),
        ('"01:0C:CD:01:10:04"', [1, 12, 205, 1, 16, 4]),
        ("[1, 12, 205, 1, 16, 4]", [1, 12, 205, 1, 16, 4]),
        (["01", "0C", "CD", "01", "10", "04"], [1, 12, 205, 1, 16, 4]),
    ],
)
def test_normalize_mac_address_accepts_historical_formats(source, expected):
    assert normalize_mac_address(source) == expected
    assert format_mac_address(source) == "01:0C:CD:01:10:04"


def test_subscription_info_normalizes_mac_before_serialization():
    subscription = GooseSubscriptionInfo(
        go_cb_ref="LD0/LLN0$GO$gcb1",
        dst_mac="01:0C:CD:01:10:04",  # type: ignore[arg-type]
    )

    assert subscription.dst_mac == [1, 12, 205, 1, 16, 4]
    assert subscription.to_dict()["dst_mac"] == "01:0C:CD:01:10:04"


def test_receiver_status_with_historical_string_mac_does_not_fail():
    receiver = GooseReceiver(ReceiverConfig(interface="eth0"))
    receiver.add_subscription(
        "LD0/LLN0$GO$gcb1",
        dst_mac="01:0C:CD:01:10:04",  # type: ignore[arg-type]
    )

    status = receiver.get_status()

    assert status["subscriptions"][0]["dst_mac"] == "01:0C:CD:01:10:04"


def test_invalid_mac_is_rejected_at_configuration_boundary():
    with pytest.raises(ValueError, match="6 个字节"):
        normalize_mac_address("01:0C:CD")
