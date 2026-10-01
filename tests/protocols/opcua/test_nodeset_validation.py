"""Reject model features that the scalar repository cannot preserve."""

import pytest

from src.proto.opcua.core.nodeset import inspect_nodeset

XML = """<?xml version="1.0" encoding="utf-8"?>
<UANodeSet xmlns="http://opcfoundation.org/UA/2011/03/UANodeSet.xsd"
 xmlns:uax="http://opcfoundation.org/UA/2008/02/Types.xsd">
 <NamespaceUris><Uri>urn:ems:model</Uri></NamespaceUris>
 <UAVariable NodeId="ns=1;s=power" BrowseName="1:Power" DataType="i=11" AccessLevel="3" UserAccessLevel="3">
  <DisplayName>Power</DisplayName>
  <References>
   <Reference ReferenceType="i=47" IsForward="false">i=85</Reference>
   <Reference ReferenceType="i=40">i=63</Reference>
  </References>
  <Value><uax:Double>12.5</uax:Double></Value>
 </UAVariable>
</UANodeSet>"""


@pytest.mark.asyncio
async def test_scalar_nodeset_is_valid_without_opening_a_listener():
    parsed = await inspect_nodeset(XML.encode())
    assert parsed.namespace_uri == "urn:ems:model"
    assert parsed.definitions[0]["node_id"] == "ns=2;s=power"
    assert parsed.definitions[0]["initial_value"] == 12.5
    assert parsed.definitions[0]["writable"] is True


@pytest.mark.parametrize(
    "source,target,message",
    [
        ('DataType="i=11"', 'DataType="i=12"', "Boolean"),
        ('AccessLevel="3"', 'AccessLevel="7"', "访问"),
        ('BrowseName="1:Power"', 'BrowseName="1:Power" ValueRank="1"', "ValueRank"),
        ("<DisplayName>Power</DisplayName>", "<DisplayName>Other</DisplayName>", "DisplayName"),
        ('ReferenceType="i=47"', 'ReferenceType="i=35"', "引用"),
        ("<uax:Double>12.5</uax:Double>", "<uax:Double>NaN</uax:Double>", "有限"),
    ],
)
@pytest.mark.asyncio
async def test_unsupported_features_are_rejected(source, target, message):
    with pytest.raises(ValueError, match=message):
        await inspect_nodeset(XML.replace(source, target).encode())


@pytest.mark.asyncio
async def test_dtd_and_duplicate_nodes_are_rejected():
    with pytest.raises(ValueError, match="DTD"):
        await inspect_nodeset(XML.replace("<UANodeSet ", "<!DOCTYPE UANodeSet []><UANodeSet ").encode())
    variable = XML[XML.index(" <UAVariable") : XML.index(" </UAVariable>") + len(" </UAVariable>")]
    with pytest.raises(ValueError, match="重复"):
        await inspect_nodeset(XML.replace("</UANodeSet>", variable + "</UANodeSet>").encode())
