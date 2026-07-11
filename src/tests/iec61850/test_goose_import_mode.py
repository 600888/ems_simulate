import pytest

from src.web.api.channel.import_points import _resolve_goose_import_mode
from src.web.api.exceptions import ValidationError


@pytest.mark.parametrize("mode", ["model_only", "local_publish", "remote_subscribe", "both"])
def test_explicit_goose_import_modes_are_preserved(mode):
    assert _resolve_goose_import_mode(mode, auto_create_goose=False) == mode


def test_legacy_auto_create_goose_maps_to_local_publish():
    assert _resolve_goose_import_mode("", auto_create_goose=True) == "local_publish"
    assert _resolve_goose_import_mode("", auto_create_goose=False) == "model_only"


def test_invalid_goose_import_mode_is_rejected():
    with pytest.raises(ValidationError):
        _resolve_goose_import_mode("client_means_subscriber", auto_create_goose=False)
