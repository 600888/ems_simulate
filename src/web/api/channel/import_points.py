"""通道管理 - 点表导入路由

ICD/SCD/CID 文件统一导入:
- MMS 测点 (遥测/遥信/遥控/遥调)
- GOOSE 配置 (Publisher/Subscriber)
"""

import asyncio
import os
import tempfile
from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile

from src.config.storage import get_storage_path
from src.data.service.channel_service import ChannelService
from src.enums.modbus_def import ProtocolType
from src.tools.excel_point_importer import ExcelPointImporter
from src.web.api.channel.helpers import reload_device_instance
from src.web.api.channel.protocol_guards import require_iec61850_channel, require_tabular_point_channel
from src.web.api.exceptions import ValidationError
from src.web.api.schemas import BaseResponse
from src.web.log import log

router = APIRouter(tags=["channel"])


def _resolve_goose_import_mode(goose_import_mode: str, auto_create_goose: bool) -> str:
    """解析显式 GOOSE 导入视角，并兼容旧版布尔参数。"""
    resolved = goose_import_mode.strip().lower()
    if not resolved:
        resolved = "local_publish" if auto_create_goose else "model_only"
    valid_modes = {"model_only", "local_publish", "remote_subscribe", "both"}
    if resolved not in valid_modes:
        raise ValidationError("goose_import_mode 必须是 model_only、local_publish、remote_subscribe 或 both")
    return resolved


def _collect_dataset_configs(goose_data: dict[str, Any]) -> list[dict[str, Any]]:
    """收集导入时必须注册的 DataSet，并按完整引用去重。

    ``pure_datasets`` 只包含未被控制块引用的数据集；被 GSEControl
    引用的数据集位于 publisher 配置中。DataSet 是独立的 MMS 模型
    对象，因此即使不自动创建 GOOSE Publisher，也必须注册。
    """
    datasets_by_ref: dict[str, dict[str, Any]] = {}

    for ds_info in goose_data.get("pure_datasets", []):
        ds_ref = ds_info.get("data_set_ref") or ds_info.get("ds_ref", "")
        if ds_ref:
            datasets_by_ref[ds_ref] = {
                **ds_info,
                "data_set_ref": ds_ref,
            }

    for publisher in goose_data.get("publishers", []):
        ds_ref = publisher.get("data_set_ref", "")
        if not ds_ref:
            continue
        ld_inst = ds_ref.split("/", 1)[0]
        ds_name = ds_ref.rsplit("$", 1)[-1] if "$" in ds_ref else ds_ref.rsplit(".", 1)[-1]
        datasets_by_ref.setdefault(
            ds_ref,
            {
                "ld_inst": ld_inst,
                "ds_name": ds_name,
                "ds_ref": ds_ref,
                "data_set_ref": ds_ref,
                "member_count": len(publisher.get("entries", [])),
                "entries": publisher.get("entries", []),
            },
        )

    return list(datasets_by_ref.values())


@router.post("/import-points", response_model=BaseResponse)
async def import_points(
    request: Request,
    channel_id: int = Form(...),
    file: UploadFile = File(...),
):
    """导入 Excel 点表"""
    require_tabular_point_channel(channel_id)

    if not file.filename.endswith((".xlsx", ".xls")):
        raise ValidationError("请上传 Excel 文件 (.xlsx 或 .xls)")

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".xlsx",
        dir=get_storage_path("point_table_cache_directory"),
    ) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from src.data.dao.point_dao import PointDao

        deleted_count = PointDao.delete_points_by_channel(channel_id)
        if deleted_count > 0:
            log.info(f"重新导入前已删除 {deleted_count} 个旧测点")

        importer = ExcelPointImporter(channel_id=channel_id)
        yc_count, yx_count, yk_count, yt_count = importer.import_from_excel(tmp_path)

        try:
            device_controller = request.app.state.device_controller
            device = device_controller.get_device_by_id(channel_id)
            if device:
                if device.protocol_type == ProtocolType.Iec61850Server:
                    was_running = device.is_protocol_running()
                    await reload_device_instance(device_controller, channel_id, is_start=was_running)
                    log.info(f"IEC 61850 服务端设备 {device.name} (ID: {channel_id}) 已重建以加载新点表")
                else:
                    device.importDataPointFromChannel(channel_id, device.protocol_type)
                    log.info(f"已同步更新设备 {device.name} (ID: {channel_id}) 的内存点表")
            else:
                log.warning(f"导入点表后未找到内存设备 (ID: {channel_id})，需要手动加载或重启")
        except Exception as e:
            log.error(f"同步内存点表失败: {e}")

        return BaseResponse(
            message="导入点表成功",
            data={
                "yc_count": yc_count,
                "yx_count": yx_count,
                "yk_count": yk_count,
                "yt_count": yt_count,
                "total": yc_count + yx_count + yk_count + yt_count,
            },
        )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/preview-icd", response_model=BaseResponse)
