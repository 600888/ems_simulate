"""SclServerModelBuilder — SclDocument → IedModel 转换器

将离线 SCL 文档 (ICD/SCD/CID) 转换为在线 IedModel，
用于从 ICD 文件构建服务器端 IedModel。

映射关系:
  SclDocument.IEDs                → IedModel
  SclLDevice                      → LDModel
  SclLN (ln_name/ln_class/ref)    → LNModel
  SclDO + SclDOType + SclDA       → DORef + DARef
  SclDataSet + SclFCDA            → DataSetRef
  SclReportControl                → RCBRef
  SclGSEControl                   → GoCBRef
"""

from __future__ import annotations

from ....defs.mms_types import BTYPE_TO_MMS_TYPE, MmsType
from ....model.ied_model import (
    DARef,
    DataSetRef,
    DORef,
    GoCBRef,
    IedModel,
    LDModel,
    LNModel,
    RCBRef,
)
from ..model.enums import (
    BTYPE_TO_IEC_TYPE,
    CDC_CATEGORY_MAP,
)
from ..model.scl_document import (
    SclDA,
    SclDocument,
    SclDOType,
    SclLDevice,
    SclLN,
)


class SclServerModelBuilder:
    """SCL 文件 → IedModel 构建器

    从离线 SCL 文档构建在线 IedModel，简化: 不做深度 BDA 展开，
    仅映射主 DA 路径和 DataSet/控制块引用。

    Args:
        doc: 已解析的 SclDocument
    """

    def __init__(self, doc: SclDocument):
        self._doc = doc

    def build(self, host: str = "", port: int = 102) -> IedModel:
        """构建 IedModel

        Args:
            host: IED 主机地址
            port: 端口号

        Returns:
            不可变 IedModel 对象
        """
        import time

        lds = []
        for ld in self._doc.get_all_ldevices():
            ln_model = self._build_ld(ld)
            if ln_model is not None:
                lds.append(ln_model)

        return IedModel(
            host=host,
            port=port,
            discover_time=time.strftime("%Y-%m-%d %H:%M:%S"),
            lds=tuple(lds),
        )

    def _build_ld(self, ld: SclLDevice) -> LDModel | None:
        """构建 LDModel"""
        lns = []
        all_lns = ([ld.ln0] + ld.lns) if ld.ln0 else ld.lns
        for ln in all_lns:
            ln_model = self._build_ln(ln, ld)
            if ln_model is not None:
                lns.append(ln_model)

        if not lns:
            return None

        return LDModel(
            name=ld.inst,
            inst=ld.inst,
            lns=tuple(lns),
        )

    def _build_ln(self, ln: SclLN, ld: SclLDevice) -> LNModel | None:
        """构建 LNModel"""
        if not ln.ln_type:
            # 没有 lnType 引用的 LN 仍包含控制块等信息
            ln_type_ref = self._doc.get_ln_node_type(ln.ln_type) if ln.ln_type else None
        else:
            ln_type_ref = self._doc.get_ln_node_type(ln.ln_type)

        # DO
        dos = []
        if ln_type_ref:
            for do_def in ln_type_ref.dos:
                do_type = self._doc.get_do_type(do_def.type_id)
                if do_type is None:
                    continue
                do_ref = f"{ld.inst}/{ln.ln_name}.{do_def.name}"
                do_model = self._build_do(do_def.name, do_ref, do_type)
                if do_model is not None:
                    dos.append(do_model)

        # DataSet
        datasets = tuple(self._build_dataset(ds, ld.inst, ln.ln_name) for ds in ln.datasets)

        # RCB
        rcb_list = tuple(self._build_rcb(rc, ld.inst, ln.ln_name) for rc in ln.report_controls)

        # GoCB
        gocb_list = tuple(self._build_gocb(gc, ld.inst, ln.ln_name) for gc in ln.gse_controls)

        return LNModel(
            name=ln.ln_name,
            ln_class=ln.ln_class,
            ref=f"{ld.inst}/{ln.ln_name}",
            dos=tuple(dos),
            datasets=datasets,
            rcb_list=rcb_list,
            gocb_list=gocb_list,
        )

    def _build_do(self, do_name: str, do_ref: str, do_type: SclDOType) -> DORef | None:
        """构建 DORef"""
        cdc = do_type.cdc
        if not cdc:
            return None

        # 确定 frame_type
        category = CDC_CATEGORY_MAP.get(cdc)
        frame_type = category.value if category is not None else -1

        # 构建 DA 列表
        das = []
        for da_def in do_type.das:
            da_model = self._build_da(da_def)
            if da_model is not None:
                das.append(da_model)

        return DORef(
            name=do_name,
            ref=do_ref,
            cdc=cdc,
            frame_type=frame_type,
            das=tuple(das),
        )

    def _build_da(self, da_def: SclDA) -> DARef | None:
        """构建 DARef"""
        if not da_def.name:
            return None

        # 解析 iec_type
        btype = da_def.b_type
        iec_type = BTYPE_TO_IEC_TYPE.get(btype, "unknown")

        # 结构体 DA: 展开 BDA 为 sub_das
        sub_das = ()
        if btype == "Struct" and da_def.type_id:
            da_type = self._doc.get_da_type(da_def.type_id)
            if da_type:
                sub_das_list = []
                for bda_def in da_type.bdas:
                    bda_type_name = BTYPE_TO_IEC_TYPE.get(bda_def.b_type, "unknown")
                    sub_bda = ()
                    # 嵌套 Struct BDA 不展开 (保持叶子路径)
                    bda_fc = bda_def.fc or da_def.fc
                    sub_das_list.append(
                        DARef(
                            name=f"{da_def.name}.{bda_def.name}",
                            path=f"{da_def.name}.{bda_def.name}",
                            fc=bda_fc,
                            iec_type=bda_type_name,
                            mms_type=BTYPE_TO_MMS_TYPE.get(bda_def.b_type, MmsType.UNKNOWN).value,
                            sub_das=sub_bda,
                        )
                    )
                sub_das = tuple(sub_das_list)

        return DARef(
            name=da_def.name,
            path=da_def.name,
            fc=da_def.fc,
            iec_type=iec_type,
            mms_type=BTYPE_TO_MMS_TYPE.get(btype, MmsType.UNKNOWN).value,
            sub_das=sub_das,
        )

    @staticmethod
    def _build_dataset(ds, ld_inst: str, ln_name: str) -> DataSetRef:
        """构建 DataSetRef"""
        ds_ref = f"{ld_inst}/{ln_name}${ds.name}"
        members = tuple(
            {
                "ld_inst": m.ld_inst or ld_inst,
                "ln_class": m.ln_class,
                "ln_inst": m.ln_inst,
                "ln_prefix": m.ln_prefix,
                "do_name": m.do_name,
                "da_name": m.da_name,
                "fc": m.fc,
                "fcda_ref": m.fcda_ref,
            }
            for m in ds.members
        )
        return DataSetRef(
            name=ds.name,
            ref=ds_ref,
            is_deletable=False,
            members=members,
        )

    @staticmethod
    def _build_rcb(rc, ld_inst: str, ln_name: str) -> RCBRef:
        """构建 RCBRef"""
        rcb_type = "BRCB" if rc.buffered else "URCB"
        return RCBRef(
            name=rc.name,
            ref=f"{ld_inst}/{ln_name}.{rc.name}",
            rcb_type=rcb_type,
            dat_set=rc.dat_set,
            intg_pd=rc.intg_period,
        )

    @staticmethod
    def _build_gocb(gc, ld_inst: str, ln_name: str) -> GoCBRef:
        """构建 GoCBRef"""
        go_cb_ref = f"{ld_inst}/{ln_name}$GO${gc.name}"
        return GoCBRef(
            name=gc.name,
            ref=f"{ld_inst}/{ln_name}.{gc.name}",
            go_cb_ref=go_cb_ref,
            go_id=gc.name,
            app_id=int(gc.app_id, 16) if gc.app_id and gc.app_id.startswith("0x") else None,
            data_set_ref=f"{ld_inst}/{ln_name}${gc.dat_set}" if gc.dat_set else "",
            conf_rev=gc.conf_rev,
        )
