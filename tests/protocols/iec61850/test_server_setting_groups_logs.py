from types import SimpleNamespace

from src.proto.iec61850.plugins.log_plugin import LogPlugin
from src.proto.iec61850.plugins.log_plugin import server as log_server
from src.proto.iec61850.plugins.scl.parser.scl_parser import SclParser
from src.proto.iec61850.plugins.setting_groups import server as sg_server

SCL_WITH_SETTING_GROUPS_AND_LOGS = """<?xml version="1.0" encoding="UTF-8"?>
<SCL xmlns="http://www.iec.ch/61850/2003/SCL">
  <IED name="IED1">
    <AccessPoint name="AP1"><Server><LDevice inst="LD0">
      <LN0 lnClass="LLN0" inst="" lnType="LLN0Type">
        <DataSet name="Events"/>
        <SettingControl numOfSGs="4" actSG="2"/>
        <Log name="EventLog"/>
        <LogControl name="EventLCB" datSet="Events" logName="EventLog"
                    intgPd="1000" logEna="true" reasonCode="true">
          <TrgOps dchg="true" qchg="true" period="true"/>
        </LogControl>
      </LN0>
    </LDevice></Server></AccessPoint>
  </IED>
  <DataTypeTemplates><LNodeType id="LLN0Type" lnClass="LLN0"/></DataTypeTemplates>
</SCL>
"""


def test_scl_parser_keeps_setting_and_log_controls():
    doc = SclParser().parse_string(SCL_WITH_SETTING_GROUPS_AND_LOGS)
    ln0 = doc.ieds[0].access_points[0].server.ldevices[0].ln0

    assert ln0.setting_control.num_of_sg == 4
    assert ln0.setting_control.act_sg == 2
    assert ln0.logs[0].name == "EventLog"
    assert ln0.log_controls[0].name == "EventLCB"
    assert ln0.log_controls[0].trg_ops.dchg is True
    assert ln0.log_controls[0].trg_ops.period is True


def test_server_setting_group_manager_edits_confirms_and_activates(monkeypatch):
    monkeypatch.setattr(sg_server.iec61850, "SettingGroupControlBlock_create", lambda *_args: object())
    monkeypatch.setattr(sg_server.iec61850, "IedServer_changeActiveSettingGroup", lambda *_args: None)
    values = {"LD0/PTOC1.StrVal.setMag.f": 10.0}
    applied = []
    server = SimpleNamespace(
        _ld_map={"LD0": object()},
        _ln_map={"LD0/LLN0": object()},
        _point_fc={"LD0/PTOC1.StrVal.setMag.f": "SG"},
        _point_refs={},
        _point_iec_type={"LD0/PTOC1.StrVal.setMag.f": "float"},
        _point_mms_type={"LD0/PTOC1.StrVal.setMag.f": "MMS_FLOAT"},
        _server=object(),
        _is_running=True,
        get_point_value=lambda address, fc="": values[address],
        set_point_values=lambda updates: applied.extend(updates) or True,
    )
    manager = sg_server.ServerSettingGroupsManager(server)

    assert manager.register("LD0", 3, 1)
    assert manager.select_edit_group("LD0/LLN0.SGCB", 2)
    assert manager.write_values(
        [{"address": "LD0/PTOC1.StrVal.setMag.f", "value": 12.5}],
        "LD0/LLN0.SGCB",
    ) == [{"address": "LD0/PTOC1.StrVal.setMag.f", "success": True}]
    assert manager.confirm_edit("LD0/LLN0.SGCB")
    assert manager.activate("LD0/LLN0.SGCB", 2)
    assert manager.get_detail("LD0/LLN0.SGCB")["act_sg"] == 2
    assert applied == [("LD0/PTOC1.StrVal.setMag.f", 12.5, "SG")]


def test_server_log_manager_records_and_queries(monkeypatch):
    monkeypatch.setattr(log_server.iec61850, "Log_create", lambda *_args: object())
    monkeypatch.setattr(log_server.iec61850, "LogControlBlock_create", lambda *_args: SimpleNamespace(logEna=True))
    server = SimpleNamespace(_ln_map={"LD0/LLN0": object()})
    manager = log_server.ServerLogManager(server)
    trg_ops = SimpleNamespace(dchg=True, qchg=False, dupd=False, period=False, gi=False)

    assert manager.register_control("LD0", "LLN0", "EventLCB", "Events", "EventLog", trg_ops, 0, True, True)
    manager.record("LD0/XCBR1.Pos.stVal", True)
    entries, more_follows = manager.query("LD0/LLN0$EventLog", 0, 9999999999999)

    assert more_follows is False
    assert entries[0]["object_ref"] == "LD0/XCBR1.Pos.stVal"
    assert entries[0]["fields"]["value"] is True


def test_client_log_trigger_bits_include_reserved_leading_bit():
    assert LogPlugin._trg_ops(0x02)["dchg"] is True
    assert LogPlugin._trg_ops(0x10)["period"] is True