async def preview_icd(
    request: Request,
    file: UploadFile = File(...),
    interface: str = Form("eth0"),
):
    """预览 ICD/SCD/CID 文件（只解析不保存，返回 MMS 测点数量和 GOOSE 配置）"""
    valid_extensions = (".icd", ".scd", ".cid", ".xml")
    if not file.filename.lower().endswith(valid_extensions):
        raise ValidationError(f"请上传 ICD 文件 ({', '.join(valid_extensions)})")

    suffix = os.path.splitext(file.filename)[1] or ".icd"
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
        dir=get_storage_path("iec61850_temp_directory"),
    ) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # ===== 1. MMS 测点预览（只计数不保存） =====
        # 优先使用 SclImportService (统一解析)，失败时回退到旧 Importer
        use_scl_service = True
        yc_count, yx_count, yk_count, yt_count = 0, 0, 0, 0
        result = None  # SclImportResult, 初始化避免 unbound

        try:
            from src.proto.iec61850.plugins.scl.service.import_service import SclImportService

            service = SclImportService()
            result = await asyncio.to_thread(service.preview_file, tmp_path)
            yc_count = len(result.points.yc_points)
            yx_count = len(result.points.yx_points)
            yk_count = len(result.points.yk_points)
            yt_count = len(result.points.yt_points)
        except Exception as scl_err:
            log.warning(f"SclImportService 预览失败，回退到旧 Importer: {scl_err}")
            use_scl_service = False
            from src.tools.icd_point_importer import IcdPointImporter

            importer = IcdPointImporter(channel_id=0)  # preview 不需要 channel_id
            yc_count, yx_count, yk_count, yt_count = await asyncio.to_thread(importer.preview_from_icd, tmp_path)

        # ===== 2. GOOSE 配置预览 =====
        goose_data: dict[str, Any] = {}
        goose_errors: list[str] = []
        try:
            if use_scl_service and result is not None:
                # 复用 SclImportService 的 GOOSE 结果
                goose_data = {
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
                    "publishers": [gse.to_publisher_dict(interface) for gse in result.goose.gse_controls],
                    "subscriptions": [gse.to_subscription_dict() for gse in result.goose.gse_controls],
                    "engineered_subscriptions": result.goose.engineered_subscriptions,
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
                }
            else:
                from src.tools.icd_goose_importer import import_goose_from_icd

                goose_result = await asyncio.to_thread(import_goose_from_icd, tmp_path, interface=interface)
                goose_data = goose_result
        except Exception as e:
            log.warning(f"预览 ICD GOOSE 配置失败 (不影响 MMS 预览): {e}")
            goose_errors.append(f"GOOSE 解析失败: {e}")

        return BaseResponse(
            message="ICD 文件预览成功",
            data={
                "yc_count": yc_count,
                "yx_count": yx_count,
                "yk_count": yk_count,
                "yt_count": yt_count,
                "total": yc_count + yx_count + yk_count + yt_count,
                "goose": {
                    "summary": goose_data.get("summary", {"gse_control_count": 0, "gse_controls": []}),
                    "publishers": goose_data.get("publishers", []),
                    "subscriptions": goose_data.get("subscriptions", []),
                    "datasets": _collect_dataset_configs(goose_data),
                    "pure_datasets": goose_data.get("pure_datasets", []),
                    "errors": goose_errors,
                }
                if goose_data
                else None,
            },
        )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/import-icd", response_model=BaseResponse)
