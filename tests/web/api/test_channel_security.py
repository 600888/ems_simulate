import pytest

from src.web.api.channel.security import _validate_tls_mode
from src.web.api.exceptions import ValidationError


def test_iec61850_only_accepts_mutual_tls():
    _validate_tls_mode(4, "mutual")

    with pytest.raises(ValidationError, match="IEC 61850 TLS 仅支持双向认证"):
        _validate_tls_mode(4, "basic")


@pytest.mark.parametrize("protocol_type", [1, 2])
def test_other_tls_protocols_keep_basic_mode(protocol_type):
    _validate_tls_mode(protocol_type, "basic")
