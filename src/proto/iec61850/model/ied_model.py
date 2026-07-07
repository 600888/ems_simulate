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
    mms_type: str = "MMS_UNKNOWN"
    sub_das: tuple[DARef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "path": self.path,
            "fc": self.fc,
            "iecType": self.iec_type,
            "mmsType": self.mms_type,
        }
        if self.sub_das:
            result["subDataAttributes"] = [bda.to_dict() for bda in self.sub_das]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DARef:
        sub_das = tuple(cls.from_dict(sd) for sd in data.get("subDataAttributes", []))
        return cls(
            name=data.get("name", ""),
            path=data.get("path", ""),
            fc=data.get("fc", ""),
            iec_type=data.get("iecType", ""),
            mms_type=data.get("mmsType", "MMS_UNKNOWN"),
            sub_das=sub_das,
        )

    def to_flat_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "fc": self.fc,
            "iecType": self.iec_type,
            "mmsType": self.mms_type,
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DORef:
        das = tuple(DARef.from_dict(da) for da in data.get("dataAttributes", []))
        return cls(
            name=data.get("name", ""),
            ref=data.get("ref", ""),
            cdc=data.get("cdc", ""),
            frame_type=data.get("frameType", -1),
            das=das,
        )

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
                target_path = DA_PATTERNS[self.cdc][0]
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataSetRef:
        members = tuple(dict(m) if isinstance(m, dict) else {"name": m} for m in data.get("members", []))
        return cls(
            name=data.get("name", ""),
            ref=data.get("ref", ""),
            is_deletable=data.get("isDeletable", False),
            members=members,
        )


