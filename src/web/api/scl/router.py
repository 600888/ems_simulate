"""SCL 文件管理 - Web API

CRUD + 上传/浏览/导入/校验 端点。

端点列表:
  POST   /scl/upload          — 上传 SCL 文件
  GET    /scl/list            — 列出所有 SCL 文件
  GET    /scl/detail          — 获取文件详情
  DELETE /scl/delete          — 删除 SCL 文件
  POST   /scl/preview         — 预览 (解析+转换，不持久化)
  POST   /scl/validate        — 校验 SCL 文件
  POST   /scl/parse           — 解析 SCL 文件 (返回结构化模型)
  POST   /scl/import-points   — 从 SCL 文件导入测点到数据库
  POST   /scl/import-goose    — 从 SCL 文件导入 GOOSE 配置
  POST   /scl/import-full     — 完整导入 (测点 + GOOSE + Report)
  GET    /scl/browse-tree     — 浏览 SCL 文件结构树
  POST   /scl/diff            — 对比两个 SCL 文件
  GET    /scl/ied-list        — 获取 SCL 文件中的 IED 列表
"""
from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, File, Form, Query, Request, UploadFile

from src.web.api.schemas import BaseResponse
from src.web.log import log

router = APIRouter(prefix="/api/scl", tags=["SCL 文件管理"])


def _get_file_manager(request: Request):
    """从 app.state 获取或创建 SclFileManager"""
    from src.proto.iec61850.plugins.scl.service.file_manager import SclFileManager

    if not hasattr(request.app.state, "scl_file_manager"):
        request.app.state.scl_file_manager = SclFileManager()
    return request.app.state.scl_file_manager


def _get_import_service(request: Request):
    """从 app.state 获取或创建 SclImportService"""
    from src.proto.iec61850.plugins.scl.service.import_service import SclImportService

    if not hasattr(request.app.state, "scl_import_service"):
        request.app.state.scl_import_service = SclImportService()
    return request.app.state.scl_import_service


# ===== 文件管理 =====


@router.post("/upload", response_model=BaseResponse)
async def upload_scl_file(request: Request, file: UploadFile = File(...)):
    """上传 SCL 文件到服务器"""
    try:
        fm = _get_file_manager(request)
        content = await file.read()
        file_path = fm.save_uploaded_file(file.filename, content)
        return BaseResponse(
            message="文件上传成功",
            data={"filename": os.path.basename(file_path), "file_path": file_path, "size": len(content)},
        )
    except ValueError as e:
        return BaseResponse(code=400, message=str(e))
    except Exception as e:
        log.error(f"上传 SCL 文件失败: {e}")
        return BaseResponse(code=500, message=f"上传失败: {e}")


@router.get("/list", response_model=BaseResponse)
async def list_scl_files(request: Request):
    """列出所有 SCL 文件"""
    try:
        fm = _get_file_manager(request)
        files = [f.to_dict() for f in fm.list_files()]
        return BaseResponse(data=files)
    except Exception as e:
        log.error(f"列出 SCL 文件失败: {e}")
        return BaseResponse(code=500, message=f"获取文件列表失败: {e}")


@router.get("/detail", response_model=BaseResponse)
async def get_scl_detail(request: Request, filename: str = Query(...)):
    """获取 SCL 文件详情"""
    try:
        fm = _get_file_manager(request)
        file_path = fm.get_file_path(filename)
        if not file_path:
            return BaseResponse(code=404, message=f"文件不存在: {filename}")

        # 解析获取 IED 摘要

        service = _get_import_service(request)
        result = service.preview_file(file_path)

        stat = os.stat(file_path)
        return BaseResponse(
            data={
                "filename": filename,
                "file_path": file_path,
                "file_size": stat.st_size,
                "ied_name": result.ied_name,
                "point_counts": {
                    "yc": len(result.points.yc_points),
                    "yx": len(result.points.yx_points),
                    "yk": len(result.points.yk_points),
                    "yt": len(result.points.yt_points),
                },
                "gse_control_count": len(result.goose.gse_controls),
                "report_control_count": len(result.reports.report_controls),
                "validation": {
                    "is_valid": result.validation.is_valid,
                    "error_count": result.validation.error_count,
                    "warning_count": result.validation.warning_count,
                },
            }
        )
    except Exception as e:
        log.error(f"获取 SCL 文件详情失败: {e}")
        return BaseResponse(code=500, message=f"获取详情失败: {e}")


@router.delete("/delete", response_model=BaseResponse)
async def delete_scl_file(request: Request, filename: str = Query(...)):
    """删除 SCL 文件"""
    try:
        fm = _get_file_manager(request)
        if fm.delete_file(filename):
            return BaseResponse(message="文件删除成功")
        return BaseResponse(code=404, message=f"文件不存在: {filename}")
    except Exception as e:
        log.error(f"删除 SCL 文件失败: {e}")
        return BaseResponse(code=500, message=f"删除失败: {e}")


