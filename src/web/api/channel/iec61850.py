"""通道管理 - IEC 61850 相关路由"""

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from src.data.service.channel_service import ChannelService
from src.enums.points.base_point import BasePoint
from src.proto.iec61850.defs.mms_types import MmsType, infer_mms_type_from_path
from src.web.api.exceptions import ConflictError, NotFoundError, ValidationError
from src.web.api.schemas import BaseResponse
from src.web.log import log

router = APIRouter(tags=["channel"])


def _format_goose_app_id(value: Any) -> str:
    """把 GOOSE APPID 规范化为前端展示和配置保存使用的十六进制文本。"""
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        text = value.strip()
        try:
            value = int(text[2:] if text.lower().startswith("0x") else text, 16)
        except ValueError:
            return text
    try:
        return f"0x{int(value):04X}"
    except (TypeError, ValueError):
        return str(value)


def _normalize_dataset_ref(value: str) -> str:
    """规范化数据集引用。"""
    ref = str(value or "").strip()
    slash_index = ref.rfind("/")
    if slash_index < 0 or "$" in ref[slash_index:]:
        return ref
    separator_index = ref.find(".", slash_index)
    if separator_index < 0:
        return ref
    return f"{ref[:separator_index]}${ref[separator_index + 1 :]}"


def _dataset_ref_aliases(value: str) -> tuple[str, ...]:
    """生成数据集引用的点号、美元符等别名，用于匹配不同来源的配置。"""
    normalized = _normalize_dataset_ref(value)
    aliases = [normalized]
    slash_index = normalized.rfind("/")
    separator_index = normalized.find("$", slash_index)
    if separator_index >= 0:
        aliases.append(f"{normalized[:separator_index]}.{normalized[separator_index + 1 :]}")
    return tuple(dict.fromkeys(alias for alias in aliases if alias))


def _get_iec61850_device(request: Request, channel_id: int):
    """获取 IEC61850 设备，校验通道存在且协议为 IEC61850

    Raises:
        NotFoundError: 通道或设备不存在
        ValidationError: 协议不是 IEC61850
    Returns:
        device 实例
    """
    channel = ChannelService.get_channel_by_id(channel_id)
    if not channel:
        raise NotFoundError("通道不存在")

    protocol_type = channel.get("protocol_type", -1)
    if protocol_type != 4:
        raise ValidationError("该通道不是 IEC61850 协议")

    device_controller = request.app.state.device_controller
    device = device_controller.get_device_by_channel_id(channel_id)
    if not device:
        raise NotFoundError("设备未找到")

    return device


# ===== IEC61850 POST 请求模型 =====


class Iec61850ReadPointsRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    category: str = Field("", description="IED/LD 分类过滤")
    item: str = Field("", description="LN 实例过滤")
    interval_ms: int = Field(0, description="读取间隔(ms)")


class Iec61850ReadPointRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    point_code: str = Field(..., description="测点编码")
    fc: str = Field("", description="功能约束；模型固有属性直读时使用")
    mms_type: str = Field("", description="模型声明的 MMS 类型")


class Iec61850ReadMetadataRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    point_code: str = Field(..., description="测点编码")


class Iec61850WritePointRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    point_code: str = Field(..., description="测点编码")
    point_value: float | str = Field(0, description="写入值")


class Iec61850StructureRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")


class Iec61850TreeDataRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    category: str = Field("", description="IED/LD 分类过滤")
    item: str = Field("", description="LN 实例过滤")
    point_name: str | None = Field(None, description="测点名称过滤")
    point_types: str = Field("", description="帧类型过滤")
    page_index: int = Field(1, description="页码")
    page_size: int = Field(10, description="每页条数")


class Iec61850TableDataRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    category: str = Field("", description="IED/LD 分类过滤")
    item: str = Field("", description="LN 实例过滤")
    point_name: str | None = Field(None, description="测点名称过滤")
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
KNOWN_STRUCT_DA_BDAS: dict[str, list[str]] = {
    "origin": ["orCat", "orIdent"],
}

# 每个 DO 应包含的标准 DA 列表 (后端自动补全)
# q 和 t 是单值 DataAttribute, 非结构体
STANDARD_DAS_FOR_DO: list[dict[str, Any]] = [
    {"name": "q", "fc": "MX", "is_struct": False},
    {"name": "t", "fc": "MX", "is_struct": False},
    {"name": "dU", "fc": "DC", "is_struct": False},
]

# DA 名称 → 默认 FC 映射
DA_NAME_FC_MAP: dict[str, str] = {
    "mag": "MX",
    "instMag": "MX",
    "cVal": "MX",
    "f": "MX",
    "stVal": "ST",
    "ctlVal": "CO",
    "setVal": "CO",
    "q": "MX",
    "t": "MX",
    "dU": "DC",
    "origin": "OR",
    "subVal": "SV",
    "blkEna": "BL",
    "SBO": "CO",
    "Oper": "CO",
    "Cancel": "CO",
}


def _parse_iec61850_address(address: str) -> dict[str, str] | None:
    """解析 IEC 61850 地址, 提取 LD/LN/DO/DA 层级

    示例: "LD0/LLN0.Mod.mag.f" → {ld: "LD0", ln: "LLN0", do_name: "Mod", da_path: "mag.f"}
    """
    if not address or "/" not in address:
        return None
    slash_idx = address.index("/")
    rest = address[slash_idx + 1 :]
    dot_idx = rest.find(".")
    if dot_idx < 0:
        return None  # 无 DO/DA 结构
    ld = address[:slash_idx]
    ln = rest[:dot_idx]
    da_part = rest[dot_idx + 1 :]
    first_dot = da_part.find(".")
    if first_dot >= 0:
        do_name = da_part[:first_dot]
        da_path = da_part[first_dot + 1 :]
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


_CONTROL_VALUE_SUFFIXES = (".Oper.ctlVal", ".SBOw.ctlVal", ".ctlVal")
_DIRECT_MMS_WRITE_FCS = frozenset({"SP", "SE", "SV", "CF", "DC", "SG", "BL", "EX"})


def _is_control_value_address(address: str) -> bool:
    """判断测点地址是否指向可执行控制值，而不是普通状态或测量属性。"""
    return str(address).endswith(_CONTROL_VALUE_SUFFIXES)