@dataclass(slots=True, frozen=True)
class RCBRef:
    """报告控制块引用"""

    name: str = ""
    ref: str = ""
    rcb_type: str = ""  # "URCB" / "BRCB"
    dat_set: str = ""  # 引用的 DataSet 名称
    intg_pd: int = 0  # 完整性周期(毫秒), URCB 专用
    # TrgOps 位图: bit0=dchg(0x01), bit1=qchg(0x02), bit2=dupd(0x04),
    #              bit3=period(0x08), bit4=gi(0x10)
    # 默认值 0x11 = dchg=True, gi=True
    trg_ops: int = 0x11
    # OptFields 位图: bit0=seq_num(0x01), bit1=time_stamp(0x02), bit2=reason_code(0x04),
    #                 bit3=data_set(0x08), bit4=data_ref(0x10), bit5=buf_ovfl(0x20),
    #                 bit6=entry_id(0x40), bit7=config_ref(0x80)
    # 默认值 0x4F = seq_num, time_stamp, reason_code, data_set, entry_id
    opt_fields: int = 0x4F

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name, "ref": self.ref, "type": self.rcb_type}
        if self.dat_set:
            result["datSet"] = self.dat_set
        if self.intg_pd:
            result["intgPd"] = self.intg_pd
        # 始终序列化位图，确保缓存加载时能恢复
        result["trgOps"] = self.trg_ops
        result["optFields"] = self.opt_fields
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RCBRef:
        return cls(
            name=data.get("name", ""),
            ref=data.get("ref", ""),
            rcb_type=data.get("type", ""),
            dat_set=data.get("datSet", ""),
            intg_pd=data.get("intgPd", 0),
            trg_ops=data.get("trgOps", 0x11),
            opt_fields=data.get("optFields", 0x4F),
        )


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoCBRef:
        return cls(
            name=data.get("name", ""),
            ref=data.get("ref", ""),
            go_cb_ref=data.get("go_cb_ref", ""),
            go_id=data.get("go_id", ""),
            app_id=data.get("app_id"),
            data_set_ref=data.get("data_set_ref", ""),
            conf_rev=data.get("conf_rev", 0),
        )


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LNModel:
        dos = tuple(DORef.from_dict(do) for do in data.get("dataObjects", []))
        datasets = tuple(DataSetRef.from_dict(ds) for ds in data.get("dataSets", []))
        rcb_list = tuple(RCBRef.from_dict(rcb) for rcb in data.get("reportControlBlocks", []))
        gocb_list = tuple(GoCBRef.from_dict(gocb) for gocb in data.get("gooseControlBlocks", []))
        return cls(
            name=data.get("name", ""),
            ln_class=data.get("lnClass", ""),
            ref=data.get("ref", ""),
            dos=dos,
            datasets=datasets,
            rcb_list=rcb_list,
            gocb_list=gocb_list,
        )


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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LDModel:
        lns = tuple(LNModel.from_dict(ln) for ln in data.get("logicalNodes", []))
        return cls(
            name=data.get("name", ""),
            inst=data.get("inst", ""),
            lns=lns,
        )


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
        result = {
            "host": self.host,
            "port": self.port,
            "discover_time": self.discover_time,
            "logicalDevices": [ld.to_dict() for ld in self.lds],
            "summary": self.summary,
        }
        # 序列化预计算的扁平测点映射，避免从文件恢复时懒加载重新计算
        if self._point_refs:
            result["_point_refs"] = self._point_refs
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IedModel:
        lds = tuple(LDModel.from_dict(ld) for ld in data.get("logicalDevices", []))
        # 使用文件中的预计算测点映射，避免从 LD 重新计算
        point_refs = data["_point_refs"]
        return cls(
            host=data.get("host", ""),
            port=data.get("port", 102),
            discover_time=data.get("discover_time", ""),
            lds=lds,
            _point_refs=point_refs,
        )

    # ===== 统计摘要 =====

    @property
    def summary(self) -> dict[str, int]:
        return {
            "totalLDs": len(self.lds),
            "totalLNs": sum(len(ld.lns) for ld in self.lds),
            "totalDOs": sum(len(ln.dos) for ld in self.lds for ln in ld.lns),
            "totalDAs": sum(len(do.das) for ld in self.lds for ln in ld.lns for do in ln.dos),
            "totalDataSets": sum(len(ln.datasets) for ld in self.lds for ln in ld.lns),
            "totalRCBs": sum(len(ln.rcb_list) for ld in self.lds for ln in ld.lns),
            "totalGoCBs": sum(len(ln.gocb_list) for ld in self.lds for ln in ld.lns),
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
                "mms_type": "MMS_FLOAT",
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
                "mms_type": "MMS_BOOLEAN",
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
                "mms_type": "MMS_BOOLEAN",
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
                "mms_type": "MMS_FLOAT",
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
            point_mms_type = da.mms_type
            if da.sub_das:
                value_bda = next((bda for bda in da.sub_das if bda.path == da.path), da.sub_das[0])
                point_mms_type = value_bda.mms_type

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

            # 同一个 DO 可同时包含可读状态 stVal(ST) 和控制入口
            # Oper.ctlVal(CO)。测点类别必须按 DA 自身的 FC 判定，不能沿用
            # DO 从 stVal 推导出的遥信类别。
            if fc == "CO":
                frame_type = 3 if iec_type == IEC_TYPE_FLOAT else 2

            if frame_type < 0:
                continue

            ref = f"{do.ref}.{da_path}"
            address = f"{ld.name}/{ln.name}.{do.name}.{da_path}"
            code = f"{ln.name}.{do.name}.{da_path}"

            result[address] = {
                "ref": ref,
                "fc": fc,
                "iec_type": iec_type,
                "mms_type": point_mms_type,
                "frame_type": frame_type,
                "code": code,
            }

            # 展开 BDA (仅 origin.orCat/orIdent 等非元数据子属性)
            for bda in da.sub_das:
                # 控制命令结构中的 Check/Test/T/ctlNum/origin 是 operate
                # 请求的附加字段，不是可单独写入的测点。仅注册 ctlVal。
                if da.name in ("Oper", "SBOw", "Cancel") and bda.name != "ctlVal":
                    continue
                bda_path = bda.path
                bda_fc = bda.fc or fc
                bda_iec_type = bda.iec_type
                bda_frame_type = frame_type
                if bda_fc == "CO":
                    bda_frame_type = 3 if bda_iec_type == IEC_TYPE_FLOAT else 2
                bda_ref = f"{do.ref}.{bda_path}"
                bda_address = f"{ld.name}/{ln.name}.{do.name}.{bda_path}"
                bda_code = f"{ln.name}.{do.name}.{bda_path}"

                result[bda_address] = {
                    "ref": bda_ref,
                    "fc": bda_fc,
                    "iec_type": bda_iec_type,
                    "mms_type": bda.mms_type,
                    "frame_type": bda_frame_type,
                    "code": bda_code,
                }

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
