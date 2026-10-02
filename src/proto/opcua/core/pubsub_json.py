"""OPC UA 1.04 reversible JSON scalar / array encoding for PubSub."""

from asyncua import ua

EVENT_TYPES = {
    "EventId": "ByteString",
    "EventType": "NodeId",
    "SourceNode": "NodeId",
    "SourceName": "String",
    "Time": "DateTime",
    "ReceiveTime": "DateTime",
    "Severity": "UInt16",
    "Message": "LocalizedText",
    "ConditionId": "NodeId",
    "AckedState": "Boolean",
    "Retain": "Boolean",
}


def variant(value, type_name: str | None) -> dict:
    type_id = ua.VariantType[type_name].value if type_name else 0

    def body(item):
        if isinstance(item, list):
            return [body(v) for v in item]
        if isinstance(item, dict):
            if "integer" in item:
                return item["integer"]
            if "base64" in item:
                return item["base64"]
            raise ValueError("PubSub 暂不支持结构字段")
        if type_name in {"Int64", "UInt64"} and item is not None:
            return str(item)
        if type_name == "LocalizedText" and item is not None:
            return {"Text": item}
        return item

    return {"Type": type_id, "Body": body(value)}


def data_value(snapshot: dict, content: list[str]) -> dict:
    value = variant(snapshot.get("value"), snapshot.get("variant_type"))
    if not content:
        return value
    result = {"Value": value}
    if "status_code" in content:
        result["StatusCode"] = getattr(ua.StatusCodes, snapshot["status_code"], ua.StatusCodes.BadUnexpectedError)
    if "source_timestamp" in content and snapshot.get("source_timestamp"):
        result["SourceTimestamp"] = snapshot["source_timestamp"]
    if "server_timestamp" in content and snapshot.get("server_timestamp"):
        result["ServerTimestamp"] = snapshot["server_timestamp"]
    return result


def overall_status(snapshots: list[dict]) -> int:
    return max(
        (getattr(ua.StatusCodes, item["status_code"], ua.StatusCodes.BadUnexpectedError) for item in snapshots),
        default=0,
    )


def field_metadata(name: str, type_name: str | None, field_id: str, array: bool = False) -> dict:
    type_id = ua.VariantType[type_name].value if type_name else 0
    return {
        "Name": name,
        "BuiltInType": type_id,
        "DataType": f"i={type_id}",
        "ValueRank": 1 if array else -1,
        "DataSetFieldId": field_id,
        "FieldFlags": 0,
    }