def _resolve_control_write_code(device, point_code: str) -> str:
    """根据目标控制属性和值选择 Web 接口返回的控制写入结果码。"""
    point = device.point_manager.get_point_by_code(point_code)
    if point is None:
        return point_code
    point_fc = str(getattr(point, "fc", "") or "").upper()
    if point_fc in _DIRECT_MMS_WRITE_FCS:
        return point_code
    if point_fc == "CO" and _is_control_value_address(str(point.address)):
        return point_code
    requested_ref = _parse_iec61850_address(str(point.address))
    if not requested_ref:
        return point_code

    candidates = []
    for candidate in device.point_manager.get_all_points():
        if getattr(candidate, "fc", "") != "CO" or not _is_control_value_address(str(candidate.address)):
            continue
        candidate_ref = _parse_iec61850_address(str(candidate.address))
        if not candidate_ref:
            continue
        if all(candidate_ref[key] == requested_ref[key] for key in ("ld", "ln", "do_name")):
            candidates.append(candidate)

    if not candidates:
        return ""

    candidates.sort(
        key=lambda candidate: (
            not str(candidate.address).endswith(".Oper.ctlVal"),
            not str(candidate.address).endswith(".SBOw.ctlVal"),
        )
    )
    return str(candidates[0].code)


def _get_cached_iec61850_model(device):
    """从 IEC61850 客户端处理器获取最近一次发现的完整 IedModel。"""
    protocol_handler = getattr(device, "protocol_handler", None)
    client = getattr(protocol_handler, "_client", None) if protocol_handler else None
    return getattr(client, "model", None) if client else None


def _point_value_and_status(point: BasePoint) -> tuple[str, str]:
    """提取前端展示用的测点值和读取状态。"""
    from src.enums.point_data import Yc, Yk, Yt, Yx

    point_fc = getattr(point, "fc", "") or ""
    is_valid = getattr(point, "is_valid", None)
    status = "成功" if is_valid is True else ("失败" if is_valid is False else "未知")

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
    return value, status


def _build_point_display_index(all_points: list[BasePoint]) -> dict[str, dict[str, Any]]:
    """按 IEC61850 完整地址索引已注册测点，供模型树叠加值/状态。"""
    index: dict[str, dict[str, Any]] = {}
    for point in all_points:
        address = str(point.address)
        value, status = _point_value_and_status(point)
        index[address] = {
            "point_code": str(point.code),
            "point_name": str(point.name),
            "value": value,
            "status": status,
            "fc": getattr(point, "fc", "") or "",
            "frame_type": point.frame_type,
        }
    return index


def _build_do_description_index(point_index: dict[str, dict[str, Any]]) -> dict[str, str]:
    """从测点名称恢复 ``DO ref -> dU`` 映射。

    在线发现不会把 dU 注册成独立测点；客户端会把读到的 dU 写入该
    DO 下所有已注册测点的 name。自动生成且未读到 dU 的测点则保持
    ``name == code``，必须排除，避免把 ``MMXU1.TotW.mag.f`` 当成描述。
    """
    descriptions: dict[str, str] = {}
    for address, info in point_index.items():
        parsed = _parse_iec61850_address(address)
        if not parsed:
            continue
        ld = parsed["ld"]
        ln = parsed["ln"]
        do_name = parsed["do_name"]
        point_name = str(info.get("point_name", "")).strip()
        point_code = str(info.get("point_code", "")).strip()
        if not point_name or point_name in (do_name, point_code, address):
            continue
        descriptions.setdefault(f"{ld}/{ln}.{do_name}", point_name)
    return descriptions


def _matches_iec61850_model_item(ld: str, ln: str, item: str) -> bool:
    """匹配 DataModel 左侧树过滤项，item 可为 LD 或 LD/LN。"""
    if not item:
        return True
    return item == ld or item == f"{ld}/{ln}"


