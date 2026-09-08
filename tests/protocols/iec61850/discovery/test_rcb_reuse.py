"""在线发现应只读取一遍 RCB，并保留报告的真实状态。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.proto.iec61850.defs.types import RCBInfo
from src.proto.iec61850.model import discovery as discovery_module
from src.proto.iec61850.model.discovery import ModelDiscoveryService
from src.proto.iec61850.model.ied_model import IedModel, LDModel, LNModel, RCBRef
from src.proto.iec61850.plugins.reports import BrcbHandler, ReportsPlugin, UrcbHandler
from src.proto.iec61850.plugins.reports.callback import ReportCallbackHandler


@pytest.mark.parametrize(("fc", "rcb_type", "parser"), [("BR", "BRCB", BrcbHandler), ("RP", "URCB", UrcbHandler)])
def test_rcb_discovery_saves_full_response_without_an_extra_read(monkeypatch, fc, rcb_type, parser):
    native = SimpleNamespace(
        IED_ERROR_OK=0,
        ClientReportControlBlock_create=Mock(return_value=object()),
        pyWrap_IedConnection_getRCBValues=Mock(return_value=(None, 0)),
        ClientReportControlBlock_destroy=Mock(),
        ClientReportControlBlock_getRptId=lambda _rcb: "report-id",
        ClientReportControlBlock_getDataSetReference=lambda _rcb: "OTHER/LLN0$ds",
        ClientReportControlBlock_getIntgPd=lambda _rcb: 15000,
        ClientReportControlBlock_getTrgOps=lambda _rcb: 0x11,
        ClientReportControlBlock_getOptFlds=lambda _rcb: 0x4F,
    )
    monkeypatch.setattr(discovery_module, "iec61850", native)
    detail = RCBInfo(ref="LD0/GGIO1.report01", rcb_type=rcb_type, rpt_ena=True, owner="other-client")
    parse = Mock(return_value=detail)
    monkeypatch.setattr(parser, "_parse_rcb", parse)
    service = ModelDiscoveryService()

    assert service._read_rcb_detail(object(), "LD0", "LD0/GGIO1", "report01", fc) == (
        "report-id",
        "ds",
        15000,
        0x11,
        0x4F,
    )
    assert service.rcb_details == {detail.ref: detail}
    assert native.pyWrap_IedConnection_getRCBValues.call_count == 1
    assert native.ClientReportControlBlock_destroy.call_count == 1
    service.invalidate()
    assert service.rcb_details == {}


def test_reusing_rcbs_preserves_reservation_and_only_retries_missing_details(monkeypatch):
    refs = [
        RCBRef(name="good", ref="LD0/GGIO1.good", rcb_type="BRCB"),
        RCBRef(name="retry", ref="LD0/GGIO1.retry", rcb_type="URCB"),
    ]
    model = IedModel(lds=(LDModel(name="LD0", lns=(LNModel(name="GGIO1", rcb_list=tuple(refs)),)),))
    plugin = ReportsPlugin()
    plugin._rcb_detail_cache["OLD/LLN0.old"] = {}
    plugin._rcb_type_map["OLD/LLN0.old"] = "URCB"
    monkeypatch.setattr(ReportCallbackHandler, "is_active", lambda *_args: False)
    retry = {"ref": refs[1].ref, "rpt_ena": False}
    plugin._get_rcb_info = Mock(return_value=retry)
    detail = RCBInfo(
        ref=refs[0].ref,
        rcb_type="BRCB",
        rpt_ena=True,
        owner="other-client",
        resv_tms=-1,
        data_set_ref="OTHER/LLN0$ds",
        conf_rev=7,
        entry_id=b"\x01",
        sq_num=13,
    )

    items = plugin.reuse_discovered_rcbs(model, {detail.ref: detail})

    assert items[0]["rpt_ena"] is True
    assert items[0]["locked"] is True
    assert items[0]["owner"] == "other-client"
    assert items[0]["data_set_ref"] == "OTHER/LLN0$ds"
    assert items[0]["conf_rev"] == 7
    assert items[0]["entry_id"] == "01"
    assert items[0]["sq_num"] == 13
    assert items[1] == retry
    plugin._get_rcb_info.assert_called_once_with(refs[1].ref, "URCB", "LD0", "GGIO1")
    assert set(plugin._rcb_detail_cache) == {rcb.ref for rcb in refs}
    assert set(plugin._rcb_type_map) == set(plugin._rcb_detail_cache)
