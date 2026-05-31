"""通道管理 - IEC 61850 相关路由"""

from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from src.data.service.channel_service import ChannelService
from src.enums.modbus_def import ProtocolType
from src.enums.points.base_point import BasePoint
from src.web.api.schemas import BaseResponse
from src.web.log import log

router = APIRouter(tags=["channel"])


# ===== IEC61850 POST 请求模型 =====

class Iec61850ReadPointsRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    category: str = Field("", description="IED/LD 分类过滤")
    item: str = Field("", description="LN 实例过滤")
    interval_ms: int = Field(0, description="读取间隔(ms)")


class Iec61850ReadPointRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    point_code: str = Field(..., description="测点编码")


class Iec61850WritePointRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    point_code: str = Field(..., description="测点编码")
    point_value: Union[float, str] = Field(0, description="写入值")


class Iec61850StructureRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")


class Iec61850TreeDataRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    category: str = Field("", description="IED/LD 分类过滤")
    item: str = Field("", description="LN 实例过滤")
    point_name: Optional[str] = Field(None, description="测点名称过滤")
    point_types: str = Field("", description="帧类型过滤")
    page_index: int = Field(1, description="页码")
    page_size: int = Field(10, description="每页条数")


class Iec61850TableDataRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    category: str = Field("", description="IED/LD 分类过滤")
    item: str = Field("", description="LN 实例过滤")
    point_name: Optional[str] = Field(None, description="测点名称过滤")
    page_index: int = Field(1, description="页码")
    page_size: int = Field(10, description="每页条数")
    point_types: str = Field("", description="帧类型过滤")


class Iec61850DoChildrenRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    ld: str = Field("", description="逻辑设备名")
    ln: str = Field("", description="逻辑节点名")


class Iec61850DaChildrenRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    ld: str = Field("", description="逻辑设备名")
    ln: str = Field("", description="逻辑节点名")
    do_name: str = Field("", description="数据对象名")


class Iec61850DatasetDetailRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    dataset_ref: str = Field(..., description="DataSet 引用路径，如 LD0/LLN0$dsGOOSE1")


class Iec61850DatasetReadRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    dataset_ref: str = Field(..., description="DataSet 引用路径，如 LD0/LLN0$dsGOOSE1")


# ===== IEC 61850 树形数据常量 =====

# 已知结构体 DA 的 BDA 子节点
# q 和 t 在 MMS 映射中为单值 (Quality BitString / UTC_Time),
# 不再展开为子 BDA 结构体。仅保留 origin 的 BDA 展开。
KNOWN_STRUCT_DA_BDAS: Dict[str, List[str]] = {
    "origin": ["orCat", "orIdent"],
}

# 每个 DO 应包含的标准 DA 列表 (后端自动补全)
# q 和 t 是单值 DataAttribute, 非结构体
STANDARD_DAS_FOR_DO: List[Dict[str, Any]] = [
    {"name": "q", "fc": "MX", "is_struct": False},
    {"name": "t", "fc": "MX", "is_struct": False},
    {"name": "dU", "fc": "DC", "is_struct": False},
]

# DA 名称 → 默认 FC 映射
DA_NAME_FC_MAP: Dict[str, str] = {
    "mag": "MX", "instMag": "MX", "cVal": "MX", "f": "MX",
    "stVal": "ST", "ctlVal": "CO", "setVal": "CO",
    "q": "MX", "t": "MX", "dU": "DC",
    "origin": "OR", "subVal": "SV", "blkEna": "BL", "SBO": "CO",
    "Oper": "CO", "Cancel": "CO",
}


def _parse_iec61850_address(address: str) -> Optional[Dict[str, str]]:
    """解析 IEC 61850 地址, 提取 LD/LN/DO/DA 层级
    
    示例: "LD0/LLN0.Mod.mag.f" → {ld: "LD0", ln: "LLN0", do_name: "Mod", da_path: "mag.f"}
    """
    if not address or "/" not in address:
        return None
    slash_idx = address.index("/")
    rest = address[slash_idx + 1:]
    dot_idx = rest.find(".")
    if dot_idx < 0:
        return None  # 无 DO/DA 结构
    ld = address[:slash_idx]
    ln = rest[:dot_idx]
    da_part = rest[dot_idx + 1:]
    first_dot = da_part.find(".")
    if first_dot >= 0:
        do_name = da_part[:first_dot]
        da_path = da_part[first_dot + 1:]
    else:
        do_name = da_part
        da_path = ""
    return {"ld": ld, "ln": ln, "do_name": do_name, "da_path": da_path}


def _infer_fc_from_da(da_path: str, fallback_fc: str = "MX") -> str:
    """从 DA 路径推断 FC"""
    if not da_path:
        return fallback_fc
    top_da = da_path.split(".")[0]
    return DA_NAME_FC_MAP.get(top_da, fallback_fc)


