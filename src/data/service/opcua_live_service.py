"""Channel-scoped rollback snapshots for live configuration operations."""

from copy import deepcopy

from sqlalchemy import delete, select

from src.data.controller.db import local_session
from src.data.model.opcua_config import OpcUaConfig
from src.data.model.opcua_feature import OpcUaFeature
from src.data.model.opcua_node import OpcUaNode
from src.data.model.opcua_point import OpcUaPoint
from src.data.model.opcua_secret import OpcUaSecret


class OpcUaLiveService:
    MODELS = (OpcUaConfig, OpcUaNode, OpcUaPoint, OpcUaFeature, OpcUaSecret)

    @staticmethod
    def snapshot(channel_id: int) -> dict:
        with local_session() as session:
            return {
                model: [
                    {column.name: deepcopy(getattr(row, column.name)) for column in model.__table__.columns}
                    for row in session.scalars(select(model).where(model.channel_id == channel_id))
                ]
                for model in OpcUaLiveService.MODELS
            }

    @staticmethod
    def restore(channel_id: int, snapshot: dict) -> None:
        with local_session() as session, session.begin():
            for model in reversed(OpcUaLiveService.MODELS):
                session.execute(delete(model).where(model.channel_id == channel_id))
            for model in OpcUaLiveService.MODELS:
                session.add_all(model(**row) for row in snapshot[model])

    @staticmethod
    def reconcile_features(channel_id: int) -> None:
        """Removed nodes must not leave simulation/history references behind."""
        with local_session() as session, session.begin():
            nodes = set(session.scalars(select(OpcUaNode.node_id).where(OpcUaNode.channel_id == channel_id)))
            for row in session.scalars(select(OpcUaFeature).where(OpcUaFeature.channel_id == channel_id)):
                config = deepcopy(row.config)
                if row.name == "simulation":
                    config["rules"] = [rule for rule in config.get("rules", []) if rule["node_id"] in nodes]
                elif row.name == "history":
                    config["nodes"] = [key for key in config.get("nodes", []) if key in nodes]
                elif row.name == "events":
                    source = config.get("source_node", "i=2253")
                    # Standard nodes remain available independently of imported definitions.
                    if source.startswith("ns=") and source not in nodes:
                        config["enabled"] = False
                row.config = config
