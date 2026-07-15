"""IEC 61850 图形化建模 REST API。"""

from fastapi import APIRouter, Query
from fastapi.responses import Response

from src.modeling.service import Iec61850ModelingService
from src.web.api.modeling.schemas import (
    NodeCreateRequest,
    NodeUpdateRequest,
    ProjectCreateRequest,
    PublishRequest,
    VersionCreateRequest,
)
from src.web.api.schemas import BaseResponse

router = APIRouter(prefix="/api/modeling", tags=["IEC 61850 Modeling"])
service = Iec61850ModelingService()


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


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> BaseResponse:
    return BaseResponse.success(service.get_project(project_id))


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> BaseResponse:
    service.delete_project(project_id)
    return BaseResponse.success(message="模型工程已删除")


@router.get("/projects/{project_id}/tree")
def get_tree(project_id: str) -> BaseResponse:
    return BaseResponse.success(service.get_tree(project_id))


@router.post("/projects/{project_id}/nodes")
def create_node(project_id: str, request: NodeCreateRequest) -> BaseResponse:
    return BaseResponse.success(service.create_node(project_id, request.model_dump()), "节点创建成功")


@router.get("/projects/{project_id}/nodes/{node_id}")
def get_node(project_id: str, node_id: str) -> BaseResponse:
    return BaseResponse.success(service.get_node(project_id, node_id))


@router.patch("/projects/{project_id}/nodes/{node_id}")
def update_node(project_id: str, node_id: str, request: NodeUpdateRequest) -> BaseResponse:
    payload = request.model_dump(exclude_unset=True)
    return BaseResponse.success(service.update_node(project_id, node_id, payload), "节点已保存")


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
def preview_scl(project_id: str) -> BaseResponse:
    return BaseResponse.success(service.generate_scl(project_id))


@router.get("/projects/{project_id}/scl-download")
def download_scl(project_id: str) -> Response:
    artifact = service.generate_scl(project_id)
    return Response(
        content=artifact["xml"].encode("utf-8"),
        media_type="application/xml; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{artifact["filename"]}"'},
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
