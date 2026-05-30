"""通道管理 - 点表导入路由

ICD/SCD/CID 文件统一导入:
- MMS 测点 (遥测/遥信/遥控/遥调)
- GOOSE 配置 (Publisher/Subscriber)
"""

import os
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, File, UploadFile, Form

from src.data.service.channel_service import ChannelService
from src.tools.excel_point_importer import ExcelPointImporter
from src.enums.modbus_def import ProtocolType
from src.web.api.schemas import BaseResponse
from src.web.api.channel.helpers import reload_device_instance
from src.web.log import log

router = APIRouter(tags=["channel"])


@router.post("/import-points", response_model=BaseResponse)
async def import_points(
    request: Request,
    channel_id: int = Form(...),
    file: UploadFile = File(...),
):
    """导入 Excel 点表"""
    try:
        if not file.filename.endswith(('.xlsx', '.xls')):
            return BaseResponse(code=400, message="请上传 Excel 文件 (.xlsx 或 .xls)")

        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
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
                    "yc_count": yc_count, "yx_count": yx_count,
                    "yk_count": yk_count, "yt_count": yt_count,
                    "total": yc_count + yx_count + yk_count + yt_count,
                },
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        log.error(f"导入点表失败: {e}")
        return BaseResponse(code=500, message=f"导入点表失败: {e}")


