"""Use the native standard catalog; never substitute example point definitions."""

from dlt698 import model, standard
from dlt698.errors import Dlt698Error
from src.proto.dlt698.codec import address_text, from_native, oad, to_native
from src.proto.dlt698.schema import TYPE_NAMES, Dlt698Config, Point


def layout(config: Dlt698Config):
    n = standard
    return n.DeviceLayout(
        wiring=n.Wiring.single_phase if config.wiring == "single_phase" else n.Wiring.three_phase,
        tariff_count=config.tariff_count,
        harmonic_order=config.harmonic_order,
    )


def default_data(kind, count=0, element=None):
    n = model
    name = kind.name
    if name in ("array", "structure"):
        return getattr(n.Data, name)([default_data(element or n.DataType.uint16) for _ in range(count)])
    if name in ("date", "date_time", "date_time_s"):
        from src.proto.dlt698.schema import Data

        label = {"date": "Date", "date_time": "DateTime", "date_time_s": "DateTimeS"}[name]
        return to_native(Data(type=label, value="2026-01-01" if name == "date" else "2026-01-01T00:00:00"))
    if name == "time":
        return n.Data.time([0, 0, 0])
    if name == "null":
        return n.Data.null()
    if name == "boolean":
        return n.Data.boolean(False)
    if name in ("visible_string", "utf8_string"):
        return getattr(n.Data, name)("")
    if name == "octet_string":
        return n.Data.octet_string(b"")
    if name == "bit_string":
        return n.Data.bit_string(0, b"")
    return getattr(n.Data, name)(0)


def standard_definition(point: Point, config: Dlt698Config) -> Point:
    n = standard
    attribute = oad(point.oad)
    if attribute.attribute & 0xE0:
        if point.standard:
            raise ValueError("特征非零的自定义属性不具有标准验证语义")
        return point
    try:
        definition = n.find_attribute(attribute)
    except (ValueError, IndexError, RuntimeError, Dlt698Error):
        definition = None
    if definition is None:
        if point.standard:
            raise ValueError("OAD 不在标准目录中") from None
        if n.find_object(attribute.oi):
            raise ValueError("标准对象没有该属性，不能通过自定义绕过")
        return point
    n.validate_oad(attribute, layout(config))
    n.validate_value(attribute, to_native(point.initial_value), layout(config))
    if point.writable and not definition.writable:
        raise ValueError("标准属性只读，不能授予远端 SET 权限")
    scaling = definition.scaling
    return point.model_copy(
        update={
            "standard": True,
            "writable": bool(definition.writable and point.writable),
            "scaler": scaling.scaler if scaling else 0,
            "unit": n.unit_symbol(scaling.unit) if scaling else "",
        }
    )


def catalog(config: Dlt698Config, limit=5000) -> list[dict]:
    n, device_layout = standard, layout(config)
    supported = set(TYPE_NAMES.values())
    rows = []
    for obj in n.objects():
        for definition in obj.attributes:
            if definition.record or not definition.readable or definition.type.name not in supported:
                continue
            attr = model.Oad(oi=obj.oi, attribute=definition.number, index=0)
            indices = []
            if definition.type.name == "array":
                if definition.element_type is None or definition.element_type.name not in supported:
                    continue
                for index in range(1, 256):
                    try:
                        n.validate_oad(model.Oad(oi=obj.oi, attribute=definition.number, index=index), device_layout)
                        indices.append(index)
                    except (ValueError, RuntimeError, IndexError, Dlt698Error):
                        break
            for index in [0, *indices]:
                attr.index = index
                try:
                    kind = definition.element_type if index else definition.type
                    data = default_data(kind, len(indices), definition.element_type)
                    n.validate_value(attr, data, device_layout)
                    value = from_native(data)
                except (ValueError, RuntimeError, TypeError, AttributeError, Dlt698Error):
                    continue
                text = address_text(attr)
                oi = obj.oi
                category = (
                    "energy"
                    if oi < 0x1000
                    else "demand"
                    if oi < 0x2000
                    else "harmonic"
                    if "谐波" in obj.name
                    else "variable"
                    if oi < 0x3000
                    else "parameter"
                )
                scaling = definition.scaling
                rows.append(
                    {
                        "code": f"DLT698_{text}",
                        "name": f"{obj.name} · {definition.name}" + (f" [{index}]" if index else ""),
                        "oad": text,
                        "category": category,
                        "data_type": value["type"],
                        "unit": n.unit_symbol(scaling.unit) if scaling else "",
                        "scaler": scaling.scaler if scaling else 0,
                        "standard": True,
                        "writable": bool(definition.writable and config.role == "client"),
                        "initial_value": value,
                    }
                )
                if len(rows) >= limit:
                    return rows
    return rows
