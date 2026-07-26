"""IEC 61850 图形化建模 REST API。"""

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import Response

from src.modeling.jobs import ModelingJobManager
from src.modeling.service import Iec61850ModelingService
from src.web.api.exceptions import ConflictError, NotFoundError, ValidationError
from src.web.api.modeling.schemas import (
    CdcTemplateApplyRequest,
    DataSetMemberRepairRequest,
    DataSetMembersCreateRequest,
    NodeCreateRequest,
    NodeUpdateRequest,
    ProjectCreateRequest,
    PublishRequest,
    VersionCreateRequest,
)
from src.web.api.schemas import BaseResponse

router = APIRouter(prefix="/api/modeling", tags=["IEC 61850 Modeling"])
service = Iec61850ModelingService()
job_manager = ModelingJobManager()
MAX_SCL_UPLOAD_BYTES = 25 * 1024 * 1024


async def _read_scl_upload(file: UploadFile) -> bytes:
    content = await file.read(MAX_SCL_UPLOAD_BYTES + 1)
    if len(content) > MAX_SCL_UPLOAD_BYTES:
        raise ValidationError("SCL 文件超过 25 MiB 导入上限")
    return content


@router.get("/projects")
def list_projects(
    keyword: str = "",
    status: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> BaseResponse:
    return BaseResponse.success(service.list_projects(keyword=keyword, status=status, page=page, page_size=page_size))


@router.post("/projects")
def create_project(request: ProjectCreateRequest) -> BaseResponse:
    return BaseResponse.success(service.create_project(request.model_dump(by_alias=True)), "模型工程创建成功")


@router.get("/profiles")
def list_profiles() -> BaseResponse:
    return BaseResponse.success(service.list_profiles())


@router.get("/standards")
def list_standards() -> BaseResponse:
    return BaseResponse.success(service.list_standards())


@router.get("/file-variants")
def list_file_variants() -> BaseResponse:
    return BaseResponse.success(service.list_file_variants())


@router.get("/cdc-templates")
def list_cdc_templates() -> BaseResponse:
    return BaseResponse.success(service.list_cdc_templates())


@router.post("/projects/import-preview")
async def preview_import(file: UploadFile = File(...)) -> BaseResponse:
    content = await _read_scl_upload(file)
    return BaseResponse.success(service.preview_import(content, filename=file.filename or "model.icd"))


@router.post("/jobs/import-preview")
async def create_import_preview_job(file: UploadFile = File(...)) -> BaseResponse:
    content = await _read_scl_upload(file)
    filename = file.filename or "model.icd"

    def run(progress, cancel_check):
        return service.preview_import(
            content,
            filename=filename,
            progress=progress,
            cancel_check=cancel_check,
        )

    try:
        job = job_manager.submit("IMPORT_PREVIEW", run, input_size=len(content))
    except RuntimeError as exc:
        raise ConflictError(str(exc)) from exc
    return BaseResponse.success(job)


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> BaseResponse:
    job = job_manager.get(job_id)
    if job is None:
        raise NotFoundError("建模后台任务不存在或已过期")
    return BaseResponse.success(job)


@router.delete("/jobs/{job_id}")
def cancel_job(job_id: str) -> BaseResponse:
    job = job_manager.cancel(job_id)
    if job is None:
        raise NotFoundError("建模后台任务不存在或已过期")
    return BaseResponse.success(job, "已请求取消建模任务")


@router.post("/projects/import")
async def import_project(
    file: UploadFile = File(...),
    code: str = Form(default=""),
    name: str = Form(default=""),
) -> BaseResponse:
    content = await _read_scl_upload(file)
    return BaseResponse.success(
        service.import_scl(content, filename=file.filename or "model.icd", code=code, name=name),
        "SCL 模型导入成功",
    )


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> BaseResponse:
    return BaseResponse.success(service.get_project(project_id))


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> BaseResponse:
    service.delete_project(project_id)
    return BaseResponse.success(message="模型工程已删除")


@router.get("/projects/{project_id}/tree")
def get_tree(
    project_id: str,
    compact: bool = False,
    max_depth: int | None = None,
    focus_id: str = "",
    keyword: str = "",
    kind: str = "",
) -> BaseResponse:
    return BaseResponse.success(
        service.get_tree(
            project_id,
            compact=compact,
            max_depth=max_depth,
            focus_id=focus_id,
            keyword=keyword,
            kind=kind,
        )
    )


@router.post("/projects/{project_id}/nodes")
def create_node(project_id: str, request: NodeCreateRequest) -> BaseResponse:
    return BaseResponse.success(service.create_node(project_id, request.model_dump()), "节点创建成功")


@router.get("/projects/{project_id}/nodes/{node_id}")
def get_node(project_id: str, node_id: str, include_children: bool = False) -> BaseResponse:
    return BaseResponse.success(service.get_node(project_id, node_id, include_children=include_children))


@router.get("/projects/{project_id}/tree-kinds")
def get_tree_kinds(project_id: str) -> BaseResponse:
    return BaseResponse.success(service.get_tree_kinds(project_id))


@router.patch("/projects/{project_id}/nodes/{node_id}")
def update_node(project_id: str, node_id: str, request: NodeUpdateRequest) -> BaseResponse:
    payload = request.model_dump(exclude_unset=True)
    return BaseResponse.success(service.update_node(project_id, node_id, payload), "节点已保存")


@router.post("/projects/{project_id}/nodes/{node_id}/apply-cdc-template")
def apply_cdc_template(project_id: str, node_id: str, request: CdcTemplateApplyRequest) -> BaseResponse:
    return BaseResponse.success(
        service.apply_cdc_template(project_id, node_id, request.template_id),
        "CDC 数据属性模板已应用",
    )


@router.get("/projects/{project_id}/datasets/{dataset_id}/member-candidates")
def get_dataset_member_candidates(project_id: str, dataset_id: str) -> BaseResponse:
    return BaseResponse.success(service.get_dataset_member_candidates(project_id, dataset_id))


@router.post("/projects/{project_id}/datasets/{dataset_id}/members")
def create_dataset_members(
    project_id: str,
    dataset_id: str,
    request: DataSetMembersCreateRequest,
) -> BaseResponse:
    return BaseResponse.success(
        service.create_dataset_members(
            project_id,
            dataset_id,
            request.candidate_ids,
            request.ordered_candidate_ids,
        ),
        "DataSet 成员已保存",
    )


@router.patch("/projects/{project_id}/datasets/{dataset_id}/members/{fcda_id}")
def repair_dataset_member(
    project_id: str,
    dataset_id: str,
    fcda_id: str,
    request: DataSetMemberRepairRequest,
) -> BaseResponse:
    return BaseResponse.success(
        service.repair_dataset_member(
            project_id,
            dataset_id,
            fcda_id,
            request.candidate_id,
        ),
        "FCDA 引用已修复",
    )


@router.get("/projects/{project_id}/nodes/{node_id}/delete-impact")
def get_delete_impact(project_id: str, node_id: str) -> BaseResponse:
    return BaseResponse.success(service.get_delete_impact(project_id, node_id))


@router.delete("/projects/{project_id}/nodes/{node_id}")
def delete_node(project_id: str, node_id: str, force: bool = False) -> BaseResponse:
    return BaseResponse.success(service.delete_node(project_id, node_id, force=force), "节点已删除")


@router.post("/projects/{project_id}/validate")
def validate_project(project_id: str) -> BaseResponse:
    return BaseResponse.success(service.validate_project(project_id), "模型校验完成")


@router.get("/projects/{project_id}/versions")
def list_versions(project_id: str) -> BaseResponse:
    return BaseResponse.success(service.list_versions(project_id))


@router.post("/projects/{project_id}/versions")
def create_version(project_id: str, request: VersionCreateRequest) -> BaseResponse:
    return BaseResponse.success(
        service.create_version(project_id, label=request.label, description=request.description),
        "版本快照创建成功",
    )


@router.post("/projects/{project_id}/versions/{version_id}/restore")
def restore_version(project_id: str, version_id: str) -> BaseResponse:
    return BaseResponse.success(service.restore_version(project_id, version_id), "模型版本已恢复")


@router.delete("/projects/{project_id}/versions/{version_id}")
def delete_version(project_id: str, version_id: str) -> BaseResponse:
    service.delete_version(project_id, version_id)
    return BaseResponse.success(message="版本快照已删除")


@router.get("/projects/{project_id}/scl-preview")
def preview_scl(project_id: str, file_type: str = "") -> BaseResponse:
    return BaseResponse.success(service.generate_scl(project_id, file_type=file_type or None))


@router.get("/projects/{project_id}/scl-download")
def download_scl(project_id: str, file_type: str = "") -> Response:
    artifact = service.generate_scl(project_id, file_type=file_type or None)
    return Response(
        content=artifact["xml"].encode("utf-8"),
        media_type="application/xml; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{artifact["filename"]}"'},
    )


@router.get("/projects/{project_id}/artifacts")
def preview_artifacts(project_id: str, file_type: str = "") -> BaseResponse:
    bundle = service.generate_artifact_bundle(project_id, file_type=file_type or None)
    return BaseResponse.success({key: bundle[key] for key in ("filename", "size", "revision", "manifest", "artifacts")})


@router.get("/projects/{project_id}/artifacts-download")
def download_artifacts(project_id: str, file_type: str = "") -> Response:
    bundle = service.generate_artifact_bundle(project_id, file_type=file_type or None)
    return Response(
        content=bundle["content"],
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{bundle["filename"]}"'},
    )


@router.post("/projects/{project_id}/publish")
def publish_project(project_id: str, request: PublishRequest) -> BaseResponse:
    return BaseResponse.success(
        service.publish_project(project_id, label=request.label, description=request.description),
        "模型发布成功",
    )


@router.get("/node-kinds/{kind}/schema")
def get_node_schema(kind: str) -> BaseResponse:
    return BaseResponse.success(service.get_kind_schema(kind))