def _build_iec61850_tree_from_model(
    model,
    all_points: list[BasePoint],
    category: str = "",
    item: str = "",
    point_name: str | None = None,
    point_types: list[int] | None = None,
    *,
    include_unknown: bool = False,
    registry=None,
    offset: int = 0,
    limit: int | None = None,
) -> dict[str, Any]:
    """把扁平 IED 模型组织成逻辑设备、逻辑节点、数据对象和数据属性树。"""
    if category and category != "DataModel":
        return {"items": [], "total": 0}

    if point_types is None:
        point_types = [0, 1, 2, 3]

    point_index = _build_point_display_index(all_points)
    do_description_index = _build_do_description_index(point_index)
    point_names_by_do: dict[str, list[str]] = {}
    for address, info in point_index.items():
        parsed = _parse_iec61850_address(address)
        if parsed:
            do_key = f"{parsed['ld']}/{parsed['ln']}.{parsed['do_name']}"
            point_names_by_do.setdefault(do_key, []).append(str(info.get("point_name", "")))

    items: list[dict[str, Any]] = []
    total = 0
    normalized_offset = max(offset, 0)
    normalized_limit = None if limit is None else max(limit, 0)

    def resolved_mms_type(address: str, fallback: str = "MMS_UNKNOWN") -> str:
        """优先采用请求中明确指定的 MMS 类型，否则从测点元数据推断。"""
        if registry is not None:
            getter = getattr(registry, "get_mms_type", None)
            if callable(getter):
                cached = getter(address)
                if cached:
                    return str(cached)
        return str(fallback or "MMS_UNKNOWN")

    priority_order = {
        "mag": 0,
        "instMag": 0,
        "cVal": 0,
        "mxVal": 0,
        "stVal": 0,
        "ctlVal": 0,
        "setVal": 0,
        "Oper": 1,
        "Cancel": 1,
        "origin": 2,
        "q": 3,
        "t": 4,
        "dU": 5,
    }

    for ld in model.lds:
        for ln in ld.lns:
            if not _matches_iec61850_model_item(ld.name, ln.name, item):
                continue
            for do in ln.dos:
                if do.frame_type not in point_types and not (include_unknown and do.frame_type < 0):
                    continue
                do_ref = do.ref
                do_desc = do_description_index.get(do_ref, "")
                if point_name and point_name not in do.name and point_name not in do_ref:
                    matched_point_name = point_name in do_desc or any(
                        point_name in name for name in point_names_by_do.get(do_ref, ())
                    )
                    if not matched_point_name:
                        continue

                item_index = total
                total += 1
                if item_index < normalized_offset:
                    continue
                if normalized_limit is not None and len(items) >= normalized_limit:
                    continue

                is_control_object = any(da.fc == "CO" or any(bda.fc == "CO" for bda in da.sub_das) for da in do.das)
                da_list: list[dict[str, Any]] = []
                for da in do.das:
                    if is_control_object and da.name in ("q", "t"):
                        continue
                    da_path = da.name if da.sub_das else da.path
                    da_addr = f"{do_ref}.{da.path}"
                    da_point = point_index.get(da_addr, {})
                    da_value = da_point.get("value", "")
                    da_name = da_point.get("point_name") or da.name
                    if da.name == "dU":
                        if da_value:
                            do_desc = da_value
                        elif do_desc:
                            # dU 不作为独立测点注册，使用客户端已写入普通
                            # 子测点 name 的描述值补全模型树中的虚拟 dU 行。
                            da_value = do_desc
                            da_name = do_desc

                    children = []
                    for bda in da.sub_das:
                        bda_addr = f"{do_ref}.{bda.path}"
                        bda_point = point_index.get(bda_addr, {})
                        bda_fc = bda_point.get("fc") or bda.fc or da.fc
                        bda_point_code = bda_point.get("point_code", "")
                        if not bda_point_code and bda_fc != "CO" and da.name not in ("q", "t"):
                            bda_point_code = bda_addr
                        children.append(
                            {
                                "bda_name": bda.name,
                                "bda_path": bda.path,
                                "fc": bda_fc,
                                "point_code": bda_point_code,
                                "mms_type": resolved_mms_type(bda_addr, bda.mms_type),
                                "value": bda_point.get("value", ""),
                                "status": bda_point.get("status", ""),
                            }
                        )
                        if not da_value and bda_point.get("value"):
                            da_value = bda_point["value"]

                    da_fc = da_point.get("fc") or da.fc or _infer_fc_from_da(da_path)
                    da_point_code = da_point.get("point_code", "")
                    if not da_point_code and not children and da_fc != "CO" and da.name not in ("q", "t"):
                        da_point_code = da_addr
                    da_list.append(
                        {
                            "da_name": da.name,
                            "da_path": da_path,
                            "fc": da_fc,
                            "is_struct": bool(children),
                            "point_code": da_point_code,
                            "mms_type": (
                                "MMS_STRUCTURE"
                                if children and da.mms_type == "MMS_STRUCTURE"
                                else resolved_mms_type(da_addr, da.mms_type)
                            ),
                            "point_name": da_name,
                            "value": da_value,
                            "status": da_point.get("status", ""),
                            "children": children,
                        }
                    )

                da_list.sort(key=lambda d: priority_order.get(d["da_name"], 2))

                da_statuses = [d["status"] for d in da_list if d.get("status")]
                for da in da_list:
                    da_statuses.extend(bda["status"] for bda in da.get("children", []) if bda.get("status"))
                if any(s == "失败" for s in da_statuses):
                    do_status = "失败"
                elif all(s == "成功" for s in da_statuses) and da_statuses:
                    do_status = "成功"
                else:
                    do_status = "未知"

                primary_fc = da_list[0]["fc"] if da_list else ""
                primary_mms_type = infer_mms_type_from_path(do.name).value
                if primary_mms_type == MmsType.UNKNOWN.value:
                    for da_item in da_list:
                        if da_item.get("children"):
                            value_child = next(
                                (child for child in da_item["children"] if child.get("point_code")),
                                None,
                            )
                            if value_child is not None:
                                primary_mms_type = value_child.get("mms_type", "MMS_UNKNOWN")
                                break
                        if da_item.get("point_code"):
                            primary_mms_type = da_item.get("mms_type", "MMS_UNKNOWN")
                            break
                items.append(
                    {
                        "do_name": do.name,
                        "do_ref": do_ref,
                        "ld": ld.name,
                        "ln": ln.name,
                        "du_name": do_desc,
                        "fc": primary_fc,
                        "frame_type": do.frame_type,
                        "mms_type": primary_mms_type,
                        "status": do_status,
                        "children": da_list,
                    }
                )

    return {"items": items, "total": total}


