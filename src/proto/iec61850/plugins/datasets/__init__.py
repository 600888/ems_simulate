"""DataSets 插件 - 客户端 DataSet 操作

封装数据集发现、浏览、读取等功能。
从 IEC61850Client 的 discover_datasets/browse_dataset_directory/read_dataset_values 方法迁移而来。
"""

import contextlib
from ctypes import c_bool
import re
from typing import Any, Dict, List, Optional

from ...core.linked_list import get_list_from_linked_list
from ...core.mms_value import mms_value_to_python
from ...defs.address import infer_fc_from_address, infer_iec_type_from_address
from ...defs.constants import HAS_IEC61850, IEC_TYPE_UNKNOWN
from ...log import log
from ..base import Iec61850Plugin

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class DataSetsPlugin:
    """DataSets 插件

    管理数据集发现、浏览、读取等客户端操作。
    """

    def __init__(self):
        self._connection = None
        self._registry = None
        self._initialized = False

    @property
    def name(self) -> str:
        return "datasets"

    @property
    def available(self) -> bool:
        return HAS_IEC61850

    def initialize(self, connection: Any, **kwargs) -> None:
        self._connection = connection
        self._registry = kwargs.get("registry")
        self._initialized = True
        log.info("DataSets 插件已初始化")

    def shutdown(self) -> None:
        self._connection = None
        self._registry = None
        self._initialized = False

    def discover_datasets(self) -> list[dict[str, Any]]:
        """发现所有逻辑设备下的 DataSet (数据集) 引用

        Returns:
            DataSet 信息列表
        """
        if not self._connection or not self._connection.is_connected:
            return []
        if not hasattr(iec61850, "IedConnection_getLogicalDeviceDataSets"):
            log.warning("pyiec61850 不支持获取逻辑设备 DataSet 列表")
            return []

        # 1. 获取逻辑设备列表
        try:
            lds = self._connection.browse_logical_devices()
        except Exception as e:
            log.error(f"发现 DataSet 时获取逻辑设备列表失败: {e}")
            return []

        datasets_result = []
        for ld in lds:
            try:
                ds_refs_raw = iec61850.IedConnection_getLogicalDeviceDataSets(self._connection.connection, ld)
                if isinstance(ds_refs_raw, (list, tuple)):
                    ds_ref_list = ds_refs_raw[0] if ds_refs_raw[0] else None
                    ds_error = ds_refs_raw[1] if len(ds_refs_raw) > 1 else 0
                else:
                    ds_ref_list = ds_refs_raw
                    ds_error = 0

                if ds_error != iec61850.IED_ERROR_OK or ds_ref_list is None:
                    continue

                ds_refs = get_list_from_linked_list(ds_ref_list)

                for ds_ref in ds_refs:
                    ds_ref_str = str(ds_ref)
                    ds_name = ds_ref_str.split("$")[-1] if "$" in ds_ref_str else ds_ref_str

                    if "/" in ds_ref_str:
                        _, rest = ds_ref_str.split("/", 1)
                        catalog_ref = f"{ld}/{rest}"
                        ds_ld = ld
                        ln_part = rest.split("$")[0] if "$" in rest else ""
                    else:
                        catalog_ref = f"{ld}/{ds_ref_str}"
                        ds_ld = ld
                        ln_part = ds_ref_str.split("$")[0] if "$" in ds_ref_str else ""

                    members = self.browse_dataset_directory(catalog_ref)

                    datasets_result.append(
                        {
                            "ref": catalog_ref,
                            "name": ds_name,
                            "ld": ds_ld,
                            "ln": ln_part,
                            "member_count": len(members),
                            "members": members,
                        }
                    )
                    log.info(f"发现 DataSet: {catalog_ref}, 成员数: {len(members)}")
            except Exception as e:
                log.debug(f"发现逻辑设备 {ld} 的 DataSet 时出错: {e}")
                continue

        log.info(f"DataSet 发现完成, 共发现 {len(datasets_result)} 个 DataSet")
        return datasets_result

    def browse_dataset_directory(self, dataset_ref: str) -> list[dict[str, Any]]:
        """浏览 DataSet 目录, 获取其成员列表 (FCDA 条目)

        Args:
            dataset_ref: DataSet 引用路径，如 "LD0/LLN0$dsGOOSE1"

        Returns:
            成员信息列表
        """
        if not self._connection or not self._connection.is_connected:
            return []
        if not hasattr(iec61850, "IedConnection_getDataSetDirectory"):
            log.warning("pyiec61850 不支持浏览 DataSet 目录")
            return []

        try:
            mms_ref = self._connection.build_dataset_ref(dataset_ref)
            result = None

            log.debug(
                f"getDataSetDirectory 函数类型: {type(iec61850.IedConnection_getDataSetDirectory).__name__}, "
                f"连接状态: {self._connection.is_connected}, mms_ref={mms_ref}"
            )

            # libIEC61850 v1.6.x 签名:
            #   LinkedList IedConnection_getDataSetDirectory(
            #       IedConnection self, IedClientError *error,
            #       const char *dataSetReference, bool *isDeletable)
            # Python SWIG 签名: (connection, dataSetRef, isDeletable) = 3个位置参数
            #   - error* 被 SWIG OUTPUT typemap 隐藏, 以返回值形式返回
            #   - isDeletable 传 None 表示不关心
            try_methods = [
                # (conn, ref, None) - isDeletable=NULL 不需要
                (
                    "ref_None",
                    lambda: iec61850.IedConnection_getDataSetDirectory(self._connection.connection, mms_ref, None),
                ),
                # (conn, ref, c_bool()) - 传 c_bool 对象
                (
                    "ref_cbool",
                    lambda: iec61850.IedConnection_getDataSetDirectory(self._connection.connection, mms_ref, c_bool()),
                ),
            ]

            for name, try_fn in try_methods:
                try:
                    r = try_fn()
                    if r is not None:
                        result = r
                        log.debug(f"getDataSetDirectory 成功: method={name}")
                        break
                    log.debug(f"getDataSetDirectory method={name}: 返回 None")
                except Exception as e:
                    log.debug(f"getDataSetDirectory method={name}: {type(e).__name__}: {e}")
                    continue

            if result is None:
                log.warning(f"浏览 DataSet 目录失败: 所有 API 方法均失败, ref={mms_ref}")
                # 打印函数签名信息辅助诊断
                try:
                    import inspect

                    sig = inspect.signature(iec61850.IedConnection_getDataSetDirectory)
                    log.warning(f"getDataSetDirectory 签名: {sig}")
                except Exception:
                    pass
                return []
            log.debug(f"getDataSetDirectory ref={mms_ref}, result type={type(result).__name__}")
            if isinstance(result, (list, tuple)):
                s_data_set = result[0] if result[0] else None
                dir_error = result[1] if len(result) > 1 else 0
            else:
                s_data_set = result
                dir_error = 0

            if dir_error != iec61850.IED_ERROR_OK or s_data_set is None:
                return []

            fcdas = getattr(s_data_set, "fcdas", None)
            is_direct_ll = False
            if fcdas is None:
                fcdas = s_data_set
                is_direct_ll = True
            log.debug(f"DataSet 提取模式: is_direct_ll={is_direct_ll}, fcdas type={type(fcdas).__name__}")

            def _extract_fcda_ref(node) -> str:
                """尝试多种方式从 LinkedList 节点提取 FCDA 引用字符串"""
                try:
                    data = iec61850.LinkedList_getData(node)
                    if data:
                        try:
                            s = iec61850.toCharP(data)
                            if s:
                                return s
                        except Exception:
                            pass
                        try:
                            s = str(data)
                            if s and s != "None" and not s.startswith("<"):
                                return s
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    raw_data = node.data
                    if raw_data:
                        try:
                            s = iec61850.toCharP(raw_data)
                            if s:
                                return s
                        except Exception:
                            pass
                        try:
                            s = str(raw_data)
                            if s and s != "None" and not s.startswith("<"):
                                return s
                        except Exception:
                            pass
                        # 回退: 使用 ctypes 将 SWIG void* 指针地址转换为字符串
                        try:
                            import ctypes

                            ptr_val = int(raw_data)
                            if ptr_val and ptr_val > 0:
                                cs = ctypes.c_char_p(ptr_val).value
                                if cs:
                                    s = cs.decode("utf-8") if isinstance(cs, bytes) else str(cs)
                                    if s:
                                        return s
                        except Exception:
                            pass
                except Exception:
                    pass
                return ""

            def _clean_fcda_ref_str(ref_str: str) -> str:
                """清除 libIEC61850 返回的 FCDA 引用中的 [FC] 后缀

                libIEC61850 的 getDataSetDirectory 返回的 FCDA 引用格式为:
                    "LD/LN.DO.da[FC]"
                例: "KG_BAMSCTMP01/MMCL1.Temp001.mag.f[MX]"
                需要清理为: "KG_BAMSCTMP01/MMCL1.Temp001.mag.f"
                """
                if not ref_str:
                    return ref_str
                return re.sub(r"\[.*?\]", "", ref_str)

            def _extract_entry_as_fcda(node, ll_data=None) -> dict:
                """将 LinkedList 节点数据作为 DataSetEntry 提取 FCDA 字段

                Returns:
                    dict 含 ref/fc/iec_type/index 或 None
                """
                entry = ll_data if ll_data is not None else None
                try:
                    if entry is None:
                        entry = iec61850.LinkedList_getData(node)
                except Exception:
                    pass
                if entry is None:
                    with contextlib.suppress(Exception):
                        entry = node.data
                if entry is None:
                    return None

                # 尝试多种可能的属性名组合
                attr_tries = [
                    ("logicalDeviceName", "variableName", "componentName"),
                    ("ldName", "varName", "compName"),
                    ("deviceName", "variableName", "componentName"),
                    ("LogicalDeviceName", "VariableName", "ComponentName"),
                ]
                for ld_attr, var_attr, comp_attr in attr_tries:
                    try:
                        ld_name = getattr(entry, ld_attr, "") or ""
                        var_name = getattr(entry, var_attr, "") or ""
                        comp_name = getattr(entry, comp_attr, "") or ""
                    except Exception:
                        continue
                    if ld_name and var_name:
                        entry_index = getattr(entry, "index", 0) or 0
                        if comp_name:
                            ref_str = f"{ld_name}/{var_name}.{comp_name}"
                            if entry_index > 0:
                                ref_str = f"{ld_name}/{var_name}[{entry_index}].{comp_name}"
                        else:
                            ref_str = f"{ld_name}/{var_name}"
                        fc_str = infer_fc_from_address(ref_str) or "MX"
                        iec_type = infer_iec_type_from_address(ref_str) or IEC_TYPE_UNKNOWN
                        log.debug(
                            f"DataSetEntry 提取成功: attr_variant={ld_attr}/{var_attr}/{comp_attr}, "
                            f"ld={ld_name}, var={var_name}, comp={comp_name}, ref={ref_str}"
                        )
                        return {"ref": ref_str, "fc": fc_str, "iec_type": iec_type, "index": entry_index}
                    if var_name and not ld_name:
                        # 没有 LD 名但 var_name 本身就包含完整路径
                        entry_index = getattr(entry, "index", 0) or 0
                        ref_str = var_name
                        if comp_name:
                            ref_str = f"{var_name}.{comp_name}"
                        if ref_str and "/" in ref_str:
                            fc_str = infer_fc_from_address(ref_str) or "MX"
                            iec_type = infer_iec_type_from_address(ref_str) or IEC_TYPE_UNKNOWN
                            return {"ref": ref_str, "fc": fc_str, "iec_type": iec_type, "index": entry_index}

                # 回退: 尝试 str(entry)
                try:
                    ref_str = str(entry)
                    if ref_str and ref_str != "None" and not ref_str.startswith("<") and "/" in ref_str:
                        fc_str = infer_fc_from_address(ref_str) or "MX"
                        iec_type = infer_iec_type_from_address(ref_str) or IEC_TYPE_UNKNOWN
                        return {"ref": ref_str, "fc": fc_str, "iec_type": iec_type, "index": 0}
                except Exception:
                    pass
                # 回退: 使用 ctypes 将 SWIG void* 指针地址转换为字符串
                try:
                    import ctypes

                    ptr_val = int(entry)
                    if ptr_val and ptr_val > 0:
                        cs = ctypes.c_char_p(ptr_val).value
                        if cs:
                            ref_str = cs.decode("utf-8") if isinstance(cs, bytes) else str(cs)
                            if ref_str and "/" in ref_str:
                                fc_str = infer_fc_from_address(ref_str) or "MX"
                                iec_type = infer_iec_type_from_address(ref_str) or IEC_TYPE_UNKNOWN
                                return {"ref": ref_str, "fc": fc_str, "iec_type": iec_type, "index": 0}
                except Exception:
                    pass
                return None

            members = []
            node_count = 0
            it = fcdas
            while it:
                node_count += 1
                # 先尝试 DataSetEntry 提取（通用路径）
                entry_data = None
                with contextlib.suppress(Exception):
                    entry_data = iec61850.LinkedList_getData(it)
                member = _extract_entry_as_fcda(it, entry_data)

                # 若 DataSetEntry 提取失败，尝试字符串提取
                if member is None:
                    ref_str = _extract_fcda_ref(it)
                    if ref_str:
                        ref_str = _clean_fcda_ref_str(ref_str)
                        fc_str = infer_fc_from_address(ref_str) or "MX"
                        iec_type = infer_iec_type_from_address(ref_str) or IEC_TYPE_UNKNOWN
                        member = {"ref": ref_str, "fc": fc_str, "iec_type": iec_type, "index": 0}

                if member:
                    # 统一清理 FCDA ref 中的 [FC] 后缀
                    member["ref"] = _clean_fcda_ref_str(member.get("ref", ""))
                    members.append(member)
                else:
                    # 记录失败调试信息
                    data_type_name = type(entry_data).__name__ if entry_data is not None else "None"
                    try:
                        str_val = str(entry_data)[:80] if entry_data is not None else "None"
                    except Exception:
                        str_val = "<str fails>"
                    log.debug(
                        f"DataSet {dataset_ref}: 节点 {node_count} 提取失败, data_type={data_type_name}, str={str_val}"
                    )
                it = iec61850.LinkedList_getNext(it)

            if node_count > 0 and len(members) == 0:
                log.warning(f"DataSet {dataset_ref}: 遍历了 {node_count} 个节点但未提取到成员")

            with contextlib.suppress(Exception):
                iec61850.LinkedList_destroy(fcdas)

            return members
        except Exception as e:
            log.error(f"浏览 DataSet 目录异常: {dataset_ref}, 错误: {e}")
            return []

    def read_dataset_values(self, dataset_ref: str) -> dict[str, Any]:
        """通过 DataSet 一次 MMS 调用读取所有成员的值

        Args:
            dataset_ref: DataSet 引用路径，如 "LD0/LLN0$dsGOOSE1"

        Returns:
            {fcda_ref: value} 字典
        """
        if not self._connection or not self._connection.is_connected:
            return {}
        if not hasattr(iec61850, "IedConnection_readDataSetValues"):
            log.warning("pyiec61850 不支持 IedConnection_readDataSetValues")
            return []

        mms_ref = self._connection.build_dataset_ref(dataset_ref)

        client_data_set = None
        read_error = -1
        created_ds = None
        if hasattr(iec61850, "ClientDataSet_create"):
            try:
                created_ds = iec61850.ClientDataSet_create()
            except Exception:
                created_ds = None

        try:
            if created_ds is not None:
                result = iec61850.IedConnection_readDataSetValues(self._connection.connection, mms_ref, created_ds)
            else:
                result = iec61850.IedConnection_readDataSetValues(self._connection.connection, mms_ref)
            if isinstance(result, (list, tuple)):
                client_data_set = result[0] if len(result) > 0 else None
                read_error = result[1] if len(result) > 1 else 0
            else:
                client_data_set = result
                read_error = 0
        except TypeError:
            tried = False
            if created_ds is not None:
                try:
                    result = iec61850.IedConnection_readDataSetValues(self._connection.connection, mms_ref)
                    if isinstance(result, (list, tuple)):
                        client_data_set = result[0] if len(result) > 0 else None
                        read_error = result[1] if len(result) > 1 else 0
                    else:
                        client_data_set = result
                        read_error = 0
                    tried = True
                except Exception:
                    pass
            if not tried:
                return {}
        except Exception:
            return {}

        if read_error != 0 or client_data_set is None:
            return {}

        members = self.browse_dataset_directory(dataset_ref)

        if not hasattr(iec61850, "ClientDataSet_getValues"):
            return {}

        mms_array = iec61850.ClientDataSet_getValues(client_data_set)
        if mms_array is None:
            return {}

        values = {}
        array_size = iec61850.MmsValue_getArraySize(mms_array) if hasattr(iec61850, "MmsValue_getArraySize") else 0

        for i in range(min(array_size, len(members))):
            element = iec61850.MmsValue_getElement(mms_array, i) if hasattr(iec61850, "MmsValue_getElement") else None
            if element is None:
                continue
            member = members[i] if i < len(members) else {}
            ref = member.get("ref", str(i))
            iec_type = member.get("iec_type", IEC_TYPE_UNKNOWN)
            try:
                val = mms_value_to_python(element, iec_type)
                if val is not None:
                    values[ref] = val
            except Exception:
                pass

        with contextlib.suppress(Exception):
            iec61850.MmsValue_delete(mms_array)
        with contextlib.suppress(Exception):
            iec61850.ClientDataSet_destroy(client_data_set)

        return values
