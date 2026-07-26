"""IEC 61850 建模 API 请求模型。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class IedSeed(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=64)
    manufacturer: str = Field(default="", max_length=128)
    type: str = Field(default="", max_length=128)
    config_version: str = Field(default="1.0", alias="configVersion", max_length=64)
    desc: str = Field(default="", max_length=256)


class LogicalDeviceSeed(BaseModel):
    inst: str = Field(min_length=1, max_length=64)
    desc: str = Field(default="", max_length=256)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=512)
    file_type: Literal["ICD", "CID", "SCD"] = "ICD"
    standard_version: str = Field(default="IEC 61850 Ed2.1", max_length=32)
    namespace: str = Field(default="", max_length=256)
    ied: IedSeed
    access_point_name: str = Field(default="AP1", min_length=1, max_length=64)
    logical_devices: list[LogicalDeviceSeed] = Field(default_factory=lambda: [LogicalDeviceSeed(inst="LD0")])
    profiles: list[str] = Field(default_factory=lambda: ["generic-ied-ed2"])


class NodeCreateRequest(BaseModel):
    parent_id: str
    kind: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    attributes: dict[str, Any] = Field(default_factory=dict)
    sort_order: int | None = None


class NodeUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    attributes: dict[str, Any] | None = None
    sort_order: int | None = None
    expected_revision: int | None = Field(default=None, ge=1)


class CdcTemplateApplyRequest(BaseModel):
    template_id: str = Field(min_length=1, max_length=128)


class DataSetMembersCreateRequest(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list, max_length=5000)
    ordered_candidate_ids: list[str] | None = Field(default=None, max_length=5000)


class DataSetMemberRepairRequest(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=512)


class InstanceOverrideCreateRequest(BaseModel):
    template_path: str = Field(min_length=1, max_length=1024)
    expected_project_revision: int | None = Field(default=None, ge=1)


class LNodeDoTemplateRequest(BaseModel):
    name_pattern: str = Field(min_length=1, max_length=128)
    start_index: int = Field(default=1, ge=0, le=99999999)
    quantity: int = Field(default=10, ge=1, le=500)
    index_width: int = Field(default=3, ge=1, le=8)
    do_type_ref: str = Field(min_length=1, max_length=128)
    expected_project_revision: int | None = Field(default=None, ge=1)


class VersionCreateRequest(BaseModel):
    label: str = Field(default="", max_length=128)
    description: str = Field(default="", max_length=512)


class PublishRequest(BaseModel):
    label: str = Field(default="", max_length=128)
    description: str = Field(default="", max_length=512)