def _build_iec61850_tree(
    all_points: List[BasePoint],
    category: str = "",
    item: str = "",
    point_name: str | None = None,
    point_types: List[int] | None = None,
    device=None,
) -> Dict[str, Any]:
    """将扁平测点列表构建为 IEC 61850 树形结构
    
    返回结构:
    {
        "items": [
            {
                "do_name": "Mod",
                "do_ref": "LD0/LLN0.Mod",
                "du_name": "模式",           # dU 描述 (如有)
                "fc": "CO",                  # DO 主 FC
                "frame_type": 2,             # 帧类型 (0=遥测, 1=遥信, 2=遥控, 3=遥调)
                "children": [                # DA 列表
                    {
                        "da_name": "ctlVal",
                        "da_path": "ctlVal",
                        "fc": "CO",
                        "is_struct": false,
                        "point_code": "xxx",
                        "point_name": "控制值",
                        "value": "1",
                        "status": "成功",
                        "children": []       # BDA 列表 (如有)
                    },
                    {
                        "da_name": "q",
                        "da_path": "q",
                        "fc": "MX",
                        "is_struct": false,
                        "point_code": "yyy",
                        "point_name": "品质",
                        "value": "0",
                        "status": "成功",
                        "children": []
                    },
                    ...
                ]
            }
        ],
        "total": 5
    }
    """
    from src.enums.point_data import Yc, Yx, Yk, Yt
    from src.device.core.data.data_exporter import DataExporter

    if point_types is None:
        point_types = [0, 1, 2, 3]

    # DataSets 分类: 从设备 handler 获取数据集成员信息
    if category and category == "DataSets":
        return _build_iec61850_dataset_tree(device, item)

    # category 过滤: 非 Data Model 分类 (如 GOOSE/Reports) 无 MMS 测点
    if category and category != "Data Model":
        return {"items": [], "total": 0}

    # 1. 收集所有测点, 构建 DO 分组

    do_map: Dict[str, Dict[str, Any]] = {}  # do_ref → {do_info, children_map}

    for point in all_points:
        # 帧类型过滤
        ft = point.frame_type
        if ft not in point_types:
            continue

        # 名称过滤
        if point_name and point_name not in str(point.name):
            continue

        address = str(point.address) if hasattr(point, "address") else ""
        parsed = _parse_iec61850_address(address)
        if not parsed:
            continue

        # category/item 过滤
        if category == "Data Model" and item:
            if not (address.startswith(f"{item}/") or address.startswith(f"{item}.")):
                continue

        ld = parsed["ld"]
        ln = parsed["ln"]
        do_name = parsed["do_name"]
        da_path = parsed["da_path"]
        do_ref = f"{ld}/{ln}.{do_name}"

        # 获取点属性
        point_fc = getattr(point, "fc", "") or ""
        is_valid = getattr(point, "is_valid", None)
        status = "成功" if is_valid is True else ("失败" if is_valid is False else "未知")

        # 获取真实值 (始终返回值，不依赖 is_valid 过滤)
        if point_fc == "DC":
            value = str(point.name)
        elif isinstance(point, (Yc, Yt)):
            value = str(point.real_value) if point.real_value is not None else ""
        elif isinstance(point, (Yx, Yk)):
            try:
                value = str(int(point.value)) if point.value is not None else ""
            except (ValueError, TypeError):
                value = str(point.value) if point.value is not None else ""
        else:
            value = ""

        # 初始化 DO 分组
        if do_ref not in do_map:
            do_map[do_ref] = {
                "do_name": do_name,
                "do_ref": do_ref,
                "ld": ld,
                "ln": ln,
                "du_name": "",
                "fc": point_fc or _infer_fc_from_da(da_path),
                "frame_type": ft,
                "da_map": {},          # da_path → da_info (实际从后端返回的 DA)
                "da_top_names": set(), # 顶级 DA 名称集合
            }

        do_info = do_map[do_ref]

        # 累积 DO 描述: 取第一个非空、且不等于 DO 名的测点名 (即 dU 描述)
        if not do_info.get("desc"):
            pn = str(point.name) if point.name is not None else ""
            if pn and pn != do_name:
                do_info["desc"] = pn

        # 记录顶级 DA 名称
        if da_path:
            top_da = da_path.split(".")[0]
            do_info["da_top_names"].add(top_da)

        # 判断是 BDA 还是 DA
        if "." in da_path:
            top_da = da_path.split(".")[0]
            bda_name = da_path[len(top_da) + 1:]

            # 确保父 DA 存在于 da_map
            if top_da not in do_info["da_map"]:
                parent_fc = point_fc or _infer_fc_from_da(top_da)
                do_info["da_map"][top_da] = {
                    "da_name": top_da,
                    "da_path": top_da,
                    "fc": parent_fc,
                    "is_struct": True,
                    "point_code": "",
                    "point_name": top_da,
                    "value": "",
                    "status": "",
                    "children": [],
                }

            # 添加 BDA
            parent_da = do_info["da_map"][top_da]
            # 检查是否已有同名 BDA
            existing_bda_names = {b.get("bda_name") for b in parent_da["children"]}
            if bda_name not in existing_bda_names:
                parent_da["children"].append({
                    "bda_name": bda_name,
                    "bda_path": da_path,
                    "fc": point_fc or parent_da["fc"],
                    "point_code": str(point.code),
                    "value": value,
                    "status": status,
                })
        else:
            # 顶级 DA
            if da_path not in do_info["da_map"]:
                is_struct = da_path in KNOWN_STRUCT_DA_BDAS
                do_info["da_map"][da_path] = {
                    "da_name": da_path,
                    "da_path": da_path,
                    "fc": point_fc or _infer_fc_from_da(da_path),
                    "is_struct": is_struct,
                    "point_code": str(point.code),
                    "point_name": str(point.name),
                    "value": value,
                    "status": status,
                    "children": [],
                }
            else:
                # 更新已有 DA 的信息 (如 mag.f 创建了 mag 虚拟行后, 真正的 mag 行又来了)
                existing = do_info["da_map"][da_path]
                if not existing["point_code"]:
                    existing["point_code"] = str(point.code)
                    existing["point_name"] = str(point.name)
                    existing["value"] = value
                    existing["status"] = status
                existing["fc"] = point_fc or existing["fc"]

            # 如果是 dU, 记录描述到 DO
            if da_path == "dU" and value and value not in ("0", "0.0"):
                do_info["du_name"] = value

    # 2. 为每个 DO 补充标准 DA (q, t, dU) 和已知 BDA
    for do_ref, do_info in do_map.items():
        da_map = do_info["da_map"]
        top_names = do_info["da_top_names"]
        main_fc = do_info["fc"]

        # q/t 的 FC 根据主值类型推断 (遥测=MX, 遥信=ST)
        qt_fc = "ST" if main_fc == "ST" else "MX"

        for std_da in STANDARD_DAS_FOR_DO:
            da_name = std_da["name"]
            if da_name in top_names or da_name in da_map:
                continue  # 已存在

            fc = qt_fc if da_name in ("q", "t") else std_da["fc"]
            is_struct = std_da["is_struct"]
            bda_list = KNOWN_STRUCT_DA_BDAS.get(da_name, [])

            # 对于 dU，使用累积到的 DO 描述作为值（dU 不单独创建测点）
            dU_value = ""
            dU_name = da_name
            if da_name == "dU":
                dU_value = do_info.get("desc", "")
                if dU_value:
                    dU_name = dU_value
                do_info["du_name"] = dU_value

            da_map[da_name] = {
                "da_name": da_name,
                "da_path": da_name,
                "fc": fc,
                "is_struct": is_struct,
                "point_code": "",
                "point_name": dU_name,
                "value": dU_value,
                "status": "",
                "children": [
                    {
                        "bda_name": bda,
                        "bda_path": f"{da_name}.{bda}",
                        "fc": fc,
                        "point_code": "",
                        "value": "",
                        "status": "",
                    }
                    for bda in bda_list
                ],
            }

        # 对已有结构体 DA 补充缺失的 BDA
        for da_name, bda_names in KNOWN_STRUCT_DA_BDAS.items():
            if da_name not in da_map:
                continue
            da_entry = da_map[da_name]
            existing_bda_names = {b.get("bda_name") for b in da_entry.get("children", [])}
            for bda_name in bda_names:
                if bda_name not in existing_bda_names:
                    da_entry["children"].append({
                        "bda_name": bda_name,
                        "bda_path": f"{da_name}.{bda_name}",
                        "fc": da_entry["fc"],
                        "point_code": "",
                        "value": "",
                        "status": "",
                    })

    # 3. 组装最终树形列表 (按 do_ref 排序)
    items = []
    for do_ref in sorted(do_map.keys()):
        do_info = do_map[do_ref]
        # DA 排序: 主值 DA 在前, q/t/dU 在后
        da_list = list(do_info["da_map"].values())
        # 按 DA 名称排序, 主值优先
        priority_order = {"mag": 0, "instMag": 0, "cVal": 0, "stVal": 0, "ctlVal": 0, "setVal": 0,
                          "Oper": 1, "Cancel": 1, "origin": 2, "q": 3, "t": 4, "dU": 5}
        da_list.sort(key=lambda d: priority_order.get(d["da_name"], 2))

        # 聚合 DA 子节点的状态到 DO 根节点
        da_statuses = [d["status"] for d in da_list if d.get("status")]
        # 也聚合 BDA 子节点的状态
        for da in da_list:
            for bda in da.get("children", []):
                if bda.get("status"):
                    da_statuses.append(bda["status"])

        if any(s == "失败" for s in da_statuses):
            do_status = "失败"
        elif all(s == "成功" for s in da_statuses) and da_statuses:
            do_status = "成功"
        else:
            do_status = "未知"

        items.append({
            "do_name": do_info["do_name"],
            "do_ref": do_info["do_ref"],
            "ld": do_info["ld"],
            "ln": do_info["ln"],
            "du_name": do_info["du_name"] or do_info.get("desc", ""),
            "fc": do_info["fc"],
            "frame_type": do_info["frame_type"],
            "status": do_status,
            "children": da_list,
        })

    return {"items": items, "total": len(items)}


