import pytest

from src.web.api.channel.security import _tls_material_requirements, _validate_tls_mode
from src.web.api.exceptions import ValidationError


def test_iec61850_accepts_one_way_and_mutual_tls():
    _validate_tls_mode(4, "one_way")
    _validate_tls_mode(4, "mutual")


@pytest.mark.parametrize("protocol_type", [1, 2])
def test_other_tls_protocols_accept_one_way_mode(protocol_type):
    _validate_tls_mode(protocol_type, "one_way")


def test_removed_basic_mode_is_rejected():
    with pytest.raises(ValidationError, match="单向认证"):
        _validate_tls_mode(1, "basic")


@pytest.mark.parametrize(
    ("conn_type", "tls_mode", "expected"),
    [
        (1, "one_way", (False, True)),
        (2, "one_way", (True, False)),
        (1, "mutual", (True, True)),
        (2, "mutual", (True, True)),
    ],
)
def test_tls_material_requirements_follow_endpoint_role(conn_type, tls_mode, expected):
    assert _tls_material_requirements(conn_type, tls_mode) == expected