# ===== 解析与预览 =====


@router.post("/preview", response_model=BaseResponse)
async def preview_scl_file(request: Request, file: UploadFile = File(...)):
    """预览 SCL 文件 (上传临时文件，解析后删除)"""
    suffix = os.path.splitext(file.filename)[1] or ".icd"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        service = _get_import_service(request)
        result = service.preview_file(tmp_path)
        return BaseResponse(message="预览成功", data=result.to_dict())
    except Exception as e:
        log.error(f"预览 SCL 文件失败: {e}")
        return BaseResponse(code=500, message=f"预览失败: {e}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/validate", response_model=BaseResponse)
async def validate_scl_file(request: Request, filename: str = Form(...)):
    """校验已上传的 SCL 文件"""
    try:
        fm = _get_file_manager(request)
        file_path = fm.get_file_path(filename)
        if not file_path:
            return BaseResponse(code=404, message=f"文件不存在: {filename}")

        service = _get_import_service(request)
        result = service.import_file(file_path, validate=True)
        return BaseResponse(
            data={
                "is_valid": result.validation.is_valid,
                "error_count": result.validation.error_count,
                "warning_count": result.validation.warning_count,
                "issues": [str(i) for i in result.validation.issues],
            }
        )
    except Exception as e:
        log.error(f"校验 SCL 文件失败: {e}")
        return BaseResponse(code=500, message=f"校验失败: {e}")


@router.post("/parse", response_model=BaseResponse)
async def parse_scl_file(request: Request, filename: str = Form(...)):
    """解析 SCL 文件 (返回结构化模型摘要)"""
    try:
        fm = _get_file_manager(request)
        file_path = fm.get_file_path(filename)
        if not file_path:
            return BaseResponse(code=404, message=f"文件不存在: {filename}")

        from src.proto.iec61850.plugins.scl.parser.scl_parser import SclParser

        parser = SclParser()
        doc = parser.parse_file(file_path)

        # 返回结构化摘要 (不包含完整树，太大会截断)
        ied_list = []
        for ied in doc.ieds:
            ld_count = sum(len(ap.server.ldevices) for ap in ied.access_points if ap.server)
            ied_list.append({
                "name": ied.name,
                "desc": ied.desc,
                "manufacturer": ied.manufacturer,
                "ld_count": ld_count,
            })

        return BaseResponse(
            data={
                "header": {
                    "id": doc.header.id,
                    "version": doc.header.version,
                    "revision": doc.header.revision,
                    "tool_id": doc.header.tool_id,
                },
                "ieds": ied_list,
                "type_counts": {
                    "l_node_types": len(doc.data_type_templates.ln_node_types),
                    "do_types": len(doc.data_type_templates.do_types),
                    "da_types": len(doc.data_type_templates.da_types),
                    "enum_types": len(doc.data_type_templates.enum_types),
                },
            }
        )
    except Exception as e:
        log.error(f"解析 SCL 文件失败: {e}")
        return BaseResponse(code=500, message=f"解析失败: {e}")


# ===== 导入 =====


@router.post("/import-points", response_model=BaseResponse)
async def import_points_from_scl(
    request: Request,
    channel_id: int = Form(...),
    filename: str = Form(...),
):
    """从已上传的 SCL 文件导入测点到数据库"""
    try:
        fm = _get_file_manager(request)
        file_path = fm.get_file_path(filename)
        if not file_path:
            return BaseResponse(code=404, message=f"文件不存在: {filename}")

        # 使用 SclImportService 解析
        service = _get_import_service(request)
        result = service.import_file(file_path)

        if not result.is_valid:
            return BaseResponse(
                code=400,
                message=f"校验失败: {result.validation.error_count} 个错误",
                data=result.to_dict()["validation"],
            )

        # 持久化到数据库 (复用 IcdPointImporter 的存储逻辑)
        from src.tools.icd_point_importer import IcdPointImporter

        importer = IcdPointImporter(channel_id=channel_id)
        # 使用 SclImportService 解析的结果，委托 IcdPointImporter 存储
        yc_count, yx_count, yk_count, yt_count = importer.import_from_icd(file_path)

        # 更新 IED 名称
        if result.ied_name:
            try:
                from src.data.service.channel_service import ChannelService
                ChannelService.update_channel(channel_id, model_name=result.ied_name)
            except Exception as e:
                log.warning(f"更新 IED 名称失败: {e}")

        return BaseResponse(
            message="测点导入成功",
            data={
                "yc_count": yc_count,
                "yx_count": yx_count,
                "yk_count": yk_count,
                "yt_count": yt_count,
                "total": yc_count + yx_count + yk_count + yt_count,
                "ied_name": result.ied_name,
            },
        )
    except Exception as e:
        log.error(f"从 SCL 导入测点失败: {e}")
        return BaseResponse(code=500, message=f"导入失败: {e}")


