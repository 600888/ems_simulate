"""统一在线模型数据类 — 不可变值对象

所有 dataclass 使用:
- slots=True: 减少 ~40% 内存占用
- frozen=True: 发现完成后不可变，线程安全
- tuple: 子元素不可变

这些模型类不依赖 pyiec61850、FastAPI、SQLAlchemy，
仅依赖标准库和 defs/ 模块。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True, frozen=True)
class DARef:
    """数据属性引用 — 最细粒度的可寻址单元"""

    name: str = ""
    path: str = ""
    fc: str = ""
    iec_type: str = ""
    sub_das: tuple[DARef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "path": self.path,
            "fc": self.fc,
            "iecType": self.iec_type,
        }
        if self.sub_das:
            result["subDataAttributes"] = [bda.to_dict() for bda in self.sub_das]
        return result

    def to_flat_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "fc": self.fc,
            "iecType": self.iec_type,
        }

    @property
    def is_leaf(self) -> bool:
        return not self.sub_das

    def iter_leaves(self) -> Iterator[DARef]:
        if self.is_leaf:
            yield self
        else:
            for bda in self.sub_das:
                yield from bda.iter_leaves()


@dataclass(slots=True, frozen=True)
class DORef:
    """数据对象引用"""

    name: str = ""
    ref: str = ""
    cdc: str = ""
    frame_type: int = -1
    das: tuple[DARef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ref": self.ref,
            "cdc": self.cdc,
            "frameType": self.frame_type,
            "dataAttributes": [da.to_dict() for da in self.das],
        }

    @property
    def primary_da(self) -> DARef | None:
        """主值 DA — 用于读写操作的默认 DA

        按优先级查找:
        1. DA_PATTERNS 中 CDC 对应的 da_path
        2. 简单地址模式的固定 DA (mag.f / stVal / ctlVal)
        3. 第一个 DA
        """
        # 简单地址模式: DO 名带前缀
        if self.name.startswith("MV_"):
            target_path = "mag.f"
        elif self.name.startswith("SPS_"):
            target_path = "stVal"
        elif self.name.startswith("SPC_"):
            target_path = "ctlVal"
        elif self.name.startswith("APC_"):
            target_path = "ctlVal"
        else:
            # 动态模型模式: 根据 CDC 推断
            from ..defs.da_patterns import DA_PATTERNS
            if self.cdc in DA_PATTERNS:
                target_path = DA_PATTERNS[self.cdc].get("da_path", "")
            else:
                target_path = ""

        if target_path:
            for da in self.das:
                if da.path == target_path:
                    return da

        return self.das[0] if self.das else None


@dataclass(slots=True, frozen=True)
class DataSetRef:
    """数据集引用"""

    name: str = ""
    ref: str = ""
    is_deletable: bool = False
    members: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ref": self.ref,
            "isDeletable": self.is_deletable,
            "members": list(self.members),
        }


@dataclass(slots=True, frozen=True)
class RCBRef:
    """报告控制块引用"""

    name: str = ""
    ref: str = ""
    rcb_type: str = ""  # "URCB" / "BRCB"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ref": self.ref, "type": self.rcb_type}


@dataclass(slots=True, frozen=True)
class GoCBRef:
    """GOOSE 控制块引用"""

    name: str = ""
    ref: str = ""
    go_cb_ref: str = ""  # 完整 GoCB 引用 (如 "LD/LLN0$GO$gcbName")
    go_id: str = ""
    app_id: int | None = None
    data_set_ref: str = ""
    conf_rev: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ref": self.ref}


@dataclass(slots=True, frozen=True)
class LNModel:
    """逻辑节点模型"""

    name: str = ""
    ln_class: str = ""
    ref: str = ""
    dos: tuple[DORef, ...] = ()
    datasets: tuple[DataSetRef, ...] = ()
    rcb_list: tuple[RCBRef, ...] = ()
    gocb_list: tuple[GoCBRef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "lnClass": self.ln_class,
            "ref": self.ref,
        }
        if self.dos:
            result["dataObjects"] = [do.to_dict() for do in self.dos]
        if self.datasets:
            result["dataSets"] = [ds.to_dict() for ds in self.datasets]
        if self.rcb_list:
            result["reportControlBlocks"] = [rcb.to_dict() for rcb in self.rcb_list]
        if self.gocb_list:
            result["gooseControlBlocks"] = [gocb.to_dict() for gocb in self.gocb_list]
        return result


@dataclass(slots=True, frozen=True)
class LDModel:
    """逻辑设备模型"""

    name: str = ""
    inst: str = ""
    lns: tuple[LNModel, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "inst": self.inst,
            "logicalNodes": [ln.to_dict() for ln in self.lns],
        }


@dataclass(slots=True, frozen=True)
class IedModel:
    """IED 统一在线模型 — 一次发现，多处消费

    替代:
    - PointRegistry (连接时发现的扁平测点映射)
    - 旧 ModelExporter 的嵌套 dataclass 导出

    特性:
    - frozen: 发现完成后不可变，线程安全
    - slots: 减少内存占用 40-50%
    - tuple: 子元素不可变
    - cached_property: 派生属性延迟计算
    - to_dict: 自带序列化，无需外部转换函数
    """

    host: str = ""
    port: int = 102
    discover_time: str = ""
    lds: tuple[LDModel, ...] = ()

    # 预计算的扁平测点映射 — 由 Builder 或 compute_point_refs() 填充
    _point_refs: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False, compare=False)

    # ===== 序列化 =====

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "discover_time": self.discover_time,
            "logicalDevices": [ld.to_dict() for ld in self.lds],
            "summary": self.summary,
        }

    # ===== 统计摘要 =====

    @property
    def summary(self) -> dict[str, int]:
        return {
            "totalLDs": len(self.lds),
            "totalLNs": sum(len(ld.lns) for ld in self.lds),
            "totalDOs": sum(len(ln.dos) for ld in self.lds for ln in ld.lns),
            "totalDAs": sum(
                len(do.das) for ld in self.lds for ln in ld.lns for do in ln.dos
            ),
            "totalDataSets": sum(
                len(ln.datasets) for ld in self.lds for ln in ld.lns
            ),
            "totalRCBs": sum(len(ln.rcb_list) for ld in self.lds for ln in ld.lns),
            "totalGoCBs": sum(
                len(ln.gocb_list) for ld in self.lds for ln in ld.lns
            ),
        }

    # ===== 派生: PointRegistry 所需数据 =====

    @property
    def point_refs(self) -> dict[str, dict[str, Any]]:
        """生成 address → {ref, fc, iec_type, frame_type, code, name} 映射

        优先使用 Builder 在构造时预计算的 _point_refs 缓存，
        未缓存时懒加载计算（兼容直接构造的场景）。
        """
        if self._point_refs:
            return self._point_refs
        # 懒加载回退 — 仅用于未通过 Builder 构造的模型
        result = compute_point_refs(self.lds)
        object.__setattr__(self, "_point_refs", result)
        return result

    @staticmethod
    def _extract_do_points(
        ld: LDModel,
        ln: LNModel,
        do: DORef,
        result: dict[str, dict[str, Any]],
    ) -> None:
        """从 DO 提取测点到 result

        仅主值 DA (mag.f/stVal/ctlVal 等) 和 origin 子属性作为测点；
        q/t/dU/subQ/subID 等元数据 DA 全部跳过，不在 PointRegistry 中创建。
        """
        from ..defs.constants import (
            IEC_TYPE_BOOLEAN,
            IEC_TYPE_FLOAT,
        )
        from ..defs.da_patterns import DA_PATTERNS, ENC_DO_DA_TYPE_OVERRIDE, EXTRA_DA_INFO, SKIP_DA_NAMES

        # 简单地址模式: DO 名带前缀
        if do.name.startswith("MV_"):
            addr = do.name[3:]
            da_path = "mag.f"
            address = f"{ld.name}/{ln.name}.{do.name}.{da_path}"
            result[address] = {
                "ref": f"{do.ref}.{da_path}",
                "fc": "MX",
                "iec_type": IEC_TYPE_FLOAT,
                "frame_type": 0,
                "code": addr,
            }
            return
        elif do.name.startswith("SPS_"):
            addr = do.name[4:]
            da_path = "stVal"
            address = f"{ld.name}/{ln.name}.{do.name}.{da_path}"
            result[address] = {
                "ref": f"{do.ref}.{da_path}",
                "fc": "ST",
                "iec_type": IEC_TYPE_BOOLEAN,
                "frame_type": 1,
                "code": addr,
            }
            return
        elif do.name.startswith("SPC_"):
            addr = do.name[4:]
            da_path = "ctlVal"
            address = f"{ld.name}/{ln.name}.{do.name}.{da_path}"
            result[address] = {
                "ref": f"{do.ref}.{da_path}",
                "fc": "CO",
                "iec_type": IEC_TYPE_BOOLEAN,
                "frame_type": 2,
                "code": addr,
            }
            return
        elif do.name.startswith("APC_"):
            addr = do.name[4:]
            da_path = "ctlVal"
            address = f"{ld.name}/{ln.name}.{do.name}.{da_path}"
            result[address] = {
                "ref": f"{do.ref}.{da_path}",
                "fc": "CO",
                "iec_type": IEC_TYPE_FLOAT,
                "frame_type": 3,
                "code": addr,
            }
            return

        # q/t/dU/subQ/subID 等元数据 DA 不作为测点 (结构体不能直接 MMS 读取)
        NON_POINT_DA_NAMES = SKIP_DA_NAMES

        # 动态模型模式: 遍历所有 DA
        for da in do.das:
            # 跳过元数据 DA (q/t/dU/subQ/subID 等), 不展开子 DA
            if da.name in NON_POINT_DA_NAMES:
                continue

            da_path = da.path
            frame_type = do.frame_type
            fc = da.fc
            iec_type = da.iec_type

            # ENC 类型 DO 的 stVal/ctlVal 是整型而非布尔
            if do.name in ENC_DO_DA_TYPE_OVERRIDE:
                da_top = da_path.split(".")[0]
                override_type = ENC_DO_DA_TYPE_OVERRIDE[do.name].get(da_top)
                if override_type:
                    iec_type = override_type

            # 从 DA_PATTERNS / EXTRA_DA_INFO 推断 frame_type 和 iec_type
            if da.name in DA_PATTERNS:
                _, ft_from_pattern, iec_type_from_pattern = DA_PATTERNS[da.name]
                if frame_type < 0:
                    frame_type = ft_from_pattern
                if not iec_type or iec_type == "unknown":
                    iec_type = iec_type_from_pattern
            elif da.name in EXTRA_DA_INFO:
                _, fc_from_extra, iec_type_from_extra = EXTRA_DA_INFO[da.name]
                if not fc:
                    fc = fc_from_extra
                if not iec_type or iec_type == "unknown":
                    iec_type = iec_type_from_extra
                if frame_type < 0:
                    frame_type = 1

            if frame_type < 0:
                continue

            ref = f"{do.ref}.{da_path}"
            address = f"{ld.name}/{ln.name}.{do.name}.{da_path}"
            code = f"{ln.name}.{do.name}.{da_path}"

            result[address] = {
                "ref": ref,
                "fc": fc,
                "iec_type": iec_type,
                "frame_type": frame_type,
                "code": code,
            }

            # 展开 BDA (仅 origin.orCat/orIdent 等非元数据子属性)
            for bda in da.sub_das:
                bda_path = bda.path
                bda_fc = bda.fc or fc
                bda_iec_type = bda.iec_type
                bda_ref = f"{do.ref}.{bda_path}"
                bda_address = f"{ld.name}/{ln.name}.{do.name}.{bda_path}"
                bda_code = f"{ln.name}.{do.name}.{bda_path}"

                result[bda_address] = {
                    "ref": bda_ref,
                    "fc": bda_fc,
                    "iec_type": bda_iec_type,
                    "frame_type": frame_type,
                    "code": bda_code,
                }

    # ===== GOOSE 控制块信息 (兼容旧格式) =====

    @property
    def goose_items(self) -> list[dict[str, Any]]:
        """GOOSE 控制块列表 — 兼容旧 discovered_goose_items 格式"""
        items = []
        for ld in self.lds:
            for ln in ld.lns:
                for gocb in ln.gocb_list:
                    items.append({
                        "_type": "goose",
                        "go_cb_ref": gocb.go_cb_ref or gocb.ref,
                        "go_id": gocb.go_id,
                        "app_id": gocb.app_id,
                        "data_set_ref": gocb.data_set_ref,
                        "conf_rev": gocb.conf_rev,
                        "name": gocb.name,
                        "ld_inst": ld.name,
                    })
        return items

    # ===== 遍历工具 =====

    def iter_dos(self) -> Iterator[tuple[LDModel, LNModel, DORef]]:
        for ld in self.lds:
            for ln in ld.lns:
                for do in ln.dos:
                    yield ld, ln, do

    def iter_da_leaves(
        self,
    ) -> Iterator[tuple[LDModel, LNModel, DORef, DARef]]:
        for ld in self.lds:
            for ln in ld.lns:
                for do in ln.dos:
                    for da in do.das:
                        for leaf in da.iter_leaves():
                            yield ld, ln, do, leaf


# ===== 模块级便捷函数 =====


def compute_point_refs(lds: tuple[LDModel, ...]) -> dict[str, dict[str, Any]]:
    """从 LD 列表预计算扁平测点映射

    供 IedModelBuilder 在构造时一次性计算，避免 @property 重复遍历。
    """
    result: dict[str, dict[str, Any]] = {}
    for ld in lds:
        for ln in ld.lns:
            for do in ln.dos:
                IedModel._extract_do_points(ld, ln, do, result)
    return result