@router.post("/iec61850-tree-data", response_model=BaseResponse)
async def get_iec61850_tree_data(
    body: Iec61850TreeDataRequest,
    request: Request,
):
    """获取 IEC61850 树形表格数据 (按 DO→DA→BDA 层级返回，支持 DO 级分页)"""
    try:
        channel = ChannelService.get_channel_by_id(body.channel_id)
        if not channel:
            return BaseResponse(code=404, message="通道不存在", data={})

        protocol_type = channel.get("protocol_type", -1)
        if protocol_type != 4:
            return BaseResponse(code=400, message="该通道不是 IEC61850 协议", data={})

        device_controller = request.app.state.device_controller
        device = device_controller.get_device_by_channel_id(body.channel_id)
        if not device:
            return BaseResponse(code=404, message="设备未找到", data={})

        pt_filter = []
        if body.point_types:
            try:
                pt_filter = [int(t.strip()) for t in body.point_types.split(",") if t.strip().isdigit()]
            except Exception:
                pt_filter = []
        if not pt_filter:
            pt_filter = [0, 1, 2, 3]

        # 获取所有测点对象
        all_points = _get_iec61850_filtered_points(device, "", "")

        # 构建树形结构
        tree_data = _build_iec61850_tree(
            all_points,
            category=body.category,
            item=body.item,
            point_name=body.point_name,
            point_types=pt_filter,
            device=device,
        )

        # DO 级分页
        all_items = tree_data["items"]
        total = tree_data["total"]
        start = (body.page_index - 1) * body.page_size
        end = start + body.page_size
        paged_items = all_items[start:end]

        return BaseResponse(message="获取 IEC61850 树形数据成功", data={
            "items": paged_items,
            "total": total,
        })
    except Exception as e:
        log.error(f"获取 IEC61850 树形数据失败: {e}")
        return BaseResponse(code=500, message=f"获取 IEC61850 树形数据失败: {e}", data={})


