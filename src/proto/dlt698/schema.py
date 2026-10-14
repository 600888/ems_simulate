"""Strict HTTP models. Protocol integers are decimal strings, never JSON floats."""

from datetime import datetime
import math
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


def address(value: str) -> str:
    value = re.sub(r"\s", "", value).removeprefix("0x").upper()
    if not re.fullmatch(r"[0-9A-F]{8}", value):
        raise ValueError("OAD/OMD 必须是 8 位十六进制")
    return value


class Dlt698Config(Model):
    role: Literal["client", "server"] = "client"
    server_address: str = "000000000000"
    logical_address: int = Field(0, ge=0, le=3, strict=True)
    client_address: int = Field(16, ge=0, le=255, strict=True)
    association: Literal["public", "preestablished"] = "public"
    request_timeout_ms: int = Field(5000, ge=100, le=60000, strict=True)
    heartbeat_interval_s: int = Field(30, ge=0, le=3600, strict=True)
    protocol_version: int = Field(1, ge=0, le=65535, strict=True)
    send_frame_max: int = Field(2048, ge=64, le=16383, strict=True)
    receive_frame_max: int = Field(2048, ge=64, le=16383, strict=True)
    receive_window: int = Field(1, ge=1, le=255, strict=True)
    apdu_max: int = Field(2048, ge=64, le=65535, strict=True)
    association_timeout_s: int = Field(120, ge=1, le=86400, strict=True)
    wiring: Literal["three_phase_four_wire", "three_phase_three_wire", "single_phase"] = "three_phase_four_wire"
    tariff_count: int = Field(4, ge=0, le=255, strict=True)
    harmonic_order: int = Field(21, ge=1, le=255, strict=True)

    @field_validator("server_address")
    @classmethod
    def validate_sa(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[0-9a-fA-F]{2}){1,16}", value):
            raise ValueError("服务器地址必须包含 1–16 个十六进制字节")
        return value.upper()


TYPE_NAMES = {
    "Null": "null",
    "Boolean": "boolean",
    "Int8": "int8",
    "UInt8": "uint8",
    "Int16": "int16",
    "UInt16": "uint16",
    "Int32": "int32",
    "UInt32": "uint32",
    "Int64": "int64",
    "UInt64": "uint64",
    "Enum": "enumeration",
    "Float32": "float32",
    "Float64": "float64",
    "OctetString": "octet_string",
    "VisibleString": "visible_string",
    "Utf8String": "utf8_string",
    "BitString": "bit_string",
    "Date": "date",
    "Time": "time",
    "DateTime": "date_time",
    "DateTimeS": "date_time_s",
    "Array": "array",
    "Structure": "structure",
}