@router.post("/import-goose", response_model=BaseResponse)
async def import_goose_from_scl(
    request: Request,
    channel_id: int = Form(...),
    filename: str = Form(...),
    interface: str = Form("eth0"),
):
    """从已上传的 SCL 文件导入 GOOSE 配置"""
    try:
        fm = _get_file_manager(request)
        file_path = fm.get_file_path(filename)
        if not file_path:
            return BaseResponse(code=404, message=f"文件不存在: {filename}")

        service = _get_import_service(request)
        result = service.import_file(file_path)

        # 构建 GOOSE 响应 (兼容 import_goose_from_icd 格式)
        publishers = [gse.to_publisher_dict(interface) for gse in result.goose.gse_controls]
        subscriptions = [gse.to_subscription_dict() for gse in result.goose.gse_controls]

        return BaseResponse(
            message="GOOSE 配置解析成功",
            data={
                "publishers": publishers,
                "subscriptions": subscriptions,
                "pure_datasets": result.goose.pure_datasets,
                "report_controls": [
                    {
                        "ld_inst": rc.ld_inst,
                        "name": rc.name,
                        "rcb_type": rc.rcb_type,
                        "rpt_id": rc.rpt_id,
                        "dat_set": rc.dat_set,
                        "data_set_ref": rc.data_set_ref,
                        "conf_rev": rc.conf_rev,
                        "buf_time": rc.buf_time,
                        "intg_period": rc.intg_period,
                        "ln_name": rc.ln_name,
                        "trg_ops": rc.trg_ops,
                        "opt_fields": rc.opt_fields,
                        "entries": rc.entries,
                    }
                    for rc in result.reports.report_controls
                ],
                "summary": {
                    "gse_control_count": len(result.goose.gse_controls),
                    "gse_controls": [
                        {
                            "go_cb_ref": g.go_cb_ref,
                            "go_id": g.name,
                            "app_id": g.app_id or g.gse_app_id,
                            "dat_set": g.dat_set,
                            "conf_rev": g.conf_rev,
                            "mac_address": g.mac_address,
                            "dataset_member_count": len(g.dataset_members),
                        }
                        for g in result.goose.gse_controls
                    ],
                },
            },
        )
    except Exception as e:
        log.error(f"从 SCL 导入 GOOSE 失败: {e}")
        return BaseResponse(code=500, message=f"导入失败: {e}")


@router.post("/import-full", response_model=BaseResponse)
async def import_full_from_scl(
    request: Request,
    channel_id: int = Form(...),
    filename: str = Form(...),
    interface: str = Form("eth0"),
):
    """完整导入 SCL 文件 (测点 + GOOSE + Report)"""
    try:
        fm = _get_file_manager(request)
        file_path = fm.get_file_path(filename)
        if not file_path:
            return BaseResponse(code=404, message=f"文件不存在: {filename}")

        service = _get_import_service(request)
        result = service.import_file(file_path)

        # 使用 IcdPointImporter 存储测点
        from src.tools.icd_point_importer import IcdPointImporter

        importer = IcdPointImporter(channel_id=channel_id)
        yc_count, yx_count, yk_count, yt_count = importer.import_from_icd(file_path)

        # 更新 IED 名称
        if result.ied_name:
            try:
                from src.data.service.channel_service import ChannelService
                ChannelService.update_channel(channel_id, model_name=result.ied_name)
            except Exception:
                pass

        # 构建 GOOSE 响应
        goose_data = result.to_dict()

        return BaseResponse(
            message="完整导入成功",
            data={
                "yc_count": yc_count,
                "yx_count": yx_count,
                "yk_count": yk_count,
                "yt_count": yt_count,
                "total": yc_count + yx_count + yk_count + yt_count,
                "goose": goose_data.get("goose"),
                "report_controls": goose_data.get("report_controls", []),
                "ied_name": result.ied_name,
            },
        )
    except Exception as e:
        log.error(f"完整导入 SCL 文件失败: {e}")
        return BaseResponse(code=500, message=f"导入失败: {e}")


# ===== 浏览 =====


