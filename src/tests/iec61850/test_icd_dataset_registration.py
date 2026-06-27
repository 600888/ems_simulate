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
        app_id="PCS001PIGO/LLN0$GO$gocb1",
        gse_app_id="2001",
        mac_address="01-0C-CD-01-20-01",
    )

    publisher = info.to_publisher_dict()

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