@router.post("/iec61850-structure", response_model=BaseResponse)
async def get_iec61850_structure(body: Iec61850StructureRequest, request: Request):
    """获取 IEC61850 设备的子节点结构树"""
    log.info(f"get_iec61850_structure 请求, channel_id={body.channel_id}")
    try:
        channel = ChannelService.get_channel_by_id(body.channel_id)
        if not channel:
            return BaseResponse(code=404, message="通道不存在", data={})

        protocol_type = channel.get("protocol_type", -1)
        if protocol_type != 4:
            return BaseResponse(code=400, message="该通道不是 IEC61850 协议", data={})

        device_controller = request.app.state.device_controller
        device = device_controller.get_device_by_channel_id(body.channel_id)
        if not device:
            return BaseResponse(code=404, message="设备未找到，请确认设备已创建", data={})

        logical_devices = []
        protocol_handler = getattr(device, 'protocol_handler', None)
        if protocol_handler:
            if hasattr(protocol_handler, '_client') and protocol_handler._client:
                client = protocol_handler._client
                if hasattr(client, 'browse_logical_devices'):
                    logical_devices = client.browse_logical_devices()
                # 获取每个 LD 下的 LN 列表
                data_model = []
                for ld in logical_devices:
                    lns = client.browse_logical_nodes(ld) if hasattr(client, 'browse_logical_nodes') else []
                    data_model.append({"name": ld, "children": lns})
            elif hasattr(protocol_handler, '_server') and protocol_handler._server:
                server = protocol_handler._server
                if hasattr(server, 'browse_logical_devices'):
                    logical_devices = server.browse_logical_devices()
                # 获取每个 LD 下的 LN 列表
                data_model = []
                for ld in logical_devices:
                    lns = server.browse_logical_nodes(ld) if hasattr(server, 'browse_logical_nodes') else []
                    data_model.append({"name": ld, "children": lns})

        # 获取 GOOSE 信息（本机发布者）
        goose_items = []
        goose_manager = getattr(request.app.state, 'goose_manager', None)
        if goose_manager:
            try:
                goose_status = goose_manager.get_all_status()
                for pub in goose_status.get("publishers", []):
                    goose_items.append(f"Pub: {pub.get('go_cb_ref', '')} ({'运行' if pub.get('is_running') else '停止'})")
                for recv in goose_status.get("receivers", []):
                    goose_items.append(f"Recv: {recv.get('interface', '')} ({'运行' if recv.get('is_running') else '停止'})")
            except Exception as e:
                log.warning(f"获取本机 GOOSE 状态失败: {e}")

        # 如果是客户端设备，补充远端发现的 GOOSE 控制块和 DataSet
        dataset_items = []
        if device and hasattr(device, 'protocol_handler') and device.protocol_handler:
            protocol_handler = device.protocol_handler
            discovered_goose = getattr(protocol_handler, '_discovered_goose_items', None)
            if discovered_goose:
                for g in discovered_goose:
                    cb_ref = g.get("go_cb_ref", "")
                    app_id = g.get("app_id")
                    app_id_str = f"0x{app_id:04X}" if app_id is not None else ""
                    status = "已发现"
                    goose_items.append(f"远端GoCB: {cb_ref} ({status}, APPID={app_id_str})")

            # 获取 DataSet 列表（含成员信息），按 LD > LN 组织层级
            if hasattr(protocol_handler, 'get_discovered_datasets'):
                discovered_datasets = protocol_handler.get_discovered_datasets()
                log.info(f"get_discovered_datasets() 返回 {len(discovered_datasets)} 个 DataSet: "
                    + ", ".join(f"{d.get('ld','')}/{d.get('ln','')}.{d.get('name','')}"
                        for d in discovered_datasets))
                # 构建 LD -> {LN -> [datasets]} 层级映射
                ld_map: Dict[str, Dict[str, list]] = {}
                for ds in discovered_datasets:
                    ds_ld = ds.get("ld", "")
                    ds_ln = ds.get("ln", "")
                    if not ds_ld:
                        continue
                    if ds_ld not in ld_map:
                        ld_map[ds_ld] = {}
                    if ds_ln not in ld_map[ds_ld]:
                        ld_map[ds_ld][ds_ln] = []
                    ld_map[ds_ld][ds_ln].append({
                        "ref": ds.get("ref", ""),
                        "name": ds.get("name", ""),
                        "ld": ds_ld,
                        "ln": ds_ln,
                        "member_count": ds.get("member_count", 0),
                    })
                # 转换为层级树: [{name: "LD0", children: [{name: "LLN0", datasets: [...]}]}]
                for ld_name, ln_dict in sorted(ld_map.items()):
                    ln_items = []
                    for ln_name, ds_list in sorted(ln_dict.items()):
                        ln_node = {
                            "name": ln_name,
                            "datasets": ds_list,
                        }
                        ln_items.append(ln_node)
                    dataset_items.append({
                        "name": ld_name,
                        "children": ln_items,
                    })

        # 获取 Reports 信息（通过 ReportsPlugin 发现远端 RCB）
        report_items = []
        if protocol_handler:
            try:
                from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler

                if isinstance(protocol_handler, IEC61850ClientHandler):
                    # 优先用连接时缓存的 RCB，避免首屏现场探测导致空白
                    rcbs = []
                    if hasattr(protocol_handler, 'get_discovered_rcbs'):
                        rcbs = protocol_handler.get_discovered_rcbs()
                    client = getattr(protocol_handler, '_client', None)
                    if not rcbs and client and hasattr(client, 'reports') and client.reports:
                        rcbs = client.reports.discover_rcbs()
                        # 现场发现成功则回写缓存，供 /reports 页面复用
                        if rcbs and hasattr(protocol_handler, 'set_discovered_rcbs'):
                            protocol_handler.set_discovered_rcbs(rcbs)
                    for rcb in rcbs:
                        active_mark = " 🟢" if rcb.get("rpt_ena") else ""
                        report_items.append(
                            f"{rcb['ref']} ({rcb['rcb_type']}){active_mark}"
                        )
                    log.info(f"Reports: 返回 {len(rcbs)} 个 RCB")
                    if not rcbs:
                        log.info("远端 IED 未配置报告控制块 (BRCB/URCB)，需在 ICD 中声明 ReportControl")
                elif isinstance(protocol_handler, IEC61850ServerHandler):
                    # 服务端模式：从 ReportManager 获取已注册的 RCB
                    server = getattr(protocol_handler, '_server', None)
                    if server and hasattr(server, 'reports') and server.reports:
                        rcbs = server.reports.browse_rcbs()
                        for rcb in rcbs:
                            report_items.append(
                                f"{rcb.get('ld_inst', '')}/LLN0.{rcb['name']} ({rcb['rcb_type']})"
                            )
                        log.info(f"通过 ReportManager 发现 {len(rcbs)} 个服务端 RCB")
            except Exception as e:
                log.warning(f"获取 Reports 信息失败: {e}")

        # 获取 Files 信息（通过 FilesPlugin 浏览远程文件目录）
        file_items = []
        if protocol_handler:
            try:
                from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler

                iec61850_client = None
                if isinstance(protocol_handler, IEC61850ClientHandler):
                    iec61850_client = getattr(protocol_handler, '_client', None)
                elif isinstance(protocol_handler, IEC61850ServerHandler):
                    iec61850_client = getattr(protocol_handler, '_server', None)

                if iec61850_client and hasattr(iec61850_client, 'files') and iec61850_client.files:
                    files_plugin = iec61850_client.files
                    root_entries = files_plugin.list_directory("")
                    for entry in root_entries:
                        entry_type = "📁" if entry.get("type") == "directory" else "📄"
                        size_str = entry.get("size_human", "")
                        file_items.append(f"{entry_type} {entry.get('name', '')} ({size_str})")
                    log.info(f"Files: 返回 {len(file_items)} 个根目录条目")
            except Exception as e:
                log.warning(f"获取 Files 信息失败: {e}")

        structure = {
            "GOOSE": goose_items, "Reports": report_items, "SettingGroups": [],
            "Files": file_items,
            "DataSets": dataset_items,
            "Data Model": data_model,
        }
        return BaseResponse(message="获取 IEC61850 结构成功", data=structure)
    except Exception as e:
        log.error(f"获取 IEC61850 结构失败: {e}")
        return BaseResponse(code=500, message=f"获取 IEC61850 结构失败: {e}", data={})


