"""Regression tests for IEC 61850 model-backed browsing and tree data."""

from unittest.mock import Mock

from src.enums.points.base_point import BasePoint
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


def test_tree_data_from_model_restores_du_from_discovered_point_name():
    model = IedModel(
        lds=(
            LDModel(
                name="LD0",
                lns=(
                    LNModel(
                        name="MMXU1",
                        ref="LD0/MMXU1",
                        dos=(
                            DORef(
                                name="TotW",
                                ref="LD0/MMXU1.TotW",
                                frame_type=0,
                                das=(
                                    DARef(name="mag", path="mag.f", fc="MX", iec_type="float"),
                                    DARef(name="dU", path="dU", fc="DC", iec_type="string"),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
    )
    point = BasePoint(
        address="LD0/MMXU1.TotW.mag.f",
        name="总有功功率",
        code="MMXU1.TotW.mag.f",
        frame_type=0,
        fc="MX",
    )

    tree = _build_iec61850_tree_from_model(model, [point], category="DataModel")

    item = tree["items"][0]
    du = next(child for child in item["children"] if child["da_name"] == "dU")
    assert item["du_name"] == "总有功功率"
    assert du["point_name"] == "总有功功率"
    assert du["value"] == "总有功功率"


def test_tree_data_from_model_does_not_treat_generated_point_name_as_du():
    model = IedModel(
        lds=(
            LDModel(
                name="LD0",
                lns=(
                    LNModel(
                        name="MMXU1",
                        ref="LD0/MMXU1",
                        dos=(
                            DORef(
                                name="TotW",
                                ref="LD0/MMXU1.TotW",
                                frame_type=0,
                                das=(DARef(name="dU", path="dU", fc="DC", iec_type="string"),),
                            ),
                        ),
                    ),
                ),
            ),
        )
    )
    generated_name = "MMXU1.TotW.mag.f"
    point = BasePoint(
        address="LD0/MMXU1.TotW.mag.f",
        name=generated_name,
        code=generated_name,
        frame_type=0,
        fc="MX",
    )

    tree = _build_iec61850_tree_from_model(model, [point], category="DataModel")

    assert tree["items"][0]["du_name"] == ""
