"""类型引用解析器

解析 DataTypeTemplates 中的类型引用链:
  LN.lnType → LNodeType → DO.type → DOType → DA.type → DAType → BDA.type → ...

优化:
- get_value_da_path / collect_all_das 添加结果缓存，
  避免同一 DOType 被重复递归解析。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..model.enums import CDC_CONTROL_DA_PATH, CDC_VALUE_DA_PATH, STRUCT_DA_TO_FULL_PATH
from ..model.scl_document import (
    SclDA,
    SclDOType,
)

if TYPE_CHECKING:
    from ..model.scl_document import SclDocument, SclDOI


class TypeResolver:
    """类型引用解析器

    从 SclDocument 的 DataTypeTemplates 解析 DO/DA 引用链，
    获取完整的测点路径 (如 "mag.f", "Oper.ctlVal")。

    缓存: get_value_da_path 和 collect_all_das 的结果按 (do_type_id, cdc)
    缓存，同一 DOType 被多个 DO 引用时避免重复递归。
    """

    def __init__(self, doc: SclDocument):
        self._dtt = doc.data_type_templates
        self._doc = doc
        # 结果缓存: key=(do_type_id, cdc) → result
        self._da_path_cache: dict[tuple[str, str], str | None] = {}
        self._all_das_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        # get_do_desc 缓存: key=do_name → desc（同一 do_name 在所有 LN 中描述相同）
        self._do_desc_cache: dict[str, str] = {}

    def get_value_da_path(self, do_type_id: str, cdc: str) -> str | None:
        """获取 DO 的主值 DA 路径（带缓存）

        优先级:
        1. 控制 CDC: 从 DOType 查找 Oper/ctlVal
        2. 测量/状态 CDC: 从 DOType 递归查找
        3. 使用 CDC 默认路径
        """
        key = (do_type_id, cdc)
        if key in self._da_path_cache:
            return self._da_path_cache[key]
        result = self._get_value_da_path_impl(do_type_id, cdc)
        self._da_path_cache[key] = result
        return result

    def _get_value_da_path_impl(self, do_type_id: str, cdc: str) -> str | None:
        """get_value_da_path 的实现体"""
        do_type = self._dtt.do_types.get(do_type_id)
        if do_type is None:
            return CDC_VALUE_DA_PATH.get(cdc)

        # 控制 CDC: 优先查找 SDO (Oper/SBOw)
        if cdc in CDC_CONTROL_DA_PATH:
            for sdo in do_type.sdos:
                if sdo.name in ("Oper", "SBOw"):
                    return f"{sdo.name}.ctlVal"
            # 查找 ctlVal DA
            for da in do_type.das:
                if da.name == "ctlVal":
                    return "ctlVal"
            # 查找 setVal DA
            for da in do_type.das:
                if da.name == "setVal":
                    return "setVal"

        # 测量/状态 CDC: 递归查找
        if cdc in ("MV", "CMV", "SAV"):
            path = self._find_measurement_path(do_type, cdc)
            if path:
                return path

        # WYE/DEL 等复合 CDC: 取第一个 SDO
        if cdc in ("WYE", "DEL", "SEQ", "HMV"):
            for sdo in do_type.sdos:
                sub_type = self._dtt.do_types.get(sdo.type_id)
                if sub_type and sub_type.cdc == "MV":
                    return f"{sdo.name}.mag.f"

        # 默认
        return CDC_VALUE_DA_PATH.get(cdc)

    def _find_measurement_path(self, do_type: SclDOType, cdc: str) -> str | None:
        """递归查找测量值 DA 路径"""
        # 查找 DA
        for da in do_type.das:
            if da.name in ("mag", "instMag", "cVal", "mxVal", "fCVal"):
                return STRUCT_DA_TO_FULL_PATH.get(da.name, da.name)
            if da.name == "stVal":
                return "stVal"
            if da.name == "actVal":
                return "actVal"

        # 查找 SDO (如 MV 类型的 mag SDO)
        for sdo in do_type.sdos:
            sub_type = self._dtt.do_types.get(sdo.type_id)
            if sub_type:
                path = self._find_measurement_path(sub_type, cdc)
                if path:
                    return f"{sdo.name}.{path}"

        return None

    def collect_all_das(self, do_type_id: str, cdc: str) -> list[dict[str, Any]]:
        """收集 DOType 下所有 DA（带缓存）

        Returns:
            DA 信息列表: [{"name": ..., "path": ..., "fc": ..., "bType": ...}]
        """
        key = (do_type_id, cdc)
        if key in self._all_das_cache:
            # 返回副本以防外部修改缓存
            return list(self._all_das_cache[key])

        do_type = self._dtt.do_types.get(do_type_id)
        if do_type is None:
            result: list[dict[str, str]] = []
            self._all_das_cache[key] = result
            return result

        result = self._collect_all_das_impl(do_type)
        self._all_das_cache[key] = result
        return list(result)

    def _collect_all_das_impl(self, do_type: SclDOType) -> list[dict[str, Any]]:
        """collect_all_das 的实现体"""
        result: list[dict[str, Any]] = []
        for da in do_type.das:
            self._collect_da(da, result, da.name)

        # SDO
        for sdo in do_type.sdos:
            sub_type = self._dtt.do_types.get(sdo.type_id)
            if sub_type:
                for da in sub_type.das:
                    self._collect_da(
                        da,
                        result,
                        f"{sdo.name}.{da.name}",
                        fc_override="CO" if sdo.name in ("Oper", "SBOw", "Cancel") else None,
                    )

        return result

    def _collect_da(
        self,
        da: SclDA,
        result: list[dict[str, Any]],
        path_prefix: str,
        fc_override: str | None = None,
    ) -> None:
        """收集单个 DA 信息"""
        mapped_name = STRUCT_DA_TO_FULL_PATH.get(da.name, da.name)
        if "." in path_prefix:
            parent_path = path_prefix.rsplit(".", 1)[0]
            da_path = f"{parent_path}.{mapped_name}"
        else:
            da_path = mapped_name
        fc = fc_override or da.fc

        result.append(
            {
                "name": da.name,
                "path": da_path,
                "fc": fc,
                "bType": da.b_type,
                "dchg": da.dchg,
                "qchg": da.qchg,
                "dupd": da.dupd,
            }
        )

        # 展开 Struct DA
        if da.b_type == "Struct" and da.type_id:
            da_type = self._dtt.da_types.get(da.type_id)
            if da_type:
                for bda in da_type.bdas:
                    if bda.b_type == "Struct":
                        continue  # 跳过嵌套 Struct
                    result.append(
                        {
                            "name": bda.name,
                            "path": f"{path_prefix}.{bda.name}",
                            "fc": fc,
                            "bType": bda.b_type,
                            # BDA 沿用其所属 DA 的触发语义；libIEC61850 的动态
                            # 模型最终更新的是叶子属性，因此触发位也必须落到叶子上。
                            "dchg": da.dchg,
                            "qchg": da.qchg,
                            "dupd": da.dupd,
                        }
                    )

    def get_do_desc(
        self,
        do_name: str,
        do_type: SclDOType,
        doi: SclDOI | None = None,
    ) -> str:
        """获取 DO 描述（带缓存）

        优先级: DOI/DAI 中 dU 的 Val → DOType desc → du DA 的 Val → DO 名称

        缓存 key 为 do_name，因为同一 do_name 在不同 LN 中的描述一致。
        """
        if do_name in self._do_desc_cache:
            return self._do_desc_cache[do_name]
        result = self._get_do_desc_impl(do_name, do_type, doi)
        self._do_desc_cache[do_name] = result
        return result

    def _get_do_desc_impl(
        self,
        do_name: str,
        do_type: SclDOType,
        doi: SclDOI | None = None,
    ) -> str:
        # 最高优先级: DOI/DAI 中 dU 的 Val
        if doi:
            du_val = doi.dai_values.get("du") or doi.dai_values.get("dU")
            if du_val:
                return du_val

        # DOType desc
        if do_type.desc:
            return do_type.desc

        # du DA 的 Val
        for da in do_type.das:
            if da.name in ("dU", "du"):
                if da.val:
                    return da.val
                if da.desc:
                    return da.desc

        return do_name
