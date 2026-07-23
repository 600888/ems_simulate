"""Regression coverage for large JSON-backed IEC 61850 model projects."""

from types import SimpleNamespace

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.data.model  # noqa: F401
from src.data.model.base import Base
from src.data.model.iec61850_modeling import Iec61850ModelProject
from src.modeling.scl_importer import SclModelImporter
from src.modeling.service import Iec61850ModelingService


def test_large_import_is_stored_as_one_document_without_node_tables(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    service = Iec61850ModelingService(sessionmaker(engine, expire_on_commit=False))
    root_id = "root"
    nodes = [
        {
            "id": root_id,
            "parent_id": None,
            "kind": "ROOT",
            "name": "Large model",
            "sort_order": 0,
            "attributes": {},
        }
    ]
    nodes.extend(
        {
            "id": f"node-{index}",
            "parent_id": root_id,
            "kind": "EXTENSION",
            "name": f"extension-{index}",
            "sort_order": index,
            "attributes": {"source": "large-model-regression"},
        }
        for index in range(39_999)
    )
    imported_model = SimpleNamespace(
        project={
            "code": "LARGE_MODEL",
            "name": "Large model",
            "file_type": "ICD",
            "standard_version": "IEC 61850 Ed2.1",
            "namespace": "",
        },
        nodes=nodes,
        summary={"node_count": len(nodes), "by_kind": {"ROOT": 1, "EXTENSION": 39_999}},
        warnings=[],
    )
    monkeypatch.setattr(SclModelImporter, "parse", lambda *_args, **_kwargs: imported_model)

    imported = service.import_scl(b"<SCL/>", filename="large.icd")
    project_id = imported["project"]["id"]
    assert "tree" not in imported

    project = service.get_project(project_id)
    tree = service.get_tree(project_id)
    impact = service.get_delete_impact(project_id, root_id)
    assert project["node_count"] == 40_000
    assert len(tree) == 1
    assert len(tree[0]["children"]) == 39_999
    assert impact["subtree_count"] == project["node_count"]

    tables = set(inspect(engine).get_table_names())
    assert "iec61850_model_node" not in tables
    assert "iec61850_model_reference" not in tables

    with service.session_factory() as session:
        stored = session.get(Iec61850ModelProject, project_id)
        assert stored.model_json.startswith('{"format_version":1')
        assert len(stored.model_checksum) == 64
