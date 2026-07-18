from src.proto.iec61850.plugins.scl.service.import_service import SclImportService

SCL_WITH_GOOSE_BINDING = """<?xml version="1.0" encoding="UTF-8"?>
<SCL xmlns="http://www.iec.ch/61850/2003/SCL" version="2007" revision="B">
  <Communication>
    <SubNetwork name="station" type="8-MMS">
      <ConnectedAP iedName="PUB" apName="AP1">
        <GSE ldInst="LD0" cbName="gcbTrip">
          <Address>
            <P type="MAC-Address">01-0C-CD-01-00-01</P>
            <P type="APPID">1001</P>
          </Address>
        </GSE>
      </ConnectedAP>
    </SubNetwork>
  </Communication>
  <IED name="PUB">
    <AccessPoint name="AP1"><Server><LDevice inst="LD0">
      <LN0 lnClass="LLN0" inst="" lnType="LLN0Type">
        <DataSet name="dsTrip">
          <FCDA ldInst="LD0" lnClass="PTRC" lnInst="1" doName="Tr" daName="stVal" fc="ST"/>
        </DataSet>
        <GSEControl name="gcbTrip" datSet="dsTrip" confRev="3" type="GOOSE"/>
      </LN0>
    </LDevice></Server></AccessPoint>
  </IED>
  <IED name="SUB">
    <AccessPoint name="AP1"><Server><LDevice inst="LD1">
      <LN0 lnClass="LLN0" inst="" lnType="LLN0Type">
        <Inputs>
          <ExtRef iedName="PUB" ldInst="LD0" lnClass="PTRC" lnInst="1"
                  doName="Tr" daName="stVal" serviceType="GOOSE"
                  srcLDInst="LD0" srcLNClass="LLN0" srcCBName="gcbTrip"
                  intAddr="TripIn1"/>
        </Inputs>
      </LN0>
    </LDevice></Server></AccessPoint>
  </IED>
  <DataTypeTemplates/>
</SCL>
"""


def test_scl_gse_control_remains_publisher_and_extref_becomes_subscription():
    result = SclImportService().import_string(SCL_WITH_GOOSE_BINDING, validate=False)

    assert len(result.goose.gse_controls) == 1
    publisher = result.goose.gse_controls[0]
    assert publisher.ied_name == "PUB"
    assert publisher.go_cb_ref == "LD0/LLN0$GO$gcbTrip"

    assert len(result.goose.engineered_subscriptions) == 1
    subscription = result.goose.engineered_subscriptions[0]
    assert subscription["go_cb_ref"] == publisher.go_cb_ref
    assert subscription["subscriber_ied_name"] == "SUB"
    assert subscription["int_addr"] == "TripIn1"
    assert subscription["binding_status"] == "resolved"
    assert subscription["source"] == "SCL_EXTREF"


def test_scl_result_exposes_remote_and_engineered_subscription_views():
    result = SclImportService().import_string(SCL_WITH_GOOSE_BINDING, validate=False)

    goose = result.to_dict()["goose"]

    # 将文件作为远端 IED 描述时，GSEControl 可作为本地订阅候选。
    assert goose["subscriptions"][0]["go_cb_ref"] == "LD0/LLN0$GO$gcbTrip"
    # 将文件作为系统工程配置时，订阅关系只能来自 Inputs/ExtRef。
    assert goose["engineered_subscriptions"][0]["source"] == "SCL_EXTREF"
