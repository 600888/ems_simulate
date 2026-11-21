"""Network diagnostic tools."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from src.tools.subnet_scan import SubnetScanner
from src.web.api.exceptions import NotFoundError, ValidationError
from src.web.api.schemas import BaseResponse

tools_router = APIRouter(prefix="/api/tools", tags=["工具"])


class SubnetScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subnet: str = Field(min_length=1, max_length=64)
    timeout_ms: int = Field(default=1000, ge=200, le=5000)


def _scanner(request: Request) -> SubnetScanner:
    return request.app.state.subnet_scanner


def _find_scan(request: Request, scan_id: str):
    scan = _scanner(request).scans.get(scan_id)
    if scan is None:
        raise NotFoundError("探测任务不存在或已过期，请重新开始探测")
    return scan


@tools_router.post("/subnet-scans", response_model=BaseResponse)
async def start_subnet_scan(body: SubnetScanRequest, request: Request):
    try:
        scan = _scanner(request).start(body.subnet, body.timeout_ms)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return BaseResponse(data=scan.snapshot())


@tools_router.get("/subnet-scans/{scan_id}", response_model=BaseResponse)
async def get_subnet_scan(scan_id: str, request: Request):
    return BaseResponse(data=_find_scan(request, scan_id).snapshot())


@tools_router.delete("/subnet-scans/{scan_id}", response_model=BaseResponse)
async def stop_subnet_scan(scan_id: str, request: Request):
    scan = _find_scan(request, scan_id)
    await _scanner(request).cancel(scan)
    return BaseResponse(data=scan.snapshot())