class Data(Model):
    type: str
    value: Any
    raw_fields: list[int] | None = None
    encoded_hex: str | None = None

    @model_validator(mode="after")
    def validate_value(self):
        if self.type not in TYPE_NAMES:
            raise ValueError(f"不支持的 Data 类型: {self.type}")
        value = self.value
        if self.type in ("Array", "Structure"):
            if not isinstance(value, list) or len(value) > 10000:
                raise ValueError("复合 Data 必须是至多 10000 个精确子项")
            self.value = [Data.model_validate(item).model_dump(exclude_none=True) for item in value]
        elif self.type == "Null":
            if value is not None:
                raise ValueError("Null 的值必须为 null")
        elif self.type == "Boolean":
            if not isinstance(value, bool):
                raise ValueError("Boolean 必须使用 true/false")
        elif self.type.startswith(("Int", "UInt")) or self.type == "Enum":
            if not isinstance(value, str) or not re.fullmatch(r"-?\d+", value):
                raise ValueError("整数 Data 必须使用十进制字符串")
            bits = 8 if self.type == "Enum" else int(re.search(r"\d+", self.type)[0])
            signed = self.type.startswith("Int")
            low, high = (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if signed else (0, (1 << bits) - 1)
            if not low <= int(value) <= high:
                raise ValueError(f"{self.type} 数值越界")
        else:
            if not isinstance(value, str) or len(value) > 1048576:
                raise ValueError("Data 值必须是有界字符串")
            if self.type.startswith("Float"):
                if not value.strip() or not math.isfinite(float(value)):
                    raise ValueError("浮点值必须有限")
                if self.type == "Float32" and abs(float(value)) > 3.4028234663852886e38:
                    raise ValueError("Float32 数值越界")
            elif self.type == "OctetString" and not re.fullmatch(r"(?:[0-9a-fA-F]{2})*", value):
                raise ValueError("OctetString 必须是十六进制字节对")
            elif self.type == "BitString" and not re.fullmatch(r"[01]*", value):
                raise ValueError("BitString 只包含 0/1")
            elif self.type in ("Date", "Time", "DateTime", "DateTimeS") and self.raw_fields is None:
                pattern = {"Date": "%Y-%m-%d", "Time": "%H:%M:%S"}.get(self.type, "%Y-%m-%dT%H:%M:%S")
                parsed = datetime.strptime(value, pattern)
                if parsed.strftime(pattern) != value:
                    raise ValueError("日期/时间格式错误")
        return self


class Point(Model):
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    oad: str
    category: Literal["energy", "demand", "variable", "harmonic", "parameter"] = "parameter"
    data_type: str
    unit: str = Field("", max_length=32)
    scaler: int = Field(0, ge=-12, le=12, strict=True)
    standard: bool = False
    writable: bool = False
    initial_value: Data

    _oad = field_validator("oad")(address)

    @model_validator(mode="after")
    def matching_type(self):
        self.code, self.name = self.code.strip(), self.name.strip()
        if not self.code or not self.name or self.data_type != self.initial_value.type:
            raise ValueError("测点编码/名称不能为空，Data 类型必须与初值一致")
        return self


class RecordQuery(Model):
    template: Literal["daily", "monthly", "power_loss", "initialization"]
    oad: str
    selector: Literal["all", "at", "between", "sequences", "latest"] = "all"
    start: str = ""
    end: str = ""
    latest: int = Field(1, ge=1, le=65535, strict=True)
    columns: list[str] = Field(min_length=1, max_length=128)

    _oad = field_validator("oad")(address)

    @field_validator("columns")
    @classmethod
    def validate_columns(cls, values):
        return [address(value) for value in values]

    @model_validator(mode="after")
    def bounds(self):
        if self.selector in ("at", "between"):
            Data(type="DateTimeS", value=self.start)
            if self.selector == "between":
                Data(type="DateTimeS", value=self.end)
                if self.start >= self.end:
                    raise ValueError("时间区间必须开始小于结束，结束不包含")
        if self.selector == "sequences":
            if (
                not self.start.isdigit()
                or not self.end.isdigit()
                or not 0 <= int(self.start) < int(self.end) <= 4294967295
            ):
                raise ValueError("序号区间不合法，结束不包含")
        return self


class ReadRequest(Model):
    codes: list[str] = Field(min_length=1, max_length=1000)


class ProbeRequest(Model):
    oads: list[str] = Field(min_length=1, max_length=1000)

    @field_validator("oads")
    @classmethod
    def validate_oads(cls, values):
        return [address(value) for value in values]


class OperationItem(Model):
    oad: str | None = None
    omd: str | None = None
    data: Data | None = None
    tsa: str | None = None
    get_oad: str | None = None
    delay_s: int = Field(0, ge=0, le=255, strict=True)

    @field_validator("oad", "omd", "get_oad")
    @classmethod
    def validate_address(cls, value):
        return address(value) if value is not None else None


class Operation(Model):
    service: Literal["set", "action", "local_values", "proxy", "md5", "then_get", "report"]
    items: list[OperationItem] = Field(max_length=1000)
    session_id: str | None = None
    proxy_service: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def required_operands(self):
        for item in self.items:
            if self.service in ("set", "local_values", "md5") and not item.oad:
                raise ValueError("操作需要 OAD")
            if self.service == "action" and not item.omd:
                raise ValueError("ACTION 需要 OMD")
            if self.service in ("set", "action", "local_values", "then_get") and item.data is None:
                raise ValueError("操作需要有类型的 Data")
            if self.service == "then_get":
                kind = self.options.get("operation", "set")
                if kind not in ("set", "action") or not item.get_oad:
                    raise ValueError("ThenGet 需要有效的操作方式和独立回读 OAD")
                if not (item.oad if kind == "set" else item.omd):
                    raise ValueError("ThenGet 缺少操作 OAD/OMD")
        return self


class AutoReadRequest(Model):
    running: bool
    interval_ms: int = Field(1000, ge=100, le=60000, strict=True)
    codes: list[str] = Field(default_factory=list, max_length=1000)
