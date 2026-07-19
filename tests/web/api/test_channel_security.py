import pytest

from src.web.api.channel.security import _validate_tls_mode
from src.web.api.exceptions import ValidationError


def test_iec61850_accepts_basic_and_mutual_tls():
    _validate_tls_mode(4, "basic")
    _validate_tls_mode(4, "mutual")


@pytest.mark.parametrize("protocol_type", [1, 2])
def test_other_tls_protocols_keep_basic_mode(protocol_type):
    _validate_tls_mode(protocol_type, "basic")