def _build_iec61850_tree(
    all_points: list[BasePoint],
    category: str = "",
    item: str = "",
    point_name: str | None = None,
    point_types: list[int] | None = None,
    device=None,
) -> dict[str, Any]:
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
    from src.enums.point_data import Yc, Yk, Yt, Yx

    if point_types is None:
        point_types = [0, 1, 2, 3]

    # DataSets 分类: 从设备 handler 获取数据集成员信息
    if category and category == "DataSets":
        return _build_iec61850_dataset_tree(device, item)

    # category 过滤: 非 DataModel 分类 (如 GOOSE/Reports) 无 MMS 测点
    if category and category != "DataModel":
        return {"items": [], "total": 0}

    # 获取 mms_type 映射
    # 服务端：从 IedModelBuilder._point_mms_type 获取
    # 客户端：从 PointRegistry.get_mms_type 逐个获取（ICD 导入时已缓存）
    _point_mms_type_map: dict[str, str] = {}
    _client_mms_getter = None
    if device:
        try:
            handler = getattr(device, "protocol_handler", None)
            server = getattr(handler, "_server", None) if handler else None
            if server is not None:
                _point_mms_type_map = server._point_mms_type
            else:
                # 客户端路径：从 PointRegistry 获取
                client = getattr(handler, "_client", None) if handler else None
                registry = getattr(client, "_registry", None) if client else None
                if registry is not None:
                    getter = getattr(registry, "get_mms_type", None)
                    if callable(getter):
                        _client_mms_getter = getter
        except Exception:
            pass

    def _resolve_mms_type(address: str, fallback: str = "MMS_UNKNOWN") -> str:
        """获取地址的 mms_type，优先服务端映射，其次客户端 registry"""
        mms_type = _point_mms_type_map.get(address, "")
        if not mms_type and _client_mms_getter is not None:
            try:
                mms_type = _client_mms_getter(address) or ""
            except Exception:
                pass
        return mms_type or fallback

    def _infer_tree_mms_type(path: str, *, is_struct: bool = False) -> str:
        """根据树节点的已知类型和标准属性路径补齐 MMS 类型。"""
        if is_struct:
            return MmsType.STRUCTURE.value
        return infer_mms_type_from_path(path).value

    # 1. 收集所有测点, 构建 DO 分组

    do_map: dict[str, dict[str, Any]] = {}  # do_ref → {do_info, children_map}

    for point in all_points:
        # 帧类型过滤
        ft = point.frame_type
        if ft not in point_types:
            continue

        # 名称过滤
        if point_name and point_name not in str(point.name):
            continue

        address = str(point.address)
        parsed = _parse_iec61850_address(address)
        if not parsed:
            continue

        # category/item 过滤
        if category == "DataModel" and item:
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
                "da_map": {},  # da_path → da_info (实际从后端返回的 DA)
                "da_top_names": set(),  # 顶级 DA 名称集合
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
            bda_name = da_path[len(top_da) + 1 :]

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
                    "mms_type": _infer_tree_mms_type(top_da, is_struct=True),
                    "children": [],
                }

            # 添加 BDA
            parent_da = do_info["da_map"][top_da]
            # 检查是否已有同名 BDA
            existing_bda_names = {b.get("bda_name") for b in parent_da["children"]}
            if bda_name not in existing_bda_names:
                bda_point_code = str(point.code)
                parent_da["children"].append(
                    {
                        "bda_name": bda_name,
                        "bda_path": da_path,
                        "fc": point_fc or parent_da["fc"],
                        "point_code": bda_point_code,
                        "value": value,
                        "status": status,
                        "mms_type": _resolve_mms_type(address, _infer_tree_mms_type(da_path)),
                    }
                )
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
                    "mms_type": _resolve_mms_type(
                        address,
                        _infer_tree_mms_type(da_path, is_struct=is_struct),
                    ),
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
    for _do_ref, do_info in do_map.items():
        da_map = do_info["da_map"]
        top_names = do_info["da_top_names"]
        main_fc = do_info["fc"]
        is_control_object = main_fc == "CO" or any(
            da.get("fc") == "CO" or any(bda.get("fc") == "CO" for bda in da.get("children", []))
            for da in da_map.values()
        )

        if is_control_object:
            da_map.pop("q", None)
            da_map.pop("t", None)

        # q/t 的 FC 根据主值类型推断 (遥测=MX, 遥信=ST)
        qt_fc = "ST" if main_fc == "ST" else "MX"

        for std_da in STANDARD_DAS_FOR_DO:
            da_name = std_da["name"]
            if is_control_object and da_name in ("q", "t"):
                continue
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
                "mms_type": _infer_tree_mms_type(da_name, is_struct=is_struct),
                "children": [
                    {
                        "bda_name": bda,
                        "bda_path": f"{da_name}.{bda}",
                        "fc": fc,
                        "point_code": "",
                        "value": "",
                        "status": "",
                        "mms_type": _infer_tree_mms_type(f"{da_name}.{bda}"),
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
                    da_entry["children"].append(
                        {
                            "bda_name": bda_name,
                            "bda_path": f"{da_name}.{bda_name}",
                            "fc": da_entry["fc"],
                            "point_code": "",
                            "value": "",
                            "status": "",
                            "mms_type": _infer_tree_mms_type(f"{da_name}.{bda_name}"),
                        }
                    )

    # 3. 组装最终树形列表 (按 do_ref 排序)
    items = []
    for do_ref in sorted(do_map.keys()):
        do_info = do_map[do_ref]
        # DA 排序: 主值 DA 在前, q/t/dU 在后
        da_list = list(do_info["da_map"].values())
        # 按 DA 名称排序, 主值优先
        priority_order = {
            "mag": 0,
            "instMag": 0,
            "cVal": 0,
            "stVal": 0,
            "ctlVal": 0,
            "setVal": 0,
            "Oper": 1,
            "Cancel": 1,
            "origin": 2,
            "q": 3,
            "t": 4,
            "dU": 5,
        }
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

        # DO 级 mms_type: 取第一个有点码且非空的 DA 子节点的 mms_type
        do_mms_type = infer_mms_type_from_path(do_info["do_name"]).value
        if do_mms_type == MmsType.UNKNOWN.value:
            for da in da_list:
                if da.get("point_code") and da.get("mms_type"):
                    do_mms_type = da["mms_type"]
                    break
                for bda in da.get("children", []):
                    if bda.get("point_code") and bda.get("mms_type"):
                        do_mms_type = bda["mms_type"]
                        break
                if do_mms_type != MmsType.UNKNOWN.value:
                    break

        items.append(
            {
                "do_name": do_info["do_name"],
                "do_ref": do_info["do_ref"],
                "ld": do_info["ld"],
                "ln": do_info["ln"],
                "du_name": do_info["du_name"] or do_info.get("desc", ""),
                "fc": do_info["fc"],
                "frame_type": do_info["frame_type"],
                "status": do_status,
                "mms_type": do_mms_type,
                "children": da_list,
            }
        )

    return {"items": items, "total": len(items)}


def _paginate_iec61850_dataset_tree(tree_data: dict[str, Any], page_index: int, page_size: int) -> dict[str, Any]:
    """按前端实际展示的 DataSet 成员行分页，并保留其 DO 分组结构。"""
    items = tree_data.get("items") or []
    total = sum(len(item.get("children") or []) for item in items)
    start = max(page_index - 1, 0) * max(page_size, 1)
    end = start + max(page_size, 1)

    paged_items: list[dict[str, Any]] = []
    member_offset = 0
    for item in items:
        children = item.get("children") or []
        item_end = member_offset + len(children)
        if item_end > start and member_offset < end:
            child_start = max(start - member_offset, 0)
            child_end = min(end - member_offset, len(children))
            paged_item = dict(item)
            paged_item["children"] = children[child_start:child_end]
            paged_items.append(paged_item)
        member_offset = item_end
        if member_offset >= end:
            break

    return {**tree_data, "items": paged_items, "total": total}


@router.post("/iec61850-tree-data", response_model=BaseResponse)
async def get_iec61850_tree_data(
    body: Iec61850TreeDataRequest,
    request: Request,
):
    """获取 IEC61850 树形表格数据。

    DataModel 按 DO 分页；DataSets 因前端平铺成员，按 DataSet 成员分页。
    """
    device = _get_iec61850_device(request, body.channel_id)

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

    model = _get_cached_iec61850_model(device)
    if model is not None and (not body.category or body.category == "DataModel"):
        protocol_handler = getattr(device, "protocol_handler", None)
        client = getattr(protocol_handler, "_client", None) if protocol_handler else None
        registry = getattr(client, "_registry", None) if client else None
        start = (body.page_index - 1) * body.page_size
        tree_data = _build_iec61850_tree_from_model(
            model,
            all_points,
            category=body.category,
            item=body.item,
            point_name=body.point_name,
            point_types=pt_filter,
            include_unknown=not bool(body.point_types),
            registry=registry,
            offset=start,
            limit=body.page_size,
        )
        paged_items = tree_data["items"]
    else:
        # DataSet 或无缓存模型时保持原有从 PointManager 反推树的逻辑
        tree_data = _build_iec61850_tree(
            all_points,
            category=body.category,
            item=body.item,
            point_name=body.point_name,
            point_types=pt_filter,
            device=device,
        )
        if body.category == "DataSets":
            tree_data = _paginate_iec61850_dataset_tree(tree_data, body.page_index, body.page_size)
            paged_items = tree_data["items"]
        else:
            start = (body.page_index - 1) * body.page_size
            end = start + body.page_size
            paged_items = tree_data["items"][start:end]

    total = tree_data["total"]

    return BaseResponse(
        message="获取 IEC61850 树形数据成功",
        data={**tree_data, "items": paged_items, "total": total},
    )


def _extract_lds_from_points(device) -> list[str]:
    """从 PointManager 的测点地址中提取唯一 LD 列表（MMS 不可用时 fallback）"""
    seen: set[str] = set()
    result: list[str] = []
    pm = getattr(device, "point_manager", None)
    if not pm:
        return result
    for slave_id in device.slave_id_list:
        for point in pm.yc_dict.get(slave_id, []) + pm.yx_dict.get(slave_id, []):
            addr = str(point.address)
            if "/" in addr:
                ld = addr.split("/")[0]
                if ld not in seen:
                    seen.add(ld)
                    result.append(ld)
    return result


def _extract_lns_from_points(device, ld: str) -> list[str]:
    """从 PointManager 的测点地址中提取指定 LD 下的 LN 列表（MMS 不可用时 fallback）"""
    seen: set[str] = set()
    result: list[str] = []
    pm = getattr(device, "point_manager", None)
    if not pm:
        return result
    for slave_id in device.slave_id_list:
        for point in pm.yc_dict.get(slave_id, []) + pm.yx_dict.get(slave_id, []):
            addr = str(point.address)
            if addr.startswith(f"{ld}/"):
                rest = addr[len(ld) + 1 :]
                if "." in rest:
                    ln = rest[: rest.index(".")]
                    if ln not in seen:
                        seen.add(ln)
                        result.append(ln)
    return result


@router.post("/iec61850-structure", response_model=BaseResponse)
async def get_iec61850_structure(body: Iec61850StructureRequest, request: Request):
    """获取 IEC61850 设备的子节点结构树"""
    log.info(f"get_iec61850_structure 请求, channel_id={body.channel_id}")
    device = _get_iec61850_device(request, body.channel_id)

    logical_devices = []
    protocol_handler = getattr(device, "protocol_handler", None)
    client_connected = False
    if protocol_handler:
        from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler

        if isinstance(protocol_handler, IEC61850ClientHandler):
            client = protocol_handler._client
            client_connected = bool(client and protocol_handler.is_running)
            if client:
                logical_devices = client.browse_logical_devices()
            # 如果 MMS 连接不可用（ICD 离线模式），从 PointManager 解析 LD/LN
            if not logical_devices:
                logical_devices = _extract_lds_from_points(device)
            data_model = []
            for ld in logical_devices:
                lns = client.browse_logical_nodes(ld) if client and client._conn.is_connected else []
                if not lns:
                    lns = _extract_lns_from_points(device, ld)
                data_model.append({"name": ld, "children": lns})
        elif isinstance(protocol_handler, IEC61850ServerHandler):
            server = protocol_handler._server
            if server:
                logical_devices = server.browse_logical_devices()
            # 获取每个 LD 下的 LN 列表
            data_model = []
            for ld in logical_devices:
                lns = server.browse_logical_nodes(ld) if server else []
                data_model.append({"name": ld, "children": lns})

    # 获取 GOOSE 信息（本机发布者）
    goose_items = []
    goose_manager = getattr(request.app.state, "goose_manager", None)
    if goose_manager:
        try:
            goose_status = goose_manager.get_all_status()
            for pub in goose_status.get("publishers", []):
                goose_items.append(f"Pub: {pub.get('go_cb_ref', '')} ({'运行' if pub.get('is_running') else '停止'})")
            for recv in goose_status.get("receivers", []):
                goose_items.append(
                    f"Recv: {recv.get('interface', '')} ({'运行' if recv.get('is_running') else '停止'})"
                )
        except Exception as e:
            log.warning(f"获取本机 GOOSE 状态失败: {e}")

    # 如果是客户端设备，补充远端发现的 GOOSE 控制块和 DataSet
    dataset_items = []
    if device.protocol_handler:
        protocol_handler = device.protocol_handler
        discovered_goose = getattr(protocol_handler, "_discovered_goose_items", None)
        if discovered_goose:
            for g in discovered_goose:
                cb_ref = g.get("go_cb_ref", "")
                app_id = g.get("app_id")
                app_id_str = _format_goose_app_id(app_id)
                status = "已发现"
                goose_items.append(f"远端GoCB: {cb_ref} ({status}, APPID={app_id_str})")

        # 获取 DataSet 列表（含成员信息），按 LD > LN 组织层级
        from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler

        if isinstance(protocol_handler, (IEC61850ClientHandler, IEC61850ServerHandler)):
            discovered_datasets = protocol_handler.get_discovered_datasets()
            if discovered_datasets or client_connected or isinstance(protocol_handler, IEC61850ServerHandler):
                log.info(
                    f"get_discovered_datasets() 返回 {len(discovered_datasets)} 个 DataSet: "
                    + ", ".join(f"{d.get('ld', '')}/{d.get('ln', '')}.{d.get('name', '')}" for d in discovered_datasets)
                )
            else:
                log.debug("IEC61850 客户端未连接，DataSet 使用空缓存")
            # 构建 LD -> {LN -> [datasets]} 层级映射
            ld_map: dict[str, dict[str, list]] = {}
            for ds in discovered_datasets:
                ds_ld = ds.get("ld", "")
                ds_ln = ds.get("ln", "")
                if not ds_ld:
                    continue
                if ds_ld not in ld_map:
                    ld_map[ds_ld] = {}
                if ds_ln not in ld_map[ds_ld]:
                    ld_map[ds_ld][ds_ln] = []
                ld_map[ds_ld][ds_ln].append(
                    {
                        "ref": _normalize_dataset_ref(ds.get("ref", "")),
                        "name": ds.get("name", ""),
                        "ld": ds_ld,
                        "ln": ds_ln,
                        "member_count": ds.get("member_count", 0),
                    }
                )
            # 转换为层级树: [{name: "LD0", children: [{name: "LLN0", datasets: [...]}]}]
            # 保持 ICD 中的原始 LD/LN/DataSet 顺序，不排序
            for ld_name, ln_dict in ld_map.items():
                ln_items = []
                for ln_name, ds_list in ln_dict.items():
                    ln_node = {
                        "name": ln_name,
                        "datasets": ds_list,
                    }
                    ln_items.append(ln_node)
                dataset_items.append(
                    {
                        "name": ld_name,
                        "children": ln_items,
                    }
                )

    # 获取 Reports 信息（通过 ReportsPlugin 发现远端 RCB）
    report_items = []
    if protocol_handler:
        try:
            from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler

            if isinstance(protocol_handler, IEC61850ClientHandler):
                # 优先用连接时缓存的 RCB，避免首屏现场探测导致空白
                rcbs = protocol_handler.get_discovered_rcbs()
                client = getattr(protocol_handler, "_client", None)
                # 只在设备已连接时才尝试现场发现，避免只读接口静默触发 MMS 连接
                if not rcbs and client_connected and client and client.reports:
                    rcbs = client.reports.discover_rcbs()
                    # 现场发现成功则回写缓存，供 /reports 页面复用
                    if rcbs:
                        protocol_handler.set_discovered_rcbs(rcbs)
                for rcb in rcbs:
                    active_mark = " 🟢" if rcb.get("rpt_ena") else ""
                    report_items.append(f"{rcb['ref']} ({rcb['rcb_type']}){active_mark}")
                if rcbs or client_connected:
                    log.info(f"Reports: 返回 {len(rcbs)} 个 RCB")
                else:
                    log.debug("IEC61850 客户端未连接，Reports 使用空缓存")
                if client_connected and not rcbs:
                    log.info("远端 IED 未配置报告控制块 (BRCB/URCB)，需在 ICD 中声明 ReportControl")
            elif isinstance(protocol_handler, IEC61850ServerHandler):
                # 服务端模式：从 ReportManager 获取已注册的 RCB
                server = getattr(protocol_handler, "_server", None)
                if server and hasattr(server, "reports") and server.reports:
                    rcbs = server.reports.browse_rcbs()
                    for rcb in rcbs:
                        ln_name = rcb.get("ln_name", "LLN0")
                        report_items.append(f"{rcb.get('ld_inst', '')}/{ln_name}.{rcb['name']} ({rcb['rcb_type']})")
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
                # 客户端文件目录是实时 MMS 操作。设备关闭时只返回空列表，
                # 不调用 FilesPlugin，避免产生“连接不可用”的误导性告警。
                if client_connected:
                    iec61850_client = getattr(protocol_handler, "_client", None)
                else:
                    log.debug("IEC61850 客户端未连接，跳过远端文件目录浏览")
            elif isinstance(protocol_handler, IEC61850ServerHandler):
                iec61850_client = getattr(protocol_handler, "_server", None)

            if iec61850_client and iec61850_client.files:
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
        "GOOSE": goose_items,
        "Reports": report_items,
        "SettingGroups": [],
        "Files": file_items,
        "DataSets": dataset_items,
        "DataModel": data_model,
    }
    return BaseResponse(message="获取 IEC61850 结构成功", data=structure)


@router.post("/iec61850-table-data", response_model=BaseResponse)
async def get_iec61850_table_data(
    body: Iec61850TableDataRequest,
    request: Request,
):
    """根据 IEC61850 左侧树形节点获取当前表格数据"""
    device = _get_iec61850_device(request, body.channel_id)

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
            slave_id=slave_id,
            name=body.point_name,
            page_index=None,
            page_size=None,
            point_types=pt_filter,
        )
        all_table_rows.extend(table_data)

    filtered_rows = _filter_iec61850_rows(all_table_rows, body.category, body.item)
    total_count = len(filtered_rows)

    start = (body.page_index - 1) * body.page_size
    end = start + body.page_size
    paged_rows = filtered_rows[start:end]

    data_dict = {
        "total": total_count,
        "head_data": head_data,
        "table_data": paged_rows,
        "category": body.category,
        "item": body.item,
    }
    return BaseResponse(message="获取 IEC61850 表格数据成功", data=data_dict)


