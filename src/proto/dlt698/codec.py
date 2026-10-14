"""Lossless conversion between HTTP Data and the installed native library."""

from datetime import datetime

from src.proto.dlt698.schema import TYPE_NAMES, Data, address


def native():
    from dlt698 import model

    return model


def oad(text: str):
    n = native()
    value = address(text)
    return n.Oad(oi=int(value[:4], 16), attribute=int(value[4:6], 16), index=int(value[6:], 16))


def omd(text: str):
    n = native()
    value = address(text)
    return n.Omd(oi=int(value[:4], 16), method=int(value[4:6], 16), mode=int(value[6:], 16))


def address_text(value) -> str:
    attribute = value.attribute if hasattr(value, "attribute") else value.method
    index = value.index if hasattr(value, "index") else value.mode
    return f"{value.oi:04X}{attribute:02X}{index:02X}"


def to_native(value: Data | dict):
    n = native()
    value = value if isinstance(value, Data) else Data.model_validate(value)
    constructor = getattr(n.Data, TYPE_NAMES[value.type])
    if value.type == "Null":
        return constructor()
    if value.type in ("Array", "Structure"):
        return constructor([to_native(item) for item in value.value])
    if value.type.startswith(("Int", "UInt")) or value.type == "Enum":
        return constructor(int(value.value))
    if value.type.startswith("Float"):
        return constructor(float(value.value))
    if value.type == "OctetString":
        return constructor(bytes.fromhex(value.value))
    if value.type == "BitString":
        bits = value.value
        return constructor(
            len(bits), int(bits.ljust((len(bits) + 7) // 8 * 8, "0") or "0", 2).to_bytes((len(bits) + 7) // 8, "big")
        )
    if value.type in ("Date", "Time", "DateTime", "DateTimeS"):
        if value.raw_fields is not None:
            return constructor(value.raw_fields)
        fmt = {"Date": "%Y-%m-%d", "Time": "%H:%M:%S"}.get(value.type, "%Y-%m-%dT%H:%M:%S")
        date = datetime.strptime(value.value, fmt)
        fields = [date.year >> 8, date.year & 255, date.month, date.day]
        if value.type == "Date":
            fields += [date.isoweekday()]
        elif value.type == "Time":
            fields = [date.hour, date.minute, date.second]
        elif value.type == "DateTimeS":
            fields += [date.hour, date.minute, date.second]
        else:
            fields += [date.isoweekday(), date.hour, date.minute, date.second, 0, 0]
        return constructor(fields)
    return constructor(value.value)


def from_native(value) -> dict:
    reverse = {native_name: name for name, native_name in TYPE_NAMES.items()}
    kind = reverse.get(value.type.name)
    if kind is None:
        from dlt698 import encode_data

        raise ValueError(f"Data 类型 {value.type.name} 需要原始详情；HEX={encode_data(value).hex().upper()}")
    raw = value.value
    if kind in ("Array", "Structure"):
        return {"type": kind, "value": [from_native(child) for child in raw]}
    if kind.startswith(("Int", "UInt")) or kind == "Enum":
        raw = str(raw)
    elif kind.startswith("Float"):
        raw = repr(raw)
    elif kind == "OctetString":
        raw = bytes(raw).hex().upper()
    elif kind == "BitString":
        raw = "".join(f"{byte:08b}" for byte in raw.value)[: raw.bit_count]
    elif kind in ("Date", "Time", "DateTime", "DateTimeS"):
        fields = list(raw)
        if kind == "Time":
            text = ":".join(f"{part:02d}" for part in fields)
        else:
            text = f"{fields[0] * 256 + fields[1]:04d}-{fields[2]:02d}-{fields[3]:02d}"
            if kind != "Date":
                clock = fields[5:8] if kind == "DateTime" else fields[4:7]
                text += "T" + ":".join(f"{part:02d}" for part in clock)
        from dlt698 import encode_data

        return {"type": kind, "value": text, "raw_fields": fields, "encoded_hex": encode_data(value).hex().upper()}
    return {"type": kind, "value": raw}
