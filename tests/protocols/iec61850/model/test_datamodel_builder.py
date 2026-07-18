"""IEC 61850 服务端动态模型构建器测试。"""

from types import SimpleNamespace

from src.proto.iec61850.plugins.datamodels import builder as builder_module


def test_first_lln0_reuses_node_created_with_logical_device(monkeypatch):
    """首个请求为 LLN0 时，不应在同一个 LD 下创建两个同名节点。"""
    created_nodes: list[tuple[str, object]] = []

    def create_logical_node(name, parent):
        node = object()
        created_nodes.append((name, parent))
        return node

    fake_iec61850 = SimpleNamespace(
        IedModel_create=lambda _name: object(),
        LogicalDevice_create=lambda _name, _model: object(),
        LogicalNode_create=create_logical_node,
    )
    monkeypatch.setattr(builder_module, "HAS_IEC61850", True)
    monkeypatch.setattr(builder_module, "iec61850", fake_iec61850, raising=False)

    builder = builder_module.IedModelBuilder(ied_name="TestIED")
    lln0 = builder.get_or_create_ln("LD0", "LLN0")

    assert lln0 is builder.ln_map["LD0/LLN0"]
    assert [name for name, _parent in created_nodes] == ["LLN0"]


def test_qualified_mms_domain_is_not_prefixed_twice(monkeypatch):
    created_lds: list[str] = []
    fake_iec61850 = SimpleNamespace(
        IedModel_create=lambda _name: object(),
        LogicalDevice_create=lambda name, _model: created_lds.append(name) or object(),
        LogicalNode_create=lambda _name, _parent: object(),
    )
    monkeypatch.setattr(builder_module, "HAS_IEC61850", True)
    monkeypatch.setattr(builder_module, "iec61850", fake_iec61850, raising=False)

    builder = builder_module.IedModelBuilder(ied_name="PCS001G")
    builder.get_or_create_ld("PCS001GC1")

    assert created_lds == ["C1"]
    assert "PCS001GC1" in builder.ld_map
    assert "PCS001GC1/LLN0" in builder.ln_map