@router.post("/iec61850-read-points", response_model=BaseResponse)
async def iec61850_read_points(
    body: Iec61850ReadPointsRequest,
    request: Request,
):
    """根据 IEC61850 左侧树形节点过滤，批量读取对应测点的值"""
    device = _get_iec61850_device(request, body.channel_id)

    if device.is_auto_read_running():
        raise ConflictError("自动读取运行中，请先停止后再执行手动读取", data=device.get_auto_read_status())

    if body.category == "DataSets":
        if not body.item:
            raise ValidationError("DataSet 读取必须指定 item")
        snapshot = await device.read_dataset_once(body.item)
        values = snapshot.get("values") or {}
        return BaseResponse(
            message="IEC61850 DataSet 读取完成",
            data={"success": len(values), "fail": 0, "snapshot": snapshot},
        )

    filtered_points = _get_iec61850_filtered_points(device, body.category, body.item)
    if not filtered_points:
        return BaseResponse(message="无匹配测点", data={"success": 0, "fail": 0})

    from src.device.protocol.iec61850_handler import IEC61850ClientHandler
    from src.enums.point_data import Yc, Yx
    from src.enums.points.change_tracker import ChangeSource, track_change

    yc_list = [p for p in filtered_points if isinstance(p, Yc)]
    yx_list = [p for p in filtered_points if isinstance(p, Yx)]

    # 判断是否为 IEC61850 客户端且支持批量读取
    protocol_handler = device.protocol_handler
    is_iec61850_client = isinstance(protocol_handler, IEC61850ClientHandler)
    has_batch = is_iec61850_client

    all_points = yc_list + yx_list
    success_count = 0
    fail_count = 0

    source = ChangeSource.CLIENT_READ if has_batch else ChangeSource.INTERNAL

    if has_batch:
        # 原生 MMS 调用是同步阻塞操作。放入工作线程后，事件循环才能同时
        # 响应前端的进度轮询；Handler 会按完成的 DataSet 更新进度快照。
        batch_results = await asyncio.to_thread(
            protocol_handler.read_points_batch,
            all_points,
            track_progress=True,
        )

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
                if body.interval_ms > 0:
                    await asyncio.sleep(body.interval_ms / 1000.0)

                value = await protocol_handler.read_value_async(point)

                if value is not None:
                    from src.device.protocol.base_handler import ClientHandler

                    source = (
                        ChangeSource.CLIENT_READ
                        if isinstance(protocol_handler, ClientHandler)
                        else ChangeSource.INTERNAL
                    )
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


