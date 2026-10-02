"""Bounded, typed feature requests with no SDK dependencies."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    node_id: str = Field(min_length=1, max_length=512)
    kind: Literal["fixed", "random", "sine", "step"] = "sine"
    minimum: float = 0
    maximum: float = 100
    period_s: float = Field(default=10, gt=0, le=86400)
    offset_s: float = Field(default=0, ge=-86400, le=86400)
    interval_ms: int = Field(default=500, ge=50, le=3600000)
    value: Any = 0
    step: float = 1
    write_policy: Literal["pause", "overwrite", "reject"] = "pause"
    enabled: bool = True

    @model_validator(mode="after")
    def bounds(self):
        if self.minimum > self.maximum:
            raise ValueError("模拟下限不能大于上限")
        return self


class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rules: list[Rule] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def unique(self):
        if len({item.node_id for item in self.rules}) != len(self.rules):
            raise ValueError("每个节点只能绑定一条模拟规则")
        return self


class MonitoredItem(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    node_id: str = Field(min_length=1, max_length=512)
    namespace_uri: str | None = Field(default=None, max_length=255)
    sampling_interval_ms: float = Field(default=500, ge=0, le=3600000)
    queue_size: int = Field(default=10, ge=1, le=10000)
    deadband: float = Field(default=0, ge=0)
    mode: Literal["Disabled", "Sampling", "Reporting"] = "Reporting"


class SubscriptionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    publishing_interval_ms: float = Field(default=500, ge=50, le=3600000)
    lifetime_count: int = Field(default=10000, ge=3, le=100000)
    keepalive_count: int = Field(default=10, ge=1, le=10000)
    enabled: bool = True
    items: list[MonitoredItem] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def bounds(self):
        if self.lifetime_count < self.keepalive_count * 3:
            raise ValueError("生命周期计数须至少为保活计数的三倍")
        keys = {(item.namespace_uri, item.node_id) for item in self.items}
        if len(keys) != len(self.items):
            raise ValueError("同一订阅中监控项不能重复")
        return self


class SubscriptionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subscriptions: list[SubscriptionConfig] = Field(default_factory=list, max_length=100)
    reconnect: bool = True
    retry_min_s: float = Field(default=1, ge=0.1, le=60)
    retry_max_s: float = Field(default=30, ge=1, le=300)

    @model_validator(mode="after")
    def unique(self):
        if len({item.id for item in self.subscriptions}) != len(self.subscriptions):
            raise ValueError("订阅名称不能重复")
        if self.retry_min_s > self.retry_max_s:
            raise ValueError("最小重连间隔不能大于最大间隔")
        return self


class SecurityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["None", "Sign", "SignAndEncrypt"] = "None"
    application_uri: str = Field(default="urn:ems-simulate:application", min_length=1, max_length=255)
    advertised_host: str | None = Field(default=None, max_length=255)
    identity: Literal["anonymous", "username"] = "anonymous"
    username: str = Field(default="", max_length=128)
    allow_anonymous: bool = False
    certificate: str | None = Field(default=None, max_length=32768)
    trusted: list[str] = Field(default_factory=list, max_length=100)
    users: list[dict[str, str]] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_identity(self):
        if self.identity == "username" and (not self.username or self.mode != "SignAndEncrypt"):
            raise ValueError("用户名身份需要用户名和 SignAndEncrypt")
        if any(
            set(user) != {"username", "role"}
            or user["role"] not in {"viewer", "operator"}
            or not 1 <= len(user["username"]) <= 64
            for user in self.users
        ):
            raise ValueError("用户角色只能为 viewer 或 operator")
        if len({user["username"] for user in self.users}) != len(self.users):
            raise ValueError("用户名重复")
        if self.mode != "None" and not self.certificate:
            raise ValueError("请先生成应用证书")
        return self


class HistoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    nodes: list[str] = Field(default_factory=list, max_length=1000)
    retention_days: int = Field(default=7, ge=1, le=3650)
    max_values: int = Field(default=100000, ge=1, le=10000000)

    @model_validator(mode="after")
    def unique_nodes(self):
        if len(set(self.nodes)) != len(self.nodes):
            raise ValueError("历史节点不能重复")
        return self


class EventsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    source_node: str = Field(default="i=2253", min_length=1, max_length=512)
    event_type: str = Field(default="i=2041", min_length=1, max_length=512)
    minimum_severity: int = Field(default=0, ge=0, le=1000)