@router.post("/iec61850-table-data", response_model=BaseResponse)
async def get_iec61850_table_data(
    body: Iec61850TableDataRequest,
    request: Request,
):
    """根据 IEC61850 左侧树形节点获取当前表格数据"""
    try:
        channel = ChannelService.get_channel_by_id(body.channel_id)
        if not channel:
            return BaseResponse(code=404, message="通道不存在", data={})

        protocol_type = channel.get("protocol_type", -1)
        if protocol_type != 4:
            return BaseResponse(code=400, message="该通道不是 IEC61850 协议", data={})

        device_controller = request.app.state.device_controller
        device = device_controller.get_device_by_channel_id(body.channel_id)
        if not device:
            return BaseResponse(code=404, message="设备未找到", data={})

        pt_filter = []
        if body.point_types:
            try:
                pt_filter = [int(t.strip()) for t in body.point_types.split(",") if t.strip().isdigit()]
            except Exception:
                pt_filter = []
        if not pt_filter:
            pt_filter = [0, 1, 2, 3]

        head_data = device.get_table_head()
        all_table_rows = []

        for slave_id in device.slave_id_list:
            table_data, _ = device.get_table_data(
                slave_id=slave_id, name=body.point_name,
                page_index=None, page_size=None, point_types=pt_filter,
            )
            all_table_rows.extend(table_data)

        filtered_rows = _filter_iec61850_rows(all_table_rows, body.category, body.item)
        total_count = len(filtered_rows)

        start = (body.page_index - 1) * body.page_size
        end = start + body.page_size
        paged_rows = filtered_rows[start:end]

        data_dict = {
            "total": total_count, "head_data": head_data,
            "table_data": paged_rows, "category": body.category, "item": body.item,
        }
        return BaseResponse(message="获取 IEC61850 表格数据成功", data=data_dict)
    except Exception as e:
        log.error(f"获取 IEC61850 表格数据失败: {e}")
        return BaseResponse(code=500, message=f"获取 IEC61850 表格数据失败: {e}", data={})


@router.post("/iec61850-read-points", response_model=BaseResponse)
async def iec61850_read_points(
    body: Iec61850ReadPointsRequest,
    request: Request,
):
    """根据 IEC61850 左侧树形节点过滤，批量读取对应测点的值"""
    try:
        channel = ChannelService.get_channel_by_id(body.channel_id)
        if not channel:
            return BaseResponse(code=404, message="通道不存在", data={})

        protocol_type = channel.get("protocol_type", -1)
        if protocol_type != 4:
            return BaseResponse(code=400, message="该通道不是 IEC61850 协议", data={})

        device_controller = request.app.state.device_controller
        device = device_controller.get_device_by_channel_id(body.channel_id)
        if not device:
            return BaseResponse(code=404, message="设备未找到", data={})

        filtered_points = _get_iec61850_filtered_points(device, body.category, body.item)
        if not filtered_points:
            return BaseResponse(message="无匹配测点", data={"success": 0, "fail": 0})

        from src.enums.point_data import Yc, Yx
        from src.enums.points.change_tracker import ChangeSource, track_change
        from src.device.protocol.iec61850_handler import IEC61850ClientHandler

        yc_list = [p for p in filtered_points if isinstance(p, Yc)]
        yx_list = [p for p in filtered_points if isinstance(p, Yx)]

        # 判断是否为 IEC61850 客户端且支持批量读取
        protocol_handler = device.protocol_handler
        is_iec61850_client = isinstance(protocol_handler, IEC61850ClientHandler)
        has_batch = is_iec61850_client and hasattr(protocol_handler, 'read_points_batch')

        all_points = yc_list + yx_list
        success_count = 0
        fail_count = 0

        source = ChangeSource.CLIENT_READ if has_batch else ChangeSource.INTERNAL

        if has_batch:
            # 批量读取模式: 一次性读取所有测点
            batch_results = protocol_handler.read_points_batch(all_points)

            for point in all_points:
                value = batch_results.get(point.code)
                if value is not None:
                    with track_change(source, f"IEC61850批量读取 {point.code}"):
                        point.value = value
                    point.is_valid = True
                    success_count += 1
                else:
                    point.is_valid = False
                    fail_count += 1
        else:
            # 回退模式: 逐点读取 (服务端或旧版客户端)
            for point in all_points:
                try:
                    import asyncio
                    if body.interval_ms > 0:
                        await asyncio.sleep(body.interval_ms / 1000.0)

                    if hasattr(protocol_handler, 'read_value_async'):
                        value = await protocol_handler.read_value_async(point)
                    else:
                        value = protocol_handler.read_value(point)

                    if value is not None:
                        source = ChangeSource.CLIENT_READ if hasattr(protocol_handler, '_client') else ChangeSource.INTERNAL
                        with track_change(source, f"IEC61850批量读取 {point.code}"):
                            point.value = value
                        point.is_valid = True
                        success_count += 1
                    else:
                        point.is_valid = False
                        fail_count += 1
                except Exception as e:
                    device.log.error(f"读取测点 {point.code} 失败: {e}")
                    point.is_valid = False
                    fail_count += 1

        return BaseResponse(message="IEC61850 读取完成", data={"success": success_count, "fail": fail_count})
    except Exception as e:
        log.error(f"IEC61850 读取测点失败: {e}")
        return BaseResponse(code=500, message=f"IEC61850 读取测点失败: {e}", data={})