def _build_iec61850_dataset_tree(device, dataset_ref: str) -> dict[str, Any]:
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
        "mag": "mag.f",
        "instMag": "instMag.f",
        "cVal": "cVal.mag.f",
        "mxVal": "mxVal.f",
        "fCVal": "fCVal.mag.f",
        "wVal": "wVal.f",
        "setMag": "setMag.f",
        "Oper": "Oper.ctlVal",
        "SBOw": "SBOw.ctlVal",
        "Cancel": "Cancel.ctlVal",
        "origin": "origin.orCat",
    }

    protocol_handler = getattr(device, "protocol_handler", None)
    if not protocol_handler:
        return {"items": [], "total": 0}

    # 获取 IEC61850 handler (客户端或服务端)
    from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler

    is_client = isinstance(protocol_handler, IEC61850ClientHandler)
    is_server = isinstance(protocol_handler, IEC61850ServerHandler)
    if not is_client and not is_server:
        return {"items": [], "total": 0}

    # 从 handler 获取已发现的 DataSet 列表
    discovered_datasets = protocol_handler.get_discovered_datasets()

    matched_ds = None
    for ds in discovered_datasets:
        if _normalize_dataset_ref(ds.get("ref", "")) == _normalize_dataset_ref(dataset_ref):
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

    # DataSet 表格查询只读取显式读取/后台任务留下的缓存快照。
    resolved_ref = matched_ds.get("ref") or dataset_ref
    snapshot = device.get_dataset_snapshot(resolved_ref)
    values = snapshot.get("values") or {}
    read_time = snapshot.get("updated_at") or ""

    # 按 DO 分组构建树
    do_map: dict[str, dict[str, Any]] = {}
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
                path_part = remaining[dot_idx + 1 :]
                first_dot = path_part.find(".")
                if first_dot >= 0:
                    do_name = path_part[:first_dot]
                    da_path = path_part[first_dot + 1 :]
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

    # 保持 ICD 文件中的 FCDA 原始顺序，不自作主张排序
    items = list(do_map.values())
    return {
        "items": items,
        "total": len(items),
        "last_updated_at": snapshot.get("updated_at"),
        "stale": snapshot.get("stale", True),
        "last_error": snapshot.get("last_error"),
    }


