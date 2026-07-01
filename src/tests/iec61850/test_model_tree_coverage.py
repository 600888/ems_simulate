"""Regression tests for IEC 61850 model-backed browsing and tree data."""

from unittest.mock import Mock

from src.enums.points.base_point import BasePoint
from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.model.ied_model import DARef, DORef, IedModel, LDModel, LNModel
from src.web.api.channel.iec61850 import _build_iec61850_tree_from_model, _resolve_control_write_code


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
        {
            "name": "vendor",
            "path": "vendor",
            "fc": "DC",
            "type": "string",
            "mms_type": "MMS_UNKNOWN",
            "children": [],
        }
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


def test_tree_data_hides_quality_and_timestamp_for_control_objects():
    control_das = (
        DARef(
            name="Oper",
            path="Oper.ctlVal",
            fc="CO",
            iec_type="boolean",
            sub_das=(DARef(name="ctlVal", path="Oper.ctlVal", fc="CO", iec_type="boolean"),),
        ),
        DARef(name="q", path="q", fc="MX", iec_type="integer"),
        DARef(name="t", path="t", fc="MX", iec_type="timestamp"),
        DARef(name="dU", path="dU", fc="DC", iec_type="string"),
    )
    model = IedModel(
        lds=(
            LDModel(
                name="LD0",
                lns=(
                    LNModel(
                        name="GGIO1",
                        ref="LD0/GGIO1",
                        dos=(DORef(name="Pos", ref="LD0/GGIO1.Pos", frame_type=2, das=control_das),),
                    ),
                ),
            ),
        )
    )

    tree = _build_iec61850_tree_from_model(model, [], category="DataModel")

    assert [da["da_name"] for da in tree["items"][0]["children"]] == ["Oper", "dU"]


def test_mixed_status_control_object_registers_oper_as_control_point():
    start_conn = DORef(
        name="StartConn",
        ref="LD0/MMBS1.StartConn",
        frame_type=1,
        das=(
            DARef(name="stVal", path="stVal", fc="ST", iec_type="boolean"),
            DARef(
                name="Oper",
                path="Oper.ctlVal",
                fc="CO",
                iec_type="boolean",
                sub_das=(
                    DARef(name="Check", path="Oper.Check", fc="CO", iec_type="integer"),
                    DARef(name="ctlVal", path="Oper.ctlVal", fc="CO", iec_type="boolean"),
                ),
            ),
        ),
    )
    model = IedModel(
        lds=(
            LDModel(
                name="LD0",
                lns=(LNModel(name="MMBS1", ref="LD0/MMBS1", dos=(start_conn,)),),
            ),
        )
    )

    assert model.point_refs["LD0/MMBS1.StartConn.stVal"]["frame_type"] == 1
    oper = model.point_refs["LD0/MMBS1.StartConn.Oper.ctlVal"]
    assert oper["fc"] == "CO"
    assert oper["frame_type"] == 2
    assert "LD0/MMBS1.StartConn.Oper.Check" not in model.point_refs


def test_status_code_is_redirected_to_control_code_of_same_do():
    status = BasePoint(
        address="LD0/MMBS1.StartConn.stVal",
        code="MMBS1.StartConn.stVal",
        frame_type=1,
        fc="ST",
    )
    control = BasePoint(
        address="LD0/MMBS1.StartConn.Oper.ctlVal",
        code="MMBS1.StartConn.Oper.ctlVal",
        frame_type=2,
        fc="CO",
    )
    point_manager = Mock()
    point_manager.get_point_by_code.return_value = status
    point_manager.get_all_points.return_value = [status, control]
    device = Mock(point_manager=point_manager)

    assert _resolve_control_write_code(device, status.code) == control.code


def test_control_auxiliary_code_is_redirected_to_ctl_val():
    check = BasePoint(
        address="LD0/MMBS1.StartConn.Oper.Check",
        code="MMBS1.StartConn.Oper.Check",
        frame_type=2,
        fc="CO",
    )
    control = BasePoint(
        address="LD0/MMBS1.StartConn.Oper.ctlVal",
        code="MMBS1.StartConn.Oper.ctlVal",
        frame_type=2,
        fc="CO",
    )
    point_manager = Mock()
    point_manager.get_point_by_code.return_value = check
    point_manager.get_all_points.return_value = [check, control]
    device = Mock(point_manager=point_manager)

    assert _resolve_control_write_code(device, check.code) == control.code