def _build_iec61850_dataset_tree(device, dataset_ref: str) -> Dict[str, Any]:
    """构建 DataSet 的树形结构（数据集成员作为 DA 列表）

    Args:
        device: 设备对象
        dataset_ref: DataSet 引用路径

    Returns:
        与 _build_iec61850_tree 格式一致的树形结构
    """
    if not device or not dataset_ref:
        return {"items": [], "total": 0}

    # 已知结构体 DA 到完整叶子 DA 路径的映射（兼容旧数据或格式不规范的 FCDA ref）
    _DA_PATH_AUTO_COMPLETE = {
        "mag": "mag.f", "instMag": "instMag.f", "cVal": "cVal.mag.f",
        "mxVal": "mxVal.f", "fCVal": "fCVal.mag.f",
        "wVal": "wVal.f", "setMag": "setMag.f",
        "Oper": "Oper.ctlVal", "SBOw": "SBOw.ctlVal",
        "Cancel": "Cancel.ctlVal", "origin": "origin.orCat",
    }

    protocol_handler = getattr(device, 'protocol_handler', None)
    if not protocol_handler:
        return {"items": [], "total": 0}

    # 获取 IEC61850 handler (客户端或服务端)
    from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler
    is_client = isinstance(protocol_handler, IEC61850ClientHandler)
    is_server = isinstance(protocol_handler, IEC61850ServerHandler)
    if not is_client and not is_server:
        return {"items": [], "total": 0}

    # 从 handler 获取已发现的 DataSet 列表
    if not hasattr(protocol_handler, 'get_discovered_datasets'):
        return {"items": [], "total": 0}
    discovered_datasets = protocol_handler.get_discovered_datasets()

    matched_ds = None
    for ds in discovered_datasets:
        if ds.get("ref") == dataset_ref:
            matched_ds = ds
            break

    # 按 ref 匹配不到时，尝试按 name 匹配（兼容前端用 name 作为 item 的场景）
    if not matched_ds:
        for ds in discovered_datasets:
            if ds.get("name") == dataset_ref:
                matched_ds = ds
                break

    if not matched_ds:
        return {"items": [], "total": 0}

    members = matched_ds.get("members", [])

    # 读取 DataSet 所有值
    values = {}
    if hasattr(protocol_handler, 'read_dataset_values'):
        values = protocol_handler.read_dataset_values(dataset_ref)

    # 记录读取时间（用于前端显示"最后更新时间"）
    import datetime
    read_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 按 DO 分组构建树
    do_map: Dict[str, Dict[str, Any]] = {}
    for member in members:
        ref = member.get("ref", "")
        fc = member.get("fc", "MX")
        value = values.get(ref, None)

        # 从 FCDA 引用中解析 DO/DA
        # 格式: "LD0/MMXU1.TotW.mag.f"
        ld = ""
        ln = ""
        do_name = ""
        da_path = ""
        do_ref = ""
        if "/" in ref:
            parts = ref.split("/", 1)
            ld = parts[0]
            remaining = parts[1]
            dot_idx = remaining.find(".")
            if dot_idx >= 0:
                ln = remaining[:dot_idx]
                path_part = remaining[dot_idx + 1:]
                first_dot = path_part.find(".")
                if first_dot >= 0:
                    do_name = path_part[:first_dot]
                    da_path = path_part[first_dot + 1:]
                    do_ref = f"{ld}/{ln}.{do_name}"
                else:
                    do_name = path_part
                    do_ref = f"{ld}/{ln}.{do_name}"
            else:
                do_name = remaining
                do_ref = ref

        # 自动补全 DA 路径（兼容旧数据：FCDA 可能只给到顶级 DA 名如 "mag" 而非完整路径 "mag.f"）
        if da_path:
            if da_path in _DA_PATH_AUTO_COMPLETE:
                da_path = _DA_PATH_AUTO_COMPLETE[da_path]
        else:
            # 无 DA 路径（如 ref 中不含 "."），直接使用 ref 作为 DO 标识
            do_name = ref
            do_ref = ref

        # 推断 frame_type
        frame_type = 0
        if da_path == "stVal":
            frame_type = 1
        elif da_path in ("ctlVal", "Oper.ctlVal"):
            frame_type = 2
        elif da_path in ("setVal", "setVal.f"):
            frame_type = 3

        # 构建 DO 分组
        if do_ref not in do_map:
            do_map[do_ref] = {
                "do_name": do_name,
                "do_ref": do_ref,
                "ld": ld,
                "ln": ln,
                "du_name": "",
                "fc": fc,
                "frame_type": frame_type,
                "children": [],
            }

        # 构建 DA 节点
        da_item = {
            "da_name": da_path if da_path else do_name,
            "da_path": da_path if da_path else do_name,
            "fc": fc,
            "is_struct": False,
            "point_code": ref,
            "point_name": da_path if da_path else do_name,
            "value": str(value) if value is not None else "",
            "status": "成功" if value is not None else "未知",
            "读取时间": read_time,
            "children": [],
        }

        # 检查是否已存在同名 DA
        existing_da_names = {d["da_name"] for d in do_map[do_ref]["children"]}
        if da_item["da_name"] not in existing_da_names:
            do_map[do_ref]["children"].append(da_item)

    items = sorted(do_map.values(), key=lambda x: x["do_ref"])
    return {"items": items, "total": len(items)}