async def import_icd(
    request: Request,
    channel_id: int = Form(...),
    file: UploadFile = File(...),
    interface: str = Form("eth0"),
    auto_create_goose: bool = Form(False),
    goose_import_mode: str = Form(""),
):
    """导入 IEC 61850 ICD/SCD/CID 文件

    解析 ICD 文件并加载到设备内存模型:
    - MMS 测点 (遥测/遥信/遥控/遥调) → 仅解析返回数量，不写入数据库
    - GOOSE 配置 (GSEControl/DataSet/GSE) → 按显式导入视角创建 Publisher/Subscription
    """
    require_iec61850_channel(channel_id)

    # 兼容旧客户端的 auto_create_goose，同时禁止再根据 MMS Client/Server
    # 角色隐式推断 GOOSE 方向。
    resolved_goose_mode = _resolve_goose_import_mode(goose_import_mode, auto_create_goose)

    valid_extensions = (".icd", ".scd", ".cid", ".xml")
    if not file.filename.lower().endswith(valid_extensions):
        raise ValidationError(f"请上传 ICD 文件 ({', '.join(valid_extensions)})")

    suffix = os.path.splitext(file.filename)[1] or ".icd"
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
        dir=get_storage_path("iec61850_temp_directory"),
    ) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # 先从通道获取设备名称，用于构建存储路径
        channel_info = ChannelService.get_channel_by_id(channel_id)
        device_name = channel_info.get("name", "unknown") if channel_info else "unknown"

        # ===== 1. 解析 ICD 文件（仅一次，后续复用） =====
        from src.proto.iec61850.plugins.scl.service.import_service import SclImportService

        service = SclImportService()
        scl_result = await asyncio.to_thread(service.import_file, tmp_path)
        scl_data = await asyncio.to_thread(scl_result.to_dict)

        # 提取 IED 名称并更新通道配置
        ied_name = scl_result.ied_name or ""
        if ied_name:
            try:
                ChannelService.update_channel(channel_id, model_name=ied_name)
                log.info(f"已从 ICD 文件提取 IED 名称: {ied_name} -> 通道 {channel_id}")
            except Exception as e:
                log.warning(f"更新通道 IED 名称失败: {e}")

        # 提取测点计数
        yc_count = len(scl_result.points.yc_points)
        yx_count = len(scl_result.points.yx_points)
        yk_count = len(scl_result.points.yk_points)
        yt_count = len(scl_result.points.yt_points)

        # ===== 2. 保存 ICD 文件到 data/device/ 目录（在重建设备前更新 icd_path） =====
        try:
            from src.proto.iec61850.plugins.scl.service.file_manager import SclFileManager

            fm = SclFileManager()
            dest_path = fm.save_to_device_dir(
                source_path=tmp_path,
                device_name=device_name,
                original_filename=file.filename,
                channel_id=channel_id,
            )
            # 更新数据库中的 icd_path（在重建设备之前，使 reload 能加载新文件）
            ChannelService.update_channel(
                channel_id,
                icd_path=dest_path,
                icd_file_hash=fm.compute_hash_from_file(dest_path),
            )
            log.info(f"ICD 文件已保存到设备目录并记录到数据库: {dest_path}")
        except Exception as e:
            log.warning(f"保存 ICD 文件到设备目录失败 (使用临时路径加载模型): {e}")

        # ===== 3. 重建设备实例（复用 scl_result，跳过内部重新解析） =====
        device_controller = request.app.state.device_controller
        was_running = False
        try:
            device = device_controller.get_device_by_id(channel_id)
            if device:
                was_running = device.is_protocol_running()
                await reload_device_instance(device_controller, channel_id, is_start=False, scl_result=scl_result)
                log.info("IEC 61850 设备已重建 (暂未启动，待 DataSet/GoCB 注册后再启动)")
            else:
                log.warning(f"导入ICD后未找到内存设备 (ID: {channel_id})，需要手动加载或重启")
        except Exception as e:
            log.error(f"同步内存点表失败: {e}")

        # ===== 4. GOOSE/DataSet/RCB 配置处理 =====
        goose_data: dict[str, Any] = {}
        goose_errors: list[str] = []
        created_goose_count = 0
        created_subscription_count = 0
        pure_datasets: list[dict[str, Any]] = []
        datasets_to_register: list[dict[str, Any]] = []
        publisher_dataset_refs: set[str] = set()

        # 重新导入 ICD 是当前通道 GOOSE 配置的全量替换。无论新的导入
        # 视角是什么，都必须先删除旧 Publisher/DataSet/Receiver/Subscription，
        # 否则数据库和运行时会同时残留上一份 ICD 的资源。
        from src.proto.iec61850.plugins.goose.cleanup import clear_channel_goose_resources

        imports_publishers = resolved_goose_mode in {"local_publish", "both"}
        imports_subscriptions = resolved_goose_mode in {"remote_subscribe", "both"}
        old_manager = getattr(request.app.state, "goose_manager", None)
        cleanup = clear_channel_goose_resources(channel_id, old_manager)
        if any(cleanup.values()):
            log.info(
                "重新导入前已清理旧 GOOSE 配置: "
                f"Publisher/DataSet={cleanup['publishers']}, Receiver={cleanup['receivers']}, "
                f"运行时 Publisher={cleanup['runtime_publishers']}, "
                f"运行时 Receiver={cleanup['runtime_receivers']}"
            )

        # 获取 IEC 61850 服务器（用于在 MMS 数据模型中注册 GSEControlBlock）
        iec61850_server = None
        do_descriptions: dict[str, str] = {}
        try:
            _device = device_controller.get_device_by_id(channel_id)
            if _device and _device.protocol_handler:
                _handler = _device.protocol_handler
                from src.device.protocol.iec61850_handler import IEC61850ServerHandler

                if isinstance(_handler, IEC61850ServerHandler):
                    iec61850_server = _handler.server
                    log.info("已获取 IEC61850Server，将在 MMS 模型中注册 DataSet/GSEControlBlock")
        except Exception as e:
            log.warning(f"获取 IEC61850Server 失败: {e}")

        try:
            # 从 scl_result 提取 GOOSE 配置和 DO 描述（复用已解析的结果）
            scl_data = await asyncio.to_thread(scl_result.to_dict)
            goose_data = dict(scl_data.get("goose", {}))
            goose_data["pure_datasets"] = scl_result.goose.pure_datasets
            goose_data["report_controls"] = scl_data.get("report_controls", [])
            for p in (
                scl_result.points.yc_points
                + scl_result.points.yx_points
                + scl_result.points.yk_points
                + scl_result.points.yt_points
            ):
                if p.name and p.reg_addr:
                    do_ref = ".".join(p.reg_addr.split(".")[:2])
                    if do_ref not in do_descriptions:
                        do_descriptions[do_ref] = p.name

            # ===== 2a. 复用 load_model() 已注册的 DataSet/RCB =====
            # reload_device_instance() 上一步已经通过 IEC61850Server.load_model()
            # 完成 DataSet 和 ReportControlBlock 的唯一一次注册。这里仅统计并持久化，
            # 不再二次创建模型节点，避免 RCB 数量翻倍和同名节点状态分裂。
            pure_datasets = goose_data.get("pure_datasets", [])
            datasets_to_register = _collect_dataset_configs(goose_data)
            report_controls = goose_data.get("report_controls", [])
            registered_dataset_count = len(iec61850_server.browse_datasets()) if iec61850_server else 0
            rc_registered = len(iec61850_server.reports.rcb_list) if iec61850_server else 0
            log.info(
                f"load_model 已完成模型注册: DataSet={registered_dataset_count}, "
                f"RCB={rc_registered}/{len(report_controls)}"
            )

            # ===== 2b. 创建 GOOSE Publisher（注册 GSEControlBlock） =====
            # GoCB 引用的 DataSet 会在 add_goose_control_block 内部创建
            # 但纯 DataSet 已在 2a 步骤中提前注册到 IedModel
            if imports_publishers and goose_data.get("publishers"):
                from src.proto.iec61850.plugins.goose.manager import GooseResourceManager

                manager: GooseResourceManager | None = getattr(request.app.state, "goose_manager", None)
                if manager:
                    for pub_config in goose_data["publishers"]:
                        try:
                            pub_result = manager.create_publisher(
                                interface=pub_config["interface"],
                                go_cb_ref=pub_config["go_cb_ref"],
                                go_id=pub_config["go_id"],
                                data_set_ref=pub_config["data_set_ref"],
                                app_id=pub_config["app_id"],
                                conf_rev=pub_config["conf_rev"],
                                time_allowed_to_live=pub_config["time_allowed_to_live"],
                                dst_mac=pub_config.get("dst_mac"),
                                vlan_id=pub_config.get("vlan_id", 0),
                                vlan_prio=pub_config.get("vlan_prio", 4),
                                simulation=pub_config.get("simulation", True),
                                entries=pub_config.get("entries", []),
                                server=iec61850_server,
                                channel_id=channel_id,  # 持久化到数据库
                                # 不在 create_publisher 内部触发 apply_model_changes，
                                # 由下面的统一启动处理
                                skip_model_rebuild=True,
                            )
                            if pub_result:
                                created_goose_count += 1
                                publisher_dataset_refs.add(pub_config.get("data_set_ref", ""))
                            else:
                                goose_errors.append(f"创建 Publisher 失败: {pub_config['go_cb_ref']}")
                        except Exception as e:
                            goose_errors.append(f"创建 Publisher 异常 ({pub_config['go_cb_ref']}): {e}")
                else:
                    goose_errors.append("GOOSE 管理器未初始化，无法自动创建 Publisher")

            # ===== 2c. 将远端 IED 的 GSEControl 显式导入为本地订阅 =====
            # 此模式表示文件描述的是远端发布者，不改变 SCL 中 GSEControl
            # 的所有权，也不把 MMS Client 身份等同于 GOOSE Subscriber。
            subscription_configs = (
                goose_data.get("subscriptions", [])
                if resolved_goose_mode == "remote_subscribe"
                else goose_data.get("engineered_subscriptions", [])
            )
            if imports_subscriptions and subscription_configs:
                manager = getattr(request.app.state, "goose_manager", None)
                if manager:
                    subscription_configs = [
                        item
                        for item in subscription_configs
                        if item.get("go_cb_ref") and item.get("binding_status") != "unresolved"
                    ]
                    receiver = manager.import_discovered(
                        subscription_configs,
                        interface=interface,
                        channel_id=channel_id,
                    )
                    if receiver:
                        created_subscription_count = len(subscription_configs)
                    else:
                        goose_errors.append("创建 GOOSE Receiver/Subscription 失败")
                else:
                    goose_errors.append("GOOSE 管理器未初始化，无法创建 Subscription")

            # ===== 2d. 统一启动 MMS 服务器 =====
            # 所有 DataSet 和 GoCB 已注册到 IedModel，现在启动 IedServer
            # IedServer_create 一次性构建包含所有节点的 MMS 命名空间
            # register_default_rcbs=False: ICD 已提供 RCB 配置，不应再创建默认 brcb01/brcb02
            # 先存储 dU 描述（无论 need_start 如何），start() 内部 _apply_du_descriptions 会自动应用
            if do_descriptions and iec61850_server:
                iec61850_server.set_du_descriptions(do_descriptions)
            need_start = created_goose_count > 0 or registered_dataset_count > 0 or rc_registered > 0 or was_running
            if need_start and iec61850_server:
                # 启动前诊断：确认 GoCB/DataSet 已注册到 IedModel
                log.info(
                    f"启动 MMS 服务器前诊断: "
                    f"GoCB={len(iec61850_server._goose_cb_list)}, "
                    f"DataSet={len(iec61850_server._dataset_catalog)}, "
                    f"LD={list(iec61850_server._ld_map.keys())}, "
                    f"LN_count={len(iec61850_server._ln_map)}, "
                    f"is_running={iec61850_server.is_running}"
                )
                try:
                    log.info(
                        f"启动 MMS 服务器 (DataSet={registered_dataset_count}, "
                        f"GoCB={created_goose_count}, "
                        f"RCB={rc_registered}, "
                        f"was_running={was_running})..."
                    )
                    # register_default_rcbs=False: 跳过 brcb01/brcb02 默认 RCB，
                    # ICD 文件中的 ReportControl 已在 2ab 步骤注册
                    await asyncio.to_thread(iec61850_server.start, register_default_rcbs=False)
                    if iec61850_server.is_running:
                        log.info("MMS 服务器启动完成，DataSet 和 GoCB 已生效")
                    else:
                        goose_errors.append("MMS 服务器启动失败")
                except Exception as start_err:
                    goose_errors.append(f"启动 MMS 服务器失败: {start_err}")

            # 持久化未由 Publisher 持久化的数据集，应用重启后可自动恢复。
            # 成功创建的 Publisher 会携带自己的 DataSet 配置，无需重复保存。
            datasets_to_persist = [
                ds for ds in datasets_to_register if ds.get("data_set_ref", "") not in publisher_dataset_refs
            ]
            if datasets_to_persist:
                try:
                    from src.data.dao.goose_publisher_dao import GoosePublisherDao

                    saved_dataset_count = 0
                    for ds_info in datasets_to_persist:
                        dao_result = GoosePublisherDao.save_pure_dataset(
                            channel_id=channel_id,
                            ld_inst=ds_info.get("ld_inst", ""),
                            ds_name=ds_info.get("ds_name", ""),
                            data_set_ref=ds_info.get("data_set_ref", ""),
                            entries=ds_info.get("entries", []),
                        )
                        if dao_result is not None:
                            saved_dataset_count += 1
                    if saved_dataset_count > 0:
                        log.info(f"已持久化 {saved_dataset_count} 个 DataSet 到数据库")
                except Exception as persist_err:
                    log.warning(f"持久化 DataSet 到数据库失败 (不影响内存注册): {persist_err}")

                if registered_dataset_count > 0:
                    log.info(f"已注册 {registered_dataset_count} 个 DataSet 到 MMS 模型")
        except Exception as e:
            log.warning(f"解析 ICD GOOSE 配置失败 (不影响 MMS 导入): {e}")
            goose_errors.append(f"GOOSE 解析失败: {e}")

        # 模型已在 reload_device_instance 中通过 load_iec61850_model 加载
        model_loaded = True

        return BaseResponse(
            message="导入ICD文件成功",
            data={
                # MMS 测点
                "yc_count": yc_count,
                "yx_count": yx_count,
                "yk_count": yk_count,
                "yt_count": yt_count,
                "total": yc_count + yx_count + yk_count + yt_count,
                # IEC61850 模型状态
                "model_loaded": model_loaded,
                # GOOSE 配置
                "goose": {
                    "summary": goose_data.get("summary", {"gse_control_count": 0, "gse_controls": []}),
                    "publishers": goose_data.get("publishers", []),
                    "subscriptions": goose_data.get("subscriptions", []),
                    "created_count": created_goose_count,
                    "subscription_created_count": created_subscription_count,
                    "import_mode": resolved_goose_mode,
                    "dataset_count": len(datasets_to_register),
                    "datasets": datasets_to_register,
                    "pure_dataset_count": len(pure_datasets) if pure_datasets else 0,
                    "pure_datasets": pure_datasets,
                    "errors": goose_errors,
                }
                if goose_data
                else None,
            },
        )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
