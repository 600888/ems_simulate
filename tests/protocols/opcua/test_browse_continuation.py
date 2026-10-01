"""Bounded native Browse continuation and explicit release on early exit."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from asyncua import ua
import pytest

import src.proto.opcua.core.transport as transport


def reference(name):
    return ua.ReferenceDescription(
        NodeId=ua.ExpandedNodeId(name, 2),
        BrowseName=ua.QualifiedName(name, 2),
        DisplayName=ua.LocalizedText(name),
        NodeClass=ua.NodeClass.Variable,
    )


def setup_client(monkeypatch, first, subsequent):
    session = SimpleNamespace(browse=AsyncMock(return_value=[first]), browse_next=AsyncMock(side_effect=subsequent))
    client = transport.UaClientCore("opc.tcp://127.0.0.1:4840/ems/")
    monkeypatch.setattr(client, "_node", lambda _node_id: SimpleNamespace(nodeid=ua.NodeId(85), session=session))
    return client, session


@pytest.mark.asyncio
async def test_native_continuation_combines_pages_before_offset(monkeypatch):
    client, session = setup_client(
        monkeypatch,
        ua.BrowseResult(References=[reference("a")], ContinuationPoint=b"one"),
        [[ua.BrowseResult(References=[reference("b"), reference("c")])]],
    )
    result = await client.browse_page(limit=1, offset=1)
    assert result["nodes"][0]["browse_name"] == "b"
    assert result["total"] == 3 and result["has_more"]
    assert session.browse.call_args.args[0].RequestedMaxReferencesPerNode == 500
    assert not session.browse_next.call_args.args[0].ReleaseContinuationPoints


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["size", "requests", "cancel"])
async def test_early_exit_releases_current_continuation(monkeypatch, failure):
    monkeypatch.setattr(transport, "MAX_BROWSE_REFERENCES", 1)
    monkeypatch.setattr(transport, "MAX_BROWSE_REQUESTS", 1 if failure == "requests" else 100)
    page = ua.BrowseResult(
        References=[reference("a"), reference("b")] if failure == "size" else [], ContinuationPoint=b"owned"
    )
    client, session = setup_client(
        monkeypatch,
        page,
        [asyncio.CancelledError(), []] if failure == "cancel" else [[]],
    )
    with pytest.raises(asyncio.CancelledError if failure == "cancel" else ValueError):
        await client.browse_page()
    release = session.browse_next.call_args.args[0]
    assert release.ReleaseContinuationPoints and release.ContinuationPoints == [b"owned"]
