"""Resolve SCL type references from DataTypeTemplates.

The resolver follows the SCL reference chain:
LN.lnType -> LNodeType -> DO.type -> DOType -> DA.type -> DAType/BDA.
It returns flattened DA paths such as ``mag.f`` and ``Oper.ctlVal``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ....defs.mms_types import mms_type_from_btype
from ..model.enums import (
    CDC_CONTROL_DA_PATH,
    CDC_VALUE_DA_PATH,
    STRUCT_DA_TO_FULL_PATH,
    iec_type_from_btype,
)
from ..model.scl_document import SclDA, SclDOType

if TYPE_CHECKING:
    from ..model.scl_document import SclDocument, SclDOI


class TypeResolver:
    """Resolve DO/DA type templates and cache repeated lookups."""

    def __init__(self, doc: SclDocument):
        """索引 SCL 类型模板，供数据属性路径、描述和叶子节点解析复用。"""
        self._dtt = doc.data_type_templates
        self._doc = doc
        self._da_path_cache: dict[tuple[str, str], str | None] = {}
        self._all_das_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        # Only type-level fallback descriptions are shared.  Instance-level
        # DOI/DAI values must never be cached by DO name: the same LNodeType is
        # commonly instantiated many times with a different dU value in every
        # LN/LD instance.
        self._do_desc_cache: dict[tuple[str, str], str] = {}

    def get_value_da_path(self, do_type_id: str, cdc: str) -> str | None:
        """获取值数据属性路径并返回结果。"""
        key = (do_type_id, cdc)
        if key in self._da_path_cache:
            return self._da_path_cache[key]
        result = self._get_value_da_path_impl(do_type_id, cdc)
        self._da_path_cache[key] = result
        return result

    def _get_value_da_path_impl(self, do_type_id: str, cdc: str) -> str | None:
        """获取值数据属性路径并返回结果。"""
        do_type = self._dtt.do_types.get(do_type_id)
        if do_type is None:
            return CDC_VALUE_DA_PATH.get(cdc)

        if cdc in CDC_CONTROL_DA_PATH:
            for sdo in do_type.sdos:
                if sdo.name in ("Oper", "SBOw"):
                    return f"{sdo.name}.ctlVal"
            for da in do_type.das:
                if da.name == "ctlVal":
                    return "ctlVal"
            for da in do_type.das:
                if da.name == "setVal":
                    return "setVal"

        if cdc in ("MV", "CMV", "SAV"):
            path = self._find_measurement_path(do_type, cdc)
            if path:
                return path

        if cdc in ("WYE", "DEL", "SEQ", "HMV"):
            for sdo in do_type.sdos:
                sub_type = self._dtt.do_types.get(sdo.type_id)
                if sub_type and sub_type.cdc == "MV":
                    return f"{sdo.name}.mag.f"

        return CDC_VALUE_DA_PATH.get(cdc)

    def _find_measurement_path(self, do_type: SclDOType, cdc: str) -> str | None:
        """查找measurement路径并返回匹配结果。"""
        for da in do_type.das:
            if da.name in ("mag", "instMag", "cVal", "mxVal", "fCVal"):
                # AnalogueValue is a Struct whose actual wire leaf can be f or
                # i.  Do not blindly apply the CDC default (for example
                # mag.f), because vendor models legitimately use mag.i.
                if str(da.b_type or "").upper() == "STRUCT" and da.type_id:
                    da_type = self._dtt.da_types.get(da.type_id)
                    if da_type:
                        leaf = next(
                            (bda for bda in da_type.bdas if str(bda.b_type or "").upper() != "STRUCT"),
                            None,
                        )
                        if leaf is not None:
                            return f"{da.name}.{leaf.name}"
                return STRUCT_DA_TO_FULL_PATH.get(da.name, da.name)
            if da.name == "stVal":
                return "stVal"
            if da.name == "actVal":
                return "actVal"

        for sdo in do_type.sdos:
            sub_type = self._dtt.do_types.get(sdo.type_id)
            if sub_type:
                path = self._find_measurement_path(sub_type, cdc)
                if path:
                    return f"{sdo.name}.{path}"

        return None

    def collect_all_das(self, do_type_id: str, cdc: str) -> list[dict[str, Any]]:
        """收集全部资源DAS并返回汇总结果。"""
        key = (do_type_id, cdc)
        if key in self._all_das_cache:
            return list(self._all_das_cache[key])

        do_type = self._dtt.do_types.get(do_type_id)
        if do_type is None:
            result: list[dict[str, Any]] = []
            self._all_das_cache[key] = result
            return result

        result = self._collect_all_das_impl(do_type)
        self._all_das_cache[key] = result
        return list(result)

    def _collect_all_das_impl(self, do_type: SclDOType) -> list[dict[str, Any]]:
        """收集全部资源DAS并返回汇总结果。"""
        result: list[dict[str, Any]] = []
        for da in do_type.das:
            self._collect_da(da, result, da.name)

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
        """收集数据属性并返回汇总结果。"""
        mapped_name = STRUCT_DA_TO_FULL_PATH.get(da.name, da.name)
        if "." in path_prefix:
            parent_path = path_prefix.rsplit(".", 1)[0]
            da_path = f"{parent_path}.{mapped_name}"
        else:
            da_path = mapped_name
        fc = fc_override or da.fc

        is_struct = str(da.b_type or "").upper() == "STRUCT"
        # This API promises DA/BDA leaf paths.  Registering the Struct parent
        # as a point produces bogus addresses such as mag.f with
        # MMS_STRUCTURE alongside the real mag.i leaf.
        if not is_struct:
            result.append(
                {
                    "name": da.name,
                    "path": da_path,
                    "fc": fc,
                    "bType": da.b_type,
                    "iecType": iec_type_from_btype(da.b_type),
                    "mmsType": mms_type_from_btype(da.b_type).value,
                    "dchg": da.dchg,
                    "qchg": da.qchg,
                    "dupd": da.dupd,
                }
            )

        if is_struct and da.type_id:
            da_type = self._dtt.da_types.get(da.type_id)
            if da_type:
                for bda in da_type.bdas:
                    if str(bda.b_type or "").upper() == "STRUCT":
                        continue
                    result.append(
                        {
                            "name": bda.name,
                            "path": f"{path_prefix}.{bda.name}",
                            "fc": fc,
                            "bType": bda.b_type,
                            "iecType": iec_type_from_btype(bda.b_type),
                            "mmsType": mms_type_from_btype(bda.b_type).value,
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
        """获取数据对象描述并返回结果。"""
        # DOI contains instance data.  Two LNs can use the same DO name/type
        # while declaring different <DAI name="dU"><Val> values, so resolve it
        # directly instead of allowing the first instance to poison the cache.
        if doi is not None:
            return self._get_do_desc_impl(do_name, do_type, doi)

        cache_key = (do_name, do_type.id)
        if cache_key in self._do_desc_cache:
            return self._do_desc_cache[cache_key]
        result = self._get_do_desc_impl(do_name, do_type)
        self._do_desc_cache[cache_key] = result
        return result

    def _get_do_desc_impl(
        self,
        do_name: str,
        do_type: SclDOType,
        doi: SclDOI | None = None,
    ) -> str:
        """获取数据对象描述并返回结果。"""
        if doi:
            du_val = doi.dai_values.get("du") or doi.dai_values.get("dU")
            if du_val:
                return du_val

        if do_type.desc:
            return do_type.desc

        for da in do_type.das:
            if da.name in ("dU", "du"):
                if da.val:
                    return da.val
                if da.desc:
                    return da.desc

        return do_name