def _get_iec61850_filtered_points(device, category: str, item: str) -> list[BasePoint]:
    """根据 IEC61850 树节点的 category 和 item 获取过滤后的测点对象列表"""

    # DataSets 分类: 返回空(数据集不包含内部测点)
    if category and category == "DataSets":
        return []

    # GOOSE/Reports 等非 DataModel 分类没有 MMS 测点
    if category and category != "DataModel":
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

    if category == "DataModel" and item:
        result = []
        for point in all_points:
            address = str(point.address)
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
    device = _get_iec61850_device(request, body.channel_id)

    do_items = []
    protocol_handler = getattr(device, "protocol_handler", None)
    if protocol_handler:
        from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler

        if isinstance(protocol_handler, IEC61850ClientHandler) and protocol_handler._client:
            client = protocol_handler._client
            if hasattr(client, "browse_data_objects"):
                do_items = client.browse_data_objects(body.ld, body.ln)
        elif isinstance(protocol_handler, IEC61850ServerHandler) and protocol_handler._server:
            server = protocol_handler._server
            if hasattr(server, "browse_data_objects"):
                do_items = server.browse_data_objects(body.ld, body.ln)

    return BaseResponse(message="获取 DO 列表成功", data={"items": do_items})


@router.post("/iec61850-da-children", response_model=BaseResponse)
async def get_iec61850_da_children(
    body: Iec61850DaChildrenRequest,
    request: Request,
):
    """获取 IEC61850 指定 DO 下的数据属性 (DA) 列表"""
    device = _get_iec61850_device(request, body.channel_id)

    da_items = []
    protocol_handler = getattr(device, "protocol_handler", None)
    if protocol_handler:
        from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler

        if isinstance(protocol_handler, IEC61850ClientHandler) and protocol_handler._client:
            client = protocol_handler._client
            if hasattr(client, "browse_data_attributes"):
                da_items = client.browse_data_attributes(body.ld, body.ln, body.do_name)
        elif isinstance(protocol_handler, IEC61850ServerHandler) and protocol_handler._server:
            server = protocol_handler._server
            if hasattr(server, "browse_data_attributes"):
                da_items = server.browse_data_attributes(body.ld, body.ln, body.do_name)

    return BaseResponse(message="获取 DA 列表成功", data={"items": da_items})


