"""Application settings API."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from src.config.storage import StoragePaths, get_storage_settings
from src.web.api.exceptions import ValidationError
from src.web.api.schemas import BaseResponse

settings_router = APIRouter(prefix="/api/settings", tags=["设置"])


class StorageSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_directory: str
    point_table_cache_directory: str
    iec61850_model_cache_directory: str
    iec61850_file_cache_directory: str
    iec61850_temp_directory: str


def _storage_payload(paths: StoragePaths) -> dict:
    settings = get_storage_settings()
    return {
        "paths": paths.to_dict(),
        "defaults": settings.defaults().to_dict(),
        "status": settings.directory_status(paths),
    }


@settings_router.get("/storage", response_model=BaseResponse)
async def get_storage_configuration():
    settings = get_storage_settings()
    return BaseResponse(data=_storage_payload(settings.get()))


@settings_router.delete("/storage/{field_name}/contents", response_model=BaseResponse)
async def clear_storage_directory(field_name: str):
    settings = get_storage_settings()
    try:
        directory = settings.clear_directory(field_name)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return BaseResponse(data={"path": str(directory)}, message="目录数据已清空")


@settings_router.put("/storage", response_model=BaseResponse)
async def update_storage_configuration(body: StorageSettingsUpdate, request: Request):
    settings = get_storage_settings()
    try:
        paths, changed_fields = settings.update(body.model_dump())
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    # The SCL manager holds its base path. Recreate it lazily so new uploads use
    # the selected model-cache directory without restarting the whole service.
    if "iec61850_model_cache_directory" in changed_fields:
        request.app.state.scl_file_manager = None

    payload = _storage_payload(paths)
    payload["changed_fields"] = changed_fields
    payload["restart_required"] = "data_directory" in changed_fields
    return BaseResponse(data=payload, message="存储设置已保存")
