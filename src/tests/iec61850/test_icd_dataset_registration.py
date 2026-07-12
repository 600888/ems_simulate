"""ICD 导入时的 DataSet 注册回归测试。"""

from types import SimpleNamespace

from src.proto.iec61850.plugins.datasets import server as dataset_server_module
from src.proto.iec61850.plugins.scl.transformer.goose_transformer import GseControlInfo
from src.web.api.channel.import_points import _collect_dataset_configs


def test_collects_gse_referenced_dataset_when_not_pure():
    goose_data = {
        "pure_datasets": [],
        "publishers": [
            {
                "data_set_ref": "PIGO/LLN0$dsGOOSE1",
                "entries": [{"name": "PIGO/dcGGIO1.AnIn1.mag.f", "fc": "MX"}],
            }
        ],
    }

    datasets = _collect_dataset_configs(goose_data)

    assert datasets == [
        {
            "ld_inst": "PIGO",
            "ds_name": "dsGOOSE1",
            "ds_ref": "PIGO/LLN0$dsGOOSE1",
            "data_set_ref": "PIGO/LLN0$dsGOOSE1",
            "member_count": 1,
            "entries": [{"name": "PIGO/dcGGIO1.AnIn1.mag.f", "fc": "MX"}],
        }
    ]


def test_publisher_prefers_communication_app_id_and_mac_address():
    info = GseControlInfo(
        name="gocb1",
        ld_inst="PCS001PIGO",
        app_id="PCS001PIGO/LLN0$GO$gocb1",
        gse_app_id="2001",
        mac_address="01-0C-CD-01-20-01",
    )

    publisher = info.to_publisher_dict()

    assert publisher["name"] == "gocb1"
    assert publisher["ld_inst"] == "PCS001PIGO"
    assert publisher["app_id"] == 0x2001
    assert publisher["dst_mac"] == [0x01, 0x0C, 0xCD, 0x01, 0x20, 0x01]


def test_goose_control_reuses_pre_registered_dataset(monkeypatch):
    dataset_create_calls = []
    fake_iec61850 = SimpleNamespace(
        DataSet_create=lambda *args: dataset_create_calls.append(args),
        GSEControlBlock_create=lambda *_args: object(),
    )
    monkeypatch.setattr(dataset_server_module, "iec61850", fake_iec61850, raising=False)

    builder = SimpleNamespace(
        model=object(),
        ld_name="GenericLD",
        ln_map={"PIGO/LLN0": object()},
        keep_alive=[],
    )
    manager = dataset_server_module.ServerDataSetManager(builder)
    manager.dataset_catalog.append(
        {
            "ref": "PIGO/LLN0$dsGOOSE1",
            "name": "dsGOOSE1",
            "ld": "PIGO",
            "ln": "LLN0",
            "member_count": 1,
            "members": [],
        }
    )

    success = manager.add_goose_control_block(
        name="gocb1",
        app_id=0x2001,
        data_set_ref="PIGO/LLN0$dsGOOSE1",
        conf_rev=1,
        ld_inst="PIGO",
    )

    assert success is True
    assert dataset_create_calls == []


def test_goose_control_reuses_pre_registered_control_block(monkeypatch):
    created_gocbs = []
    fake_iec61850 = SimpleNamespace(
        DataSet_create=lambda *_args: object(),
        GSEControlBlock_create=lambda *args: created_gocbs.append(args) or object(),
    )
    monkeypatch.setattr(dataset_server_module, "iec61850", fake_iec61850, raising=False)

    builder = SimpleNamespace(
        model=object(),
        ln_map={"PIGO/LLN0": object()},
        keep_alive=[],
    )
    manager = dataset_server_module.ServerDataSetManager(builder)
    manager.dataset_catalog.append({"ref": "PIGO/LLN0$dsGOOSE1"})
    config = {
        "name": "gocbPub1",
        "app_id": 0x2001,
        "data_set_ref": "PIGO/LLN0$dsGOOSE1",
        "conf_rev": 1,
        "ld_inst": "PIGO",
    }

    assert manager.add_goose_control_block(**config) is True
    assert manager.add_goose_control_block(**config) is True

    assert len(created_gocbs) == 1
    assert manager.goose_cb_list == [{"ld_inst": "PIGO", "name": "gocbPub1", "app_id": 0x2001}]


def test_dataset_entry_uses_unqualified_native_ld_inst(monkeypatch):
    entry_calls = []
    fake_iec61850 = SimpleNamespace(
        DataSetEntry_create=lambda *args: entry_calls.append(args) or object(),
    )
    monkeypatch.setattr(dataset_server_module, "iec61850", fake_iec61850, raising=False)
    builder = SimpleNamespace(
        model_name="PCS001G",
        keep_alive=[],
        ensure_fcda_model_nodes=lambda *_args: None,
    )
    manager = dataset_server_module.ServerDataSetManager(builder)

    count = manager._add_fcda_entries_to_dataset(
        object(),
        [{"name": "PCS001GC1/CSWI1.StrVal.setMag.f", "fc": "SG", "iec_type": "float"}],
        "PCS001GC1",
    )

    assert count == 1
    assert entry_calls[0][1] == "C1/CSWI1$SG$StrVal"
    assert entry_calls[0][3] == "setMag$f"


def test_goose_control_derives_ld_from_dataset_instead_of_generic_ld(monkeypatch):
    created_gocbs = []
    fake_iec61850 = SimpleNamespace(
        DataSet_create=lambda *_args: object(),
        GSEControlBlock_create=lambda *args: created_gocbs.append(args) or object(),
    )
    monkeypatch.setattr(dataset_server_module, "iec61850", fake_iec61850, raising=False)
    lln0 = object()
    builder = SimpleNamespace(
        model=object(),
        model_name="PCS001G",
        ld_name="GenericLD",
        ld_map={"PCS001GC1": object()},
        ln_map={"PCS001GC1/LLN0": lln0},
        keep_alive=[],
    )
    manager = dataset_server_module.ServerDataSetManager(builder)
    manager.dataset_catalog.append({"ref": "PCS001GC1/LLN0$GooseDs"})

    assert manager.add_goose_control_block(
        name="ItlPositions",
        app_id=0x3000,
        data_set_ref="PCS001GC1/LLN0$GooseDs",
        conf_rev=1,
    )
    assert created_gocbs
    assert "GenericLD" not in builder.ld_map