def _filter_iec61850_rows(rows: list[str], category: str, item: str) -> list[str]:
    """根据 IEC61850 树节点的 category 和 item 过滤表格行"""
    if not category:
        return rows

    if category and category != "DataModel":
        return []

    if category == "DataModel" and item:
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
    device = _get_iec61850_device(request, body.channel_id)

    if not body.point_code:
        raise ValidationError("测点编码不能为空")

    point = device.point_manager.get_point_by_code(body.point_code)
    point_fc = getattr(point, "fc", "") if point is not None else body.fc
    if point_fc == "CO":
        raise ValidationError("控制测点不支持读取", data={"point_code": body.point_code})

    protocol_handler = getattr(device, "protocol_handler", None)
    client = getattr(protocol_handler, "_client", None) if protocol_handler else None
    model_attribute = None
    if point is None and client is not None:
        model = getattr(client, "model", None)
        if model is not None:
            for ld in model.lds:
                for ln in ld.lns:
                    for do in ln.dos:
                        for da in do.das:
                            if not da.sub_das and f"{do.ref}.{da.path}" == body.point_code:
                                model_attribute = da
                                break
                            model_attribute = next(
                                (bda for bda in da.sub_das if f"{do.ref}.{bda.path}" == body.point_code),
                                None,
                            )
                            if model_attribute is not None:
                                break
                        if model_attribute is not None:
                            break
                    if model_attribute is not None:
                        break
                if model_attribute is not None:
                    break

    if point is not None:
        value = await device.read_single_point_async(body.point_code)
    elif model_attribute is not None and client is not None:
        direct_fc = body.fc or model_attribute.fc
        if direct_fc == "CO":
            raise ValidationError("控制属性不支持直接读取", data={"point_code": body.point_code})
        direct_mms_type = body.mms_type or model_attribute.mms_type
        value = await asyncio.to_thread(client.read_point, body.point_code, direct_fc, direct_mms_type)
    else:
        raise ValidationError("模型中不存在可读取的数据属性", data={"point_code": body.point_code})

    if value is None:
        log.warning(
            f"IEC61850 属性读取失败: ref={body.point_code}, fc={point_fc or body.fc}, "
            f"mms_type={body.mms_type or getattr(model_attribute, 'mms_type', '')}"
        )
        raise ValidationError("读取失败，请检查连接状态", data={"value": None, "point_code": body.point_code})
    mms_type = body.mms_type or getattr(model_attribute, "mms_type", "") or "MMS_UNKNOWN"
    registry = getattr(client, "_registry", None) if client else None
    if registry is not None and point is not None:
        mms_type = registry.get_mms_type(str(point.address)) or mms_type
    return BaseResponse(
        message="读取成功",
        data={"value": value, "point_code": body.point_code, "mms_type": mms_type},
    )


@router.post("/iec61850-read-metadata", response_model=BaseResponse)
async def iec61850_read_metadata(
    body: Iec61850ReadMetadataRequest,
    request: Request,
):
    """IEC61850 按需读取测点的品质(q)与时标(t)元数据

    不纳入常规轮询，仅当前端请求时调用。返回 quality + timestamp 子属性字典。
    """
    device = _get_iec61850_device(request, body.channel_id)

    if not body.point_code:
        raise ValidationError("测点编码不能为空")

    # 直接传 point_code，客户端内部 parse_ref 提取 DO 引用
    handler = device.point_operator._handler
    client = getattr(handler, "_client", None) if handler else None
    if not client or not hasattr(client, "read_metadata"):
        raise ValidationError("设备不支持元数据读取")

    meta = client.read_metadata(body.point_code)

    from src.proto.iec61850.defs.address import parse_ref

    parsed = parse_ref(body.point_code)
    do_ref = f"{parsed[0]}/{parsed[1]}.{parsed[2]}" if parsed else body.point_code

    return BaseResponse(
        message="读取元数据成功",
        data={
            "point_code": do_ref,
            **meta.to_dict(),
        },
    )


@router.post("/iec61850-write-point", response_model=BaseResponse)
async def iec61850_write_single_point(
    body: Iec61850WritePointRequest,
    request: Request,
):
    """IEC61850 单点写入 - 通过 channel_id 定位设备，写入指定测点的值"""
    device = _get_iec61850_device(request, body.channel_id)

    if not body.point_code:
        raise ValidationError("测点编码不能为空")

    write_point_code = _resolve_control_write_code(device, body.point_code)
    if not write_point_code:
        raise ValidationError(
            "未发现可写属性（控制对象应包含 Oper.ctlVal、SBOw.ctlVal 或 ctlVal）",
            data={"point_code": body.point_code},
        )
    success = await device.edit_point_data_async(write_point_code, body.point_value)
    if not success:
        raise ValidationError("写入失败", data={"point_code": write_point_code})
    return BaseResponse(message="写入成功", data={"point_code": write_point_code, "value": body.point_value})


@router.post("/iec61850-dataset-detail", response_model=BaseResponse)
async def get_iec61850_dataset_detail(
    body: Iec61850DatasetDetailRequest,
    request: Request,
):
    """获取 IEC61850 DataSet 的详细信息（成员列表及当前值）"""
    device = _get_iec61850_device(request, body.channel_id)

    from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler

    protocol_handler = getattr(device, "protocol_handler", None)
    is_iec61850 = isinstance(protocol_handler, (IEC61850ClientHandler, IEC61850ServerHandler))
    if not is_iec61850:
        raise ValidationError("仅 IEC61850 协议支持 DataSet 操作")

    # 详情查询必须是纯缓存查询，不再实时浏览或读取远端设备。
    matched_ds = None
    for ds in protocol_handler.get_discovered_datasets():
        if _normalize_dataset_ref(ds.get("ref", "")) == _normalize_dataset_ref(body.dataset_ref):
            matched_ds = ds
            break

    if not matched_ds:
        raise NotFoundError("DataSet 未找到，请先连接设备获取结构")

    resolved_ref = matched_ds.get("ref") or body.dataset_ref
    snapshot = device.get_dataset_snapshot(resolved_ref)
    values = snapshot.get("values") or {}

    # 复制成员，避免查询接口污染 Handler 的发现缓存。
    members = [dict(member) for member in matched_ds.get("members", [])]
    for member in members:
        ref = member.get("ref", "")
        member["value"] = values.get(ref, None)

    return BaseResponse(
        message="获取 DataSet 详情成功",
        data={
            "ref": _normalize_dataset_ref(matched_ds.get("ref", "")),
            "name": matched_ds.get("name", ""),
            "ld": matched_ds.get("ld", ""),
            "member_count": len(members),
            "members": members,
            "last_updated_at": snapshot.get("updated_at"),
            "stale": snapshot.get("stale", True),
            "last_error": snapshot.get("last_error"),
        },
    )
