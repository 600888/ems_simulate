"""OPC UA configuration stays separate and consistent with channel addresses."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.model.channel import Channel
from src.data.model.opcua_config import OpcUaConfig
from src.data.model.opcua_node import OpcUaNode
from src.data.model.opcua_point import OpcUaPoint
import src.data.service.opcua_config_service as config_module
import src.data.service.opcua_node_service as node_module


@pytest.fixture
def isolated_db(monkeypatch):
    engine = create_engine("sqlite://")
    Channel.metadata.create_all(
        engine,
        tables=[
            Channel.__table__,
            OpcUaConfig.__table__,
            OpcUaNode.__table__,
            OpcUaPoint.__table__,
        ],
    )
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(config_module, "local_session", sessions)
    monkeypatch.setattr(node_module, "local_session", sessions)
    with sessions() as session, session.begin():
        session.add_all(
            [
                Channel(
                    id=1, code="UA_CLIENT", name="UA client", protocol_type=7, conn_type=1, ip="127.0.0.1", port=4840
                ),
                Channel(
                    id=2, code="UA_SERVER", name="UA server", protocol_type=7, conn_type=2, ip="127.0.0.1", port=4840
                ),
            ]
        )
    yield sessions
    engine.dispose()


def test_client_endpoint_updates_channel_in_one_transaction(isolated_db):
    result = config_module.OpcUaConfigService.save_client_endpoint(1, "opc.tcp://127.0.0.2:4855/custom/")
    assert result["endpoint_url"] == "opc.tcp://127.0.0.2:4855/custom/"
    with isolated_db() as session:
        channel = session.get(Channel, 1)
        assert (channel.ip, channel.port) == ("127.0.0.2", 4855)
    with pytest.raises(ValueError, match="loopback"):
        config_module.OpcUaConfigService.save_client_endpoint(1, "opc.tcp://192.0.2.1:4840/")
    assert config_module.OpcUaConfigService.get(1)["bind_port"] == 4855


def test_server_nodes_are_persistent_and_namespace_cannot_drift(isolated_db):
    namespace_uri = "urn:ems-simulate:channel:2"
    node = node_module.OpcUaNodeService.upsert_variable(
        2,
        namespace_uri,
        {
            "node_id": "ns=2;s=energy.power",
            "browse_name": "Power",
            "data_type": "Double",
            "initial_value": 12.5,
            "writable": True,
        },
    )
    assert node["node_id"] == "ns=2;s=energy.power"
    assert node_module.OpcUaNodeService.list_nodes(2)[0]["initial_value"] == 12.5
    with pytest.raises(ValueError, match="不能更改命名空间"):
        config_module.OpcUaConfigService.save_server_model(2, "/ua/", "urn:other")
    assert config_module.OpcUaConfigService.get(2)["namespace_uri"] == namespace_uri
    with pytest.raises(ValueError, match="Boolean"):
        node_module.OpcUaNodeService.upsert_variable(
            2,
            namespace_uri,
            {
                "node_id": "ns=2;s=energy.invalid",
                "browse_name": "Invalid",
                "data_type": "Boolean",
                "initial_value": 1,
            },
        )
    assert len(node_module.OpcUaNodeService.list_nodes(2)) == 1