def _get_iec61850_filtered_points(device, category: str, item: str) -> list[BasePoint]:
    """根据 IEC61850 树节点的 category 和 item 获取过滤后的测点对象列表"""
    from src.enums.point_data import Yc, Yx, Yk, Yt

    # DataSets 分类: 返回空(数据集不包含内部测点)
    if category and category == "DataSets":
        return []

    # GOOSE/Reports 等非 Data Model 分类没有 MMS 测点
    if category and category != "Data Model":
        return []

    all_points = []
    pm = device.point_manager
    for slave_id in device.slave_id_list:
        yc_list = pm.yc_dict.get(slave_id, [])
        yx_list = pm.yx_dict.get(slave_id, [])
        yk_list = pm.yk_dict.get(slave_id, [])
        yt_list = pm.yt_dict.get(slave_id, [])
        all_points.extend(yc_list + yx_list + yk_list + yt_list)

    if not category:
        return all_points

    if category == "Data Model" and item:
        result = []
        for point in all_points:
            address = str(point.address) if hasattr(point, 'address') else ""
            if address.startswith(f"{item}/") or address.startswith(f"{item}."):
                result.append(point)
        return result

    return all_points


@router.post("/iec61850-do-children", response_model=BaseResponse)
async def get_iec61850_do_children(
    body: Iec61850DoChildrenRequest,
    request: Request,
):
    """获取 IEC61850 指定 LN 下的数据对象 (DO) 列表"""
    try:
        channel = ChannelService.get_channel_by_id(body.channel_id)
        if not channel:
            return BaseResponse(code=404, message="通道不存在", data={})

        protocol_type = channel.get("protocol_type", -1)
        if protocol_type != 4:
            return BaseResponse(code=400, message="该通道不是 IEC61850 协议", data={})

        device_controller = request.app.state.device_controller
        device = device_controller.get_device_by_channel_id(body.channel_id)
        if not device:
            return BaseResponse(code=404, message="设备未找到", data={})

        do_items = []
        protocol_handler = getattr(device, 'protocol_handler', None)
        if protocol_handler:
            if hasattr(protocol_handler, '_client') and protocol_handler._client:
                client = protocol_handler._client
                if hasattr(client, 'browse_data_objects'):
                    do_items = client.browse_data_objects(body.ld, body.ln)
            elif hasattr(protocol_handler, '_server') and protocol_handler._server:
                server = protocol_handler._server
                if hasattr(server, 'browse_data_objects'):
                    do_items = server.browse_data_objects(body.ld, body.ln)

        return BaseResponse(message="获取 DO 列表成功", data={"items": do_items})
    except Exception as e:
        log.error(f"获取 IEC61850 DO 列表失败: {e}")
        return BaseResponse(code=500, message=f"获取 DO 列表失败: {e}", data={})


@router.post("/iec61850-da-children", response_model=BaseResponse)
async def get_iec61850_da_children(
    body: Iec61850DaChildrenRequest,
    request: Request,
):
    """获取 IEC61850 指定 DO 下的数据属性 (DA) 列表"""
    try:
        channel = ChannelService.get_channel_by_id(body.channel_id)
        if not channel:
            return BaseResponse(code=404, message="通道不存在", data={})

        protocol_type = channel.get("protocol_type", -1)
        if protocol_type != 4:
            return BaseResponse(code=400, message="该通道不是 IEC61850 协议", data={})

        device_controller = request.app.state.device_controller
        device = device_controller.get_device_by_channel_id(body.channel_id)
        if not device:
            return BaseResponse(code=404, message="设备未找到", data={})

        da_items = []
        protocol_handler = getattr(device, 'protocol_handler', None)
        if protocol_handler:
            if hasattr(protocol_handler, '_client') and protocol_handler._client:
                client = protocol_handler._client
                if hasattr(client, 'browse_data_attributes'):
                    da_items = client.browse_data_attributes(body.ld, body.ln, body.do_name)
            elif hasattr(protocol_handler, '_server') and protocol_handler._server:
                server = protocol_handler._server
                if hasattr(server, 'browse_data_attributes'):
                    da_items = server.browse_data_attributes(body.ld, body.ln, body.do_name)

        return BaseResponse(message="获取 DA 列表成功", data={"items": da_items})
    except Exception as e:
        log.error(f"获取 IEC61850 DA 列表失败: {e}")
        return BaseResponse(code=500, message=f"获取 DA 列表失败: {e}", data={})


def _filter_iec61850_rows(rows: list[str], category: str, item: str) -> list[str]:
    """根据 IEC61850 树节点的 category 和 item 过滤表格行"""
    if not category:
        return rows

    if category and category != "Data Model":
        return []

    if category == "Data Model" and item:
        result = []
        for row in rows:
            address = str(row[0]) if row else ""
            if address.startswith(f"{item}/") or address.startswith(f"{item}."):
                result.append(row)
        return result

    return rows


