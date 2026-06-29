"""Regression tests for IEC 61850 model-backed browsing and tree data."""

from unittest.mock import Mock

from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.model.ied_model import DARef, DORef, IedModel, LDModel, LNModel
from src.web.api.channel.iec61850 import _build_iec61850_tree_from_model


def test_client_browse_children_prefers_cached_model():
    model = IedModel(
        lds=(
            LDModel(
                name="LD0",
                lns=(
                    LNModel(
                        name="LLN0",
                        ref="LD0/LLN0",
                        dos=(
                            DORef(
                                name="NamPlt",
                                ref="LD0/LLN0.NamPlt",
                                frame_type=-1,
                                das=(DARef(name="vendor", path="vendor", fc="DC", iec_type="string"),),
                            ),
                        ),
                    ),
                ),
            ),
        )
    )
    client = IEC61850Client.__new__(IEC61850Client)
    client._discovery = Mock(model=model)
    client._conn = Mock()

    assert client.browse_logical_devices() == ["LD0"]
    assert client.browse_logical_nodes("LD0") == ["LLN0"]
    assert client.browse_data_objects("LD0", "LLN0") == [{"name": "NamPlt", "frame_type": -1}]
    assert client.browse_data_attributes("LD0", "LLN0", "NamPlt") == [
        {"name": "vendor", "path": "vendor", "fc": "DC", "type": "string", "children": []}
    ]
    client._conn.browse_logical_devices.assert_not_called()


def test_tree_data_from_model_keeps_non_point_model_nodes():
    model = IedModel(
        lds=(
            LDModel(
                name="LD0",
                lns=(
                    LNModel(
                        name="LLN0",
                        ref="LD0/LLN0",
                        dos=(
                            DORef(
                                name="NamPlt",
                                ref="LD0/LLN0.NamPlt",
                                frame_type=-1,
                                das=(DARef(name="vendor", path="vendor", fc="DC", iec_type="string"),),
                            ),
                        ),
                    ),
                ),
            ),
        )
    )

    tree = _build_iec61850_tree_from_model(
        model,
        [],
        category="DataModel",
        item="LD0/LLN0",
        point_types=[0, 1, 2, 3],
        include_unknown=True,
    )

    assert tree["total"] == 1
    assert tree["items"][0]["do_ref"] == "LD0/LLN0.NamPlt"
    assert tree["items"][0]["children"][0]["da_path"] == "vendor"