@router.get("/browse-tree", response_model=BaseResponse)
async def browse_scl_tree(request: Request, filename: str = Query(...)):
    """浏览 SCL 文件结构树"""
    try:
        fm = _get_file_manager(request)
        file_path = fm.get_file_path(filename)
        if not file_path:
            return BaseResponse(code=404, message=f"文件不存在: {filename}")

        from src.proto.iec61850.plugins.scl.parser.scl_parser import SclParser

        parser = SclParser()
        doc = parser.parse_file(file_path)

        # 构建树形结构
        tree = {"header": {"id": doc.header.id, "version": doc.header.version}, "ieds": []}

        for ied in doc.ieds:
            ied_node = {"name": ied.name, "desc": ied.desc, "access_points": []}
            for ap in ied.access_points:
                ap_node = {"name": ap.name, "ldevices": []}
                if ap.server:
                    for ld in ap.server.ldevices:
                        ld_node = {"inst": ld.inst, "desc": ld.desc, "logical_nodes": []}
                        all_lns = ([ld.ln0] + ld.lns) if ld.ln0 else ld.lns
                        for ln in all_lns:
                            ln_node = {
                                "ln_name": ln.ln_name,
                                "ln_class": ln.ln_class,
                                "ln_type": ln.ln_type,
                                "do_count": len(ln.dois),
                                "dataset_count": len(ln.datasets),
                                "gse_control_count": len(ln.gse_controls),
                                "report_control_count": len(ln.report_controls),
                            }
                            ld_node["logical_nodes"].append(ln_node)
                        ap_node["ldevices"].append(ld_node)
                ied_node["access_points"].append(ap_node)
            tree["ieds"].append(ied_node)

        return BaseResponse(data=tree)
    except Exception as e:
        log.error(f"浏览 SCL 文件树失败: {e}")
        return BaseResponse(code=500, message=f"浏览失败: {e}")


# ===== 对比 =====


@router.post("/diff", response_model=BaseResponse)
async def diff_scl_files(
    request: Request,
    filename_a: str = Form(...),
    filename_b: str = Form(...),
):
    """对比两个 SCL 文件"""
    try:
        fm = _get_file_manager(request)

        path_a = fm.get_file_path(filename_a)
        path_b = fm.get_file_path(filename_b)
        if not path_a:
            return BaseResponse(code=404, message=f"文件不存在: {filename_a}")
        if not path_b:
            return BaseResponse(code=404, message=f"文件不存在: {filename_b}")

        from src.proto.iec61850.plugins.scl.parser.scl_parser import SclParser

        parser = SclParser()
        doc_a = parser.parse_file(path_a)
        doc_b = parser.parse_file(path_b)

        # 简单对比: IED 名称、类型数量、测点数量
        diff = {
            "file_a": filename_a,
            "file_b": filename_b,
            "ied_names": {
                "a": [ied.name for ied in doc_a.ieds],
                "b": [ied.name for ied in doc_b.ieds],
                "added": [ied.name for ied in doc_b.ieds if ied.name not in {i.name for i in doc_a.ieds}],
                "removed": [ied.name for ied in doc_a.ieds if ied.name not in {i.name for i in doc_b.ieds}],
            },
            "type_counts": {
                "a": {
                    "l_node_types": len(doc_a.data_type_templates.ln_node_types),
                    "do_types": len(doc_a.data_type_templates.do_types),
                    "da_types": len(doc_a.data_type_templates.da_types),
                    "enum_types": len(doc_a.data_type_templates.enum_types),
                },
                "b": {
                    "l_node_types": len(doc_b.data_type_templates.ln_node_types),
                    "do_types": len(doc_b.data_type_templates.do_types),
                    "da_types": len(doc_b.data_type_templates.da_types),
                    "enum_types": len(doc_b.data_type_templates.enum_types),
                },
            },
        }

        # 测点数量对比
        from src.proto.iec61850.plugins.scl.transformer.point_transformer import SclPointTransformer

        pts_a = SclPointTransformer(doc_a).transform()
        pts_b = SclPointTransformer(doc_b).transform()
        diff["point_counts"] = {
            "a": pts_a.to_count_tuple(),
            "b": pts_b.to_count_tuple(),
        }

        return BaseResponse(data=diff)
    except Exception as e:
        log.error(f"对比 SCL 文件失败: {e}")
        return BaseResponse(code=500, message=f"对比失败: {e}")


# ===== IED 列表 =====


@router.get("/ied-list", response_model=BaseResponse)
async def get_scl_ied_list(request: Request, filename: str = Query(...)):
    """获取 SCL 文件中的 IED 列表"""
    try:
        fm = _get_file_manager(request)
        file_path = fm.get_file_path(filename)
        if not file_path:
            return BaseResponse(code=404, message=f"文件不存在: {filename}")

        from src.proto.iec61850.plugins.scl.parser.scl_parser import SclParser

        parser = SclParser()
        doc = parser.parse_file(file_path)

        ieds = [
            {
                "name": ied.name,
                "desc": ied.desc,
                "manufacturer": ied.manufacturer,
                "config_revision": ied.config_revision,
                "access_point_count": len(ied.access_points),
            }
            for ied in doc.ieds
        ]

        return BaseResponse(data=ieds)
    except Exception as e:
        log.error(f"获取 IED 列表失败: {e}")
        return BaseResponse(code=500, message=f"获取失败: {e}")