@router.post("/preview-icd", response_model=BaseResponse)
async def preview_icd(
    request: Request,
    file: UploadFile = File(...),
    interface: str = Form("eth0"),
):
    """预览 ICD/SCD/CID 文件（只解析不保存，返回 MMS 测点数量和 GOOSE 配置）"""
    try:
        valid_extensions = ('.icd', '.scd', '.cid', '.xml')
        if not file.filename.lower().endswith(valid_extensions):
            return BaseResponse(code=400, message=f"请上传 ICD 文件 ({', '.join(valid_extensions)})")

        suffix = os.path.splitext(file.filename)[1] or '.icd'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            # ===== 1. MMS 测点预览（只计数不保存） =====
            from src.tools.icd_point_importer import IcdPointImporter
            importer = IcdPointImporter(channel_id=0)  # preview 不需要 channel_id
            yc_count, yx_count, yk_count, yt_count = importer.preview_from_icd(tmp_path)

            # ===== 2. GOOSE 配置预览 =====
            goose_data: Dict[str, Any] = {}
            goose_errors: List[str] = []
            try:
                from src.tools.icd_goose_importer import import_goose_from_icd
                goose_result = import_goose_from_icd(tmp_path, interface=interface)
                goose_data = goose_result
            except Exception as e:
                log.warning(f"预览 ICD GOOSE 配置失败 (不影响 MMS 预览): {e}")
                goose_errors.append(f"GOOSE 解析失败: {e}")

            return BaseResponse(
                message="ICD 文件预览成功",
                data={
                    "yc_count": yc_count, "yx_count": yx_count,
                    "yk_count": yk_count, "yt_count": yt_count,
                    "total": yc_count + yx_count + yk_count + yt_count,
                    "goose": {
                        "summary": goose_data.get("summary", {"gse_control_count": 0, "gse_controls": []}),
                        "publishers": goose_data.get("publishers", []),
                        "subscriptions": goose_data.get("subscriptions", []),
                        "errors": goose_errors,
                    } if goose_data else None,
                },
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        log.error(f"预览 ICD 文件失败: {e}")
        return BaseResponse(code=500, message=f"预览 ICD 文件失败: {e}")


@router.post("/import-icd", response_model=BaseResponse)
async def import_icd(
    request: Request,
    channel_id: int = Form(...),
    file: UploadFile = File(...),
    interface: str = Form("eth0"),
    auto_create_goose: bool = Form(True),
):
    """导入 IEC 61850 ICD/SCD/CID 文件

    同时解析:
    - MMS 测点 (遥测/遥信/遥控/遥调) → 写入数据库
    - GOOSE 配置 (GSEControl/DataSet/GSE) → 返回给前端，可选自动创建 Publisher
    """
    try:
        valid_extensions = ('.icd', '.scd', '.cid', '.xml')
        if not file.filename.lower().endswith(valid_extensions):
            return BaseResponse(code=400, message=f"请上传 ICD 文件 ({', '.join(valid_extensions)})")

        suffix = os.path.splitext(file.filename)[1] or '.icd'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            # ===== 1. MMS 测点导入 =====
            # IcdPointImporter.import_from_icd() 内部会先清除旧测点，此处无需重复删除
            from src.tools.icd_point_importer import IcdPointImporter
            importer = IcdPointImporter(channel_id=channel_id)
            yc_count, yx_count, yk_count, yt_count = importer.import_from_icd(tmp_path)

            # 从 ICD 文件中提取 IED 名称，更新通道配置
            try:
                ied_name = importer.get_ied_name()
                if ied_name:
                    ChannelService.update_channel(channel_id, model_name=ied_name)
                    log.info(f"已从 ICD 文件提取 IED 名称: {ied_name} -> 通道 {channel_id}")
            except Exception as e:
                log.warning(f"提取 IED 名称失败 (不影响测点导入): {e}")

            # 重建设备实例（暂不启动），先注册 DataSet/GoCB 再启动服务器
            # IEC 61850 标准要求的创建顺序：数据模型(DO/DA) → DataSet → GSEControlBlock → IedServer_create
            device_controller = request.app.state.device_controller
            was_running = False
            try:
                device = device_controller.get_device_by_id(channel_id)
                if device:
                    if device.protocol_type == ProtocolType.Iec61850Server:
                        was_running = device.is_protocol_running()
                        # 关键：is_start=False，不立即启动服务器
                        # 先完成 DataSet 和 GoCB 注册，最后统一启动
                        await reload_device_instance(device_controller, channel_id, is_start=False)
                        log.info(f"IEC 61850 服务端设备已重建 (暂未启动，待 DataSet/GoCB 注册后再启动)")
                    else:
                        device.importDataPointFromChannel(channel_id, device.protocol_type)
                        log.info(f"已同步更新设备 {device.name} (ID: {channel_id}) 的内存点表")
                else:
                    log.warning(f"导入ICD后未找到内存设备 (ID: {channel_id})，需要手动加载或重启")
            except Exception as e:
                log.error(f"同步内存点表失败: {e}")

            # ===== 2. GOOSE 配置解析 =====
            goose_data: Dict[str, Any] = {}
            goose_errors: List[str] = []
            created_goose_count = 0
            pure_datasets: List[Dict[str, Any]] = []

            # 先清除旧的 GOOSE 持久化记录和内存中的 Publisher
            try:
                from src.data.dao.goose_publisher_dao import GoosePublisherDao
                old_count = GoosePublisherDao.delete_by_channel(channel_id)
                if old_count > 0:
                    log.info(f"重新导入前已删除 {old_count} 个旧 GOOSE Publisher 持久化记录")
            except Exception as e:
                log.warning(f"清除旧 GOOSE 持久化记录失败: {e}")

            # 清除管理器中的旧 Publisher 记录（防止 go_cb_ref 缓存导致新 Publisher 跳过创建）
            try:
                from src.proto.iec61850.goose_manager import GooseManager
                old_manager: Optional[GooseManager] = getattr(
                    request.app.state, "goose_manager", None
                )
                if old_manager:
                    # 仅清除当前通道的 Publisher（通过 _channel_map 过滤）
                    old_go_cb_refs = [
                        go_cb_ref for go_cb_ref, cid in old_manager._channel_map.items()
                        if cid == channel_id
                    ]
                    deleted_old = 0
                    for go_cb_ref in old_go_cb_refs:
                        if old_manager.delete_publisher(go_cb_ref, delete_from_db=False):
                            deleted_old += 1
                    if deleted_old > 0:
                        log.info(f"已从 GOOSE 管理器中清除通道 {channel_id} 的 {deleted_old} 个旧 Publisher")
            except Exception as e:
                log.warning(f"清除旧 GOOSE Publisher 内存记录失败: {e}")

            # 获取 IEC 61850 服务器（用于在 MMS 数据模型中注册 GSEControlBlock）
            iec61850_server = None
            try:
                _device = device_controller.get_device_by_id(channel_id)
                if _device and hasattr(_device, 'protocol_handler') and _device.protocol_handler:
                    _handler = _device.protocol_handler
                    if hasattr(_handler, 'server'):
                        iec61850_server = _handler.server
                        log.info("已获取 IEC61850Server，将在 MMS 模型中注册 DataSet/GSEControlBlock")
            except Exception as e:
                log.warning(f"获取 IEC61850Server 失败: {e}")

            try:
                from src.tools.icd_goose_importer import import_goose_from_icd
                goose_result = import_goose_from_icd(tmp_path, interface=interface)
                goose_data = goose_result

                # ===== 2a. 注册纯 DataSet（必须在 GoCB 之前） =====
                # IEC 61850 标准创建顺序：数据模型 → DataSet → GSEControlBlock
                # DataSet 必须先于引用它的 GSEControlBlock 存在于 IedModel 中
                pure_datasets = goose_result.get("pure_datasets", [])
                pure_ds_count = 0
                log.info(f"纯 DataSet 注册准备: pure_datasets={len(pure_datasets)}个, iec61850_server={'可用' if iec61850_server else 'None'}")
                if pure_datasets and iec61850_server:
                    for ds_info in pure_datasets:
                        try:
                            success = iec61850_server.register_dataset(
                                ld_inst=ds_info["ld_inst"],
                                ds_name=ds_info["ds_name"],
                                data_set_ref=ds_info["data_set_ref"],
                                entries=ds_info.get("entries", []),
                            )
                            if success:
                                pure_ds_count += 1
                        except Exception as ds_err:
                            log.warning(f"注册纯 DataSet 失败 ({ds_info.get('ds_name', '')}): {ds_err}")

                # ===== 2ab. 注册 ReportControl (RCB) =====
                # 从 ICD 的 ReportControl 元素创建 RCB 对象到 IedModel
                report_controls = goose_result.get("report_controls", [])
                rc_registered = 0
                if report_controls and iec61850_server:
                    log.info(f"ReportControl 注册准备: {len(report_controls)}个")
                    for rc_info in report_controls:
                        try:
                            # 确保 DataSet 已注册 (RCB 引用的 DataSet)
                            ds_ref = rc_info.get("data_set_ref", "")
                            if ds_ref and iec61850_server:
                                ds_name = ds_ref.split("$")[-1] if "$" in ds_ref else ""
                                if ds_name and not any(
                                    d.get("ref") == ds_ref
                                    for d in iec61850_server.browse_datasets()
                                ):
                                    iec61850_server.register_dataset(
                                        ld_inst=rc_info["ld_inst"],
                                        ds_name=ds_name,
                                        data_set_ref=ds_ref,
                                        entries=None,
                                    )
                            # 注册 RCB 到 MMS 模型
                            trg_ops = rc_info.get("trg_ops", {})
                            opt_fields = rc_info.get("opt_fields", {})
                            # 如果 register_rcb 不可用，至少存到目录
                            if hasattr(iec61850_server, 'reports') and iec61850_server.reports:
                                success = iec61850_server.reports.register_rcb(
                                    ld_inst=rc_info["ld_inst"],
                                    name=rc_info["name"],
                                    rcb_type=rc_info["rcb_type"],
                                    rpt_id=rc_info.get("rpt_id", rc_info["name"]),
                                    data_set_ref=ds_ref,
                                    conf_rev=rc_info.get("conf_rev", 1),
                                    buf_time=rc_info.get("buf_time", 0),
                                    intg_period=rc_info.get("intg_period", 0),
                                    trg_ops=trg_ops if any(trg_ops.values()) else None,
                                    opt_fields=opt_fields if any(opt_fields.values()) else None,
                                )
                                if success:
                                    rc_registered += 1
                                    log.info(f"RCB 已注册: {rc_info['ld_inst']}/{rc_info['name']}")
                                else:
                                    log.warning(f"RCB 注册失败: {rc_info['ld_inst']}/{rc_info['name']}")
                            else:
                                log.warning(f"reports 管理器不可用，跳过 RCB 注册: {rc_info['name']}")
                        except Exception as rc_err:
                            log.warning(f"注册 RCB 异常 ({rc_info.get('name', '')}): {rc_err}")
                    log.info(f"ReportControl 注册完成: {rc_registered}/{len(report_controls)}")


                # ===== 2b. 创建 GOOSE Publisher（注册 GSEControlBlock） =====
                # GoCB 引用的 DataSet 会在 add_goose_control_block 内部创建
                # 但纯 DataSet 已在 2a 步骤中提前注册到 IedModel
                if auto_create_goose and goose_result.get("publishers"):
                    from src.proto.iec61850.goose_manager import GooseManager
                    manager: Optional[GooseManager] = getattr(
                        request.app.state, "goose_manager", None
                    )
                    if manager:
                        for pub_config in goose_result["publishers"]:
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
                                else:
                                    goose_errors.append(
                                        f"创建 Publisher 失败: {pub_config['go_cb_ref']}"
                                    )
                            except Exception as e:
                                goose_errors.append(
                                    f"创建 Publisher 异常 ({pub_config['go_cb_ref']}): {e}"
                                )
                    else:
                        goose_errors.append("GOOSE 管理器未初始化，无法自动创建 Publisher")

                # ===== 2c. 统一启动 MMS 服务器 =====
                # 所有 DataSet 和 GoCB 已注册到 IedModel，现在启动 IedServer
                # IedServer_create 一次性构建包含所有节点的 MMS 命名空间
                need_start = (created_goose_count > 0 or pure_ds_count > 0 or was_running)
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
                            f"启动 MMS 服务器 (DataSet={pure_ds_count}, "
                            f"GoCB={created_goose_count}, was_running={was_running})..."
                        )
                        iec61850_server.start()
                        if iec61850_server.is_running:
                            log.info("MMS 服务器启动完成，DataSet 和 GoCB 已生效")
                        else:
                            goose_errors.append("MMS 服务器启动失败")
                    except Exception as start_err:
                        goose_errors.append(f"启动 MMS 服务器失败: {start_err}")

                # 持久化纯 DataSet 到数据库（应用重启后可自动恢复）
                if pure_datasets:
                    try:
                        from src.data.dao.goose_publisher_dao import GoosePublisherDao
                        saved_pure_count = 0
                        for ds_info in pure_datasets:
                            dao_result = GoosePublisherDao.save_pure_dataset(
                                channel_id=channel_id,
                                ld_inst=ds_info.get("ld_inst", ""),
                                ds_name=ds_info.get("ds_name", ""),
                                data_set_ref=ds_info.get("data_set_ref", ""),
                                entries=ds_info.get("entries", []),
                            )
                            if dao_result is not None:
                                saved_pure_count += 1
                        if saved_pure_count > 0:
                            log.info(f"已持久化 {saved_pure_count} 个纯 DataSet 到数据库")
                    except Exception as persist_err:
                        log.warning(f"持久化纯 DataSet 到数据库失败 (不影响内存注册): {persist_err}")

                    if pure_ds_count > 0:
                        log.info(f"已注册 {pure_ds_count} 个纯 DataSet 到 MMS 模型")
            except Exception as e:
                log.warning(f"解析 ICD GOOSE 配置失败 (不影响 MMS 导入): {e}")
                goose_errors.append(f"GOOSE 解析失败: {e}")

            return BaseResponse(
                message="导入ICD文件成功",
                data={
                    # MMS 测点
                    "yc_count": yc_count, "yx_count": yx_count,
                    "yk_count": yk_count, "yt_count": yt_count,
                    "total": yc_count + yx_count + yk_count + yt_count,
                    # GOOSE 配置
                    "goose": {
                        "summary": goose_data.get("summary", {"gse_control_count": 0, "gse_controls": []}),
                        "publishers": goose_data.get("publishers", []),
                        "subscriptions": goose_data.get("subscriptions", []),
                        "created_count": created_goose_count,
                        "pure_dataset_count": len(pure_datasets) if pure_datasets else 0,
                        "errors": goose_errors,
                    } if goose_data else None,
                },
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        log.error(f"导入ICD文件失败: {e}")
        return BaseResponse(code=500, message=f"导入ICD文件失败: {e}")