@router.post("/iec61850-read-point", response_model=BaseResponse)
async def iec61850_read_single_point(
    body: Iec61850ReadPointRequest,
    request: Request,
):
    """IEC61850 单点读取 - 通过 channel_id 定位设备，读取指定测点的值"""
    try:
        channel = ChannelService.get_channel_by_id(body.channel_id)
        if not channel:
            return BaseResponse(code=404, message="通道不存在", data={})

        protocol_type = channel.get("protocol_type", -1)
        if protocol_type != 4:
            return BaseResponse(code=400, message="该通道不是 IEC61850 协议", data={})

        device_controller = request.app.state.device_controller
        device = device_controller.get_device_by_channel_id(body.channel_id)
        if not device:
            return BaseResponse(code=404, message="设备未找到", data={})

        if not body.point_code:
            return BaseResponse(code=400, message="测点编码不能为空", data={})

        value = await device.read_single_point_async(body.point_code)
        if value is not None:
            return BaseResponse(message="读取成功", data={"value": value, "point_code": body.point_code})
        else:
            return BaseResponse(code=400, message="读取失败，请检查连接状态", data={"value": None, "point_code": body.point_code})
    except Exception as e:
        log.error(f"IEC61850 单点读取失败: {e}")
        return BaseResponse(code=500, message=f"IEC61850 单点读取失败: {e}", data={})


@router.post("/iec61850-write-point", response_model=BaseResponse)
async def iec61850_write_single_point(
    body: Iec61850WritePointRequest,
    request: Request,
):
    """IEC61850 单点写入 - 通过 channel_id 定位设备，写入指定测点的值"""
    try:
        channel = ChannelService.get_channel_by_id(body.channel_id)
        if not channel:
            return BaseResponse(code=404, message="通道不存在", data={})

        protocol_type = channel.get("protocol_type", -1)
        if protocol_type != 4:
            return BaseResponse(code=400, message="该通道不是 IEC61850 协议", data={})

        device_controller = request.app.state.device_controller
        device = device_controller.get_device_by_channel_id(body.channel_id)
        if not device:
            return BaseResponse(code=404, message="设备未找到", data={})

        if not body.point_code:
            return BaseResponse(code=400, message="测点编码不能为空", data={})

        success = await device.edit_point_data_async(body.point_code, body.point_value)
        if success:
            return BaseResponse(message="写入成功", data={"point_code": body.point_code, "value": body.point_value})
        else:
            return BaseResponse(code=400, message="写入失败", data={"point_code": body.point_code})
    except ValueError as e:
        return BaseResponse(code=400, message=str(e), data={"point_code": body.point_code})
    except Exception as e:
        log.error(f"IEC61850 单点写入失败: {e}")
        return BaseResponse(code=500, message=f"IEC61850 单点写入失败: {e}", data={})


@router.post("/iec61850-dataset-detail", response_model=BaseResponse)
async def get_iec61850_dataset_detail(
    body: Iec61850DatasetDetailRequest,
    request: Request,
):
    """获取 IEC61850 DataSet 的详细信息（成员列表及当前值）"""
    try:
        channel = ChannelService.get_channel_by_id(body.channel_id)
        if not channel:
            return BaseResponse(code=404, message="通道不存在", data={})

        protocol_type = channel.get("protocol_type", -1)
        if protocol_type != 4:
            return BaseResponse(code=400, message="该通道不是 IEC61850 协议", data={})

        device_controller = request.app.state.device_controller
        device = device_controller.get_device_by_channel_id(body.channel_id)
        if not device:
            return BaseResponse(code=404, message="设备未找到", data={})

        from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler
        protocol_handler = getattr(device, 'protocol_handler', None)
        is_iec61850 = isinstance(protocol_handler, (IEC61850ClientHandler, IEC61850ServerHandler))
        if not is_iec61850:
            return BaseResponse(code=400, message="仅 IEC61850 协议支持 DataSet 操作", data={})

        # 优先实时浏览 DataSet 目录（获取最新成员信息）
        matched_ds = None
        if isinstance(protocol_handler, IEC61850ClientHandler) and hasattr(protocol_handler.client, 'browse_dataset_directory'):
            members = protocol_handler.client.browse_dataset_directory(body.dataset_ref)
            matched_ds = {
                "ref": body.dataset_ref,
                "name": body.dataset_ref.split("$")[-1] if "$" in body.dataset_ref else body.dataset_ref,
                "member_count": len(members),
                "members": members,
            }

        # 如果实时浏览失败，从缓存查找
        if (not matched_ds or matched_ds.get("member_count", 0) == 0) and hasattr(protocol_handler, 'get_discovered_datasets'):
            for ds in protocol_handler.get_discovered_datasets():
                if ds.get("ref") == body.dataset_ref:
                    matched_ds = ds
                    break

        if not matched_ds:
            return BaseResponse(code=404, message="DataSet 未找到，请先连接设备获取结构", data={})

        # 读取 DataSet 所有成员的值
        values = {}
        if hasattr(protocol_handler, 'read_dataset_values'):
            values = protocol_handler.read_dataset_values(body.dataset_ref)

        # 将值合并到成员列表
        members = matched_ds.get("members", [])
        for member in members:
            ref = member.get("ref", "")
            member["value"] = values.get(ref, None)

        return BaseResponse(message="获取 DataSet 详情成功", data={
            "ref": matched_ds.get("ref", ""),
            "name": matched_ds.get("name", ""),
            "ld": matched_ds.get("ld", ""),
            "member_count": len(members),
            "members": members,
        })
    except Exception as e:
        log.error(f"获取 DataSet 详情失败: {e}")
        return BaseResponse(code=500, message=f"获取 DataSet 详情失败: {e}", data={})
