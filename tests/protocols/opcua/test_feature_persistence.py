"""Desired configurations and secrets are isolated, copied and redacted correctly."""

import base64

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.model.channel import Channel
from src.data.model.opcua_config import OpcUaConfig
from src.data.model.opcua_feature import OpcUaFeature
from src.data.model.opcua_node import OpcUaNode
from src.data.model.opcua_point import OpcUaPoint
from src.data.model.opcua_secret import OpcUaSecret
import src.data.service.opcua_config_service as config_module
import src.data.service.opcua_copy_service as copy_module
import src.data.service.opcua_feature_service as feature_module
import src.data.service.opcua_security_service as security_module
from src.proto.opcua.core.security import certificate_info


def test_feature_and_secret_copy_has_a_new_application_identity(monkeypatch, tmp_path):
    engine = create_engine("sqlite://")
    Channel.metadata.create_all(
        engine,
        tables=[model.__table__ for model in (Channel, OpcUaConfig, OpcUaNode, OpcUaPoint, OpcUaFeature, OpcUaSecret)],
    )
    sessions = sessionmaker(engine, expire_on_commit=False)
    for module in (config_module, copy_module, feature_module, security_module):
        monkeypatch.setattr(module, "local_session", sessions)
    monkeypatch.setattr(security_module.OpcUaSecurityService, "_directory", lambda: tmp_path)
    try:
        with sessions() as session, session.begin():
            for identifier in (1, 2):
                session.add(
                    Channel(
                        id=identifier,
                        code=f"UA{identifier}",
                        name=f"UA{identifier}",
                        protocol_type=7,
                        conn_type=1,
                        ip="127.0.0.1",
                        port=4840 + identifier,
                    )
                )
        feature_module.OpcUaFeatureService.save(1, "subscriptions", {"subscriptions": [{"id": "one", "items": []}]})
        security_module.OpcUaSecurityService.generate(1, "urn:ems:original", "127.0.0.1")
        security_module.OpcUaSecurityService.save_secret(1, "password", "private password")
        source = feature_module.OpcUaFeatureService.load(1)
        assert "private password" not in str(source)
        assert "private_key" not in str(source)
        copy_module.OpcUaCopyService.clone_for_channel(1, 2)
        target = feature_module.OpcUaFeatureService.load(2)
        assert source["subscriptions"] == target["subscriptions"]
        source_fingerprint = certificate_info(base64.b64decode(source["security"]["certificate"]))["fingerprint"]
        target_fingerprint = certificate_info(base64.b64decode(target["security"]["certificate"]))["fingerprint"]
        assert source_fingerprint != target_fingerprint
        assert target["security"]["application_uri"] == "urn:ems-simulate:channel:2"
        assert security_module.OpcUaSecurityService.secrets(2)["password"] == "private password"
        feature_module.OpcUaFeatureService.save(2, "subscriptions", {"subscriptions": []})
        assert feature_module.OpcUaFeatureService.load(1)["subscriptions"]["subscriptions"]
        security = target["security"]
        security["mode"] = "SignAndEncrypt"
        feature_module.OpcUaFeatureService.save(2, "security", security)
        config_module.OpcUaConfigService.save_client_endpoint(2, "opc.tcp://192.0.2.1:4840/remote/")
        assert config_module.OpcUaConfigService.get(2)["bind_host"] == "192.0.2.1"
    finally:
        engine.dispose()
