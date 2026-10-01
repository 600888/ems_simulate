"""Scalar model conflict handling, ownership, and channel copy persistence."""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.data.model.channel import Channel
from src.data.model.opcua_config import OpcUaConfig
from src.data.model.opcua_feature import OpcUaFeature
from src.data.model.opcua_node import OpcUaNode
from src.data.model.opcua_point import OpcUaPoint
from src.data.model.opcua_secret import OpcUaSecret
import src.data.service.opcua_copy_service as copy_module
import src.data.service.opcua_model_service as model_module
import src.data.service.opcua_node_service as node_module
from src.proto.opcua.core.nodeset import ScalarNodeSet


@pytest.fixture
def model_db(monkeypatch):
    engine = create_engine("sqlite://")
    Channel.metadata.create_all(
        engine,
        tables=[
            Channel.__table__,
            OpcUaConfig.__table__,
            OpcUaNode.__table__,
            OpcUaPoint.__table__,
            OpcUaFeature.__table__,
            OpcUaSecret.__table__,
        ],
    )
    sessions = sessionmaker(engine, expire_on_commit=False)
    for module in (copy_module, model_module, node_module):
        monkeypatch.setattr(module, "local_session", sessions)
    with sessions() as session, session.begin():
        session.add_all(
            [
                Channel(
                    id=identifier,
                    code=f"UA_{identifier}",
                    name=f"UA {identifier}",
                    protocol_type=7,
                    conn_type=1 if identifier in (1, 4) else 2,
                    ip="127.0.0.1",
                    port=4840 + identifier,
                )
                for identifier in (1, 2, 3, 4)
            ]
        )
    yield sessions
    engine.dispose()


def model() -> ScalarNodeSet:
    return ScalarNodeSet(
        "digest",
        "urn:ems:model",
        [
            {
                "namespace_uri": "urn:ems:model",
                "node_id": "ns=2;s=power",
                "browse_name": "Power",
                "data_type": "Double",
                "initial_value": 12.5,
                "writable": True,
            }
        ],
    )


def test_nodeset_import_requires_digest_and_explicit_overwrite(model_db):
    parsed = model()
    assert not model_module.OpcUaModelService.preview(2, parsed)["errors"]
    with pytest.raises(ValueError, match="重新预检"):
        model_module.OpcUaModelService.apply(2, parsed, "changed", "add")
    created = model_module.OpcUaModelService.apply(2, parsed, parsed.sha256, "add")
    assert created["created"] == 1
    assert len(model_module.OpcUaModelService.preview(2, parsed)["conflicts"]) == 1
    with pytest.raises(ValueError, match="冲突"):
        model_module.OpcUaModelService.apply(2, parsed, parsed.sha256, "add")
    parsed.definitions[0]["initial_value"] = 42.0
    result = model_module.OpcUaModelService.apply(2, parsed, parsed.sha256, "overwrite")
    assert result["created"] == 0 and result["updated"] == 1
    with model_db() as session:
        assert session.get(OpcUaConfig, 2).namespace_uri == "urn:ems:model"
        assert session.scalar(select(OpcUaNode)).initial_value == 42.0
    assert node_module.OpcUaNodeService.delete_variable(2, "ns=2;s=power")


def test_import_cannot_overwrite_excel_point_owned_node(model_db):
    parsed = model()
    with model_db() as session, session.begin():
        session.add(
            OpcUaPoint(
                channel_id=2,
                point_type=0,
                point_code="POWER",
                point_name="Power",
                attribute_code="power",
                node_id="ns=2;s=power",
                namespace_uri="urn:ems:model",
                data_type="Double",
                sampling_interval_ms=1000,
                initial_value=12.5,
            )
        )
    assert model_module.OpcUaModelService.preview(2, parsed)["errors"][0]["node_id"] == "ns=2;s=power"
    with pytest.raises(ValueError, match="点表"):
        model_module.OpcUaModelService.apply(2, parsed, parsed.sha256, "overwrite")
    with pytest.raises(ValueError, match="点表"):
        node_module.OpcUaNodeService.upsert_variable(2, parsed.namespace_uri, parsed.definitions[0])
    with pytest.raises(ValueError, match="点表"):
        node_module.OpcUaNodeService.delete_variable(2, "ns=2;s=power")
    with model_db() as session:
        assert session.scalar(select(func.count()).select_from(OpcUaNode)) == 0


def test_server_copy_preserves_namespace_nodes_and_point_metadata(model_db):
    parsed = model()
    model_module.OpcUaModelService.apply(2, parsed, parsed.sha256, "add")
    with model_db() as session, session.begin():
        session.add(
            OpcUaPoint(
                channel_id=2,
                point_type=0,
                point_code="POWER",
                point_name="Power",
                attribute_code="power",
                node_id="ns=2;s=power",
                namespace_uri="urn:ems:model",
                data_type="Double",
                sampling_interval_ms=1000,
                initial_value=12.5,
            )
        )
    assert copy_module.OpcUaCopyService.clone_for_channel(2, 3) == {"node_count": 1, "point_count": 1}
    with model_db() as session:
        assert session.get(OpcUaConfig, 3).namespace_uri == "urn:ems:model"
        target = session.scalar(select(OpcUaPoint).where(OpcUaPoint.channel_id == 3))
        assert target.point_code == "POWER" and target.node_id == "ns=2;s=power"
        assert target.id != session.scalar(select(OpcUaPoint.id).where(OpcUaPoint.channel_id == 2))
    with pytest.raises(ValueError, match="已有"):
        copy_module.OpcUaCopyService.clone_for_channel(2, 3)


def test_client_copy_rebuilds_full_endpoint_from_target_address(model_db):
    with model_db() as session, session.begin():
        session.add(OpcUaConfig(channel_id=1, endpoint_url="opc.tcp://127.0.0.1:4841/custom/path/"))
    assert copy_module.OpcUaCopyService.clone_for_channel(1, 4) == {"node_count": 0, "point_count": 0}
    with model_db() as session:
        assert session.get(OpcUaConfig, 4).endpoint_url == "opc.tcp://127.0.0.1:4844/custom/path/"


def test_model_import_rejects_client_role(model_db):
    with pytest.raises(ValueError, match="服务端"):
        model_module.OpcUaModelService.apply(1, model(), "digest", "add")
