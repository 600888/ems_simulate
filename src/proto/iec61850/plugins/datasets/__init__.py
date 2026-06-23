"""DataSets 插件 - 客户端 DataSet 操作

封装数据集发现、浏览、读取等功能。
从 IEC61850Client 的 discover_datasets/browse_dataset_directory/read_dataset_values 方法迁移而来。
"""

import contextlib
from ctypes import c_bool
import re
from typing import Any

from ...core.linked_list import get_list_from_linked_list
from ...core.mms_value import mms_value_to_python
from ...defs.address import infer_fc_from_address, infer_iec_type_from_address
from ...defs.constants import HAS_IEC61850, IEC_TYPE_UNKNOWN
from ...log import log

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
        self._dataset_members_cache: dict[str, list[dict[str, Any]]] = {}

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
        self._dataset_members_cache.clear()

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
            # LinkedList 头节点是 dummy 节点（无数据），
            # 必须从 LinkedList_getNext 开始遍历实际数据节点。
            # 参考 core/linked_list.py:get_list_from_linked_list 和 plugins/files/directory.py
            it = iec61850.LinkedList_getNext(fcdas)
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

    def _get_dataset_members_cached(self, dataset_ref: str) -> list[dict[str, Any]]:
        cache_key = self._connection.build_dataset_ref(dataset_ref) if self._connection else dataset_ref
        if cache_key in self._dataset_members_cache:
            return self._dataset_members_cache[cache_key]
        members = self.browse_dataset_directory(dataset_ref)
        if members:
            self._dataset_members_cache[cache_key] = members
        return members

    def _read_dataset_values_by_mms(self, dataset_ref: str) -> dict[str, Any]:
        """Read a DataSet in one MMS request via NamedVariableList values."""
        required = (
            "IedConnection_getMmsConnection",
            "MmsConnection_readNamedVariableListValues",
            "MmsError_create",
            "MmsError_getValue",
            "MmsValue_getArraySize",
            "MmsValue_getElement",
        )
        if not all(hasattr(iec61850, name) for name in required):
            log.debug(f"MMS DataSet read unavailable: missing API, ref={dataset_ref}")
            return {}

        mms_ref = self._connection.build_dataset_ref(dataset_ref)
        slash = mms_ref.find("/")
        if slash <= 0 or slash == len(mms_ref) - 1:
            log.warning(f"MMS DataSet read failed: invalid ref={dataset_ref}, mms_ref={mms_ref}")
            return {}
        domain_id = mms_ref[:slash]
        item_id = mms_ref[slash + 1 :].replace(".", "$")

        # 诊断: 检查 domain_id 是否在已发现的 LD 列表中
        discovered_lds = getattr(self._connection, "_discovered_lds", []) or []
        if discovered_lds and domain_id not in discovered_lds:
            log.warning(
                f"MMS DataSet read: domain_id='{domain_id}' 不在已发现 LD 列表中, "
                f"dataset_ref={dataset_ref}, mms_ref={mms_ref}, discovered_lds={discovered_lds[:5]}"
            )

        try:
            mms_conn = iec61850.IedConnection_getMmsConnection(self._connection.connection)
        except Exception as e:
            log.warning(f"MMS DataSet read failed: get MmsConnection exception, ref={dataset_ref}, error={e}")
            return {}
        if not mms_conn:
            log.warning(f"MMS DataSet read failed: no MmsConnection, ref={dataset_ref}")
            return {}

        mms_error = None
        values_array = None
        try:
            mms_error = iec61850.MmsError_create()
            values_array = iec61850.MmsConnection_readNamedVariableListValues(
                mms_conn, mms_error, domain_id, item_id, False
            )
            error_code = iec61850.MmsError_getValue(mms_error)
            if error_code != 0:
                error_text = ""
                with contextlib.suppress(Exception):
                    error_text = iec61850.MmsError_toString(mms_error)
                log.warning(
                    f"MMS DataSet read failed: ref={dataset_ref}, domain={domain_id}, "
                    f"item={item_id}, error={error_code}, text={error_text}"
                )
                return {}
            if not values_array:
                log.warning(f"MMS DataSet read returned no data: ref={dataset_ref}, domain={domain_id}, item={item_id}")
                return {}

            members = self._get_dataset_members_cached(dataset_ref)
            array_size = iec61850.MmsValue_getArraySize(values_array)
            out: dict[str, Any] = {}
            for i in range(array_size):
                element = iec61850.MmsValue_getElement(values_array, i)
                if element is None:
                    continue
                member = members[i] if i < len(members) else {}
                ref = member.get("ref") or f"data[{i}]"
                iec_type = member.get("iec_type", IEC_TYPE_UNKNOWN)
                value = mms_value_to_python(element, iec_type)
                if value is not None:
                    out[ref] = value

            if out:
                log.info(f"MMS DataSet read succeeded: ref={dataset_ref}, values={len(out)}")
            else:
                log.warning(
                    f"MMS DataSet read decoded no values: ref={dataset_ref}, size={array_size}, members={len(members)}"
                )
            return out
        except Exception as e:
            log.warning(f"MMS DataSet read exception: ref={dataset_ref}, domain={domain_id}, item={item_id}, error={e}")
            return {}
        finally:
            if values_array:
                with contextlib.suppress(Exception):
                    iec61850.MmsValue_delete(values_array)
            if mms_error is not None:
                # 注意: SWIG 导出的析构函数名是 MmsErrror_destroy (三个 r 的拼写错误, 见 patches/iec61850.i)
                destroy = getattr(iec61850, "MmsErrror_destroy", None) or getattr(iec61850, "MmsError_destroy", None)
                if destroy is not None:
                    with contextlib.suppress(Exception):
                        destroy(mms_error)

    def _read_dataset_values_by_members(self, dataset_ref: str, reason: str = "") -> dict[str, Any]:
        """Fallback DataSet read: browse members and read each FCDA with readObject."""
        members = self._get_dataset_members_cached(dataset_ref)
        if not members:
            log.warning(f"Read DataSet values fallback failed: no members, ref={dataset_ref}, reason={reason}")
            return {}
        if not hasattr(iec61850, "IedConnection_readObject"):
            log.warning(
                f"Read DataSet values fallback failed: readObject unavailable, ref={dataset_ref}, reason={reason}"
            )
            return {}

        values: dict[str, Any] = {}
        for member in members:
            ref = member.get("ref") or ""
            if not ref:
                continue
            mms_ref = self._connection.build_dataset_ref(ref)
            fc = member.get("fc") or infer_fc_from_address(ref) or "MX"
            iec_type = member.get("iec_type") or infer_iec_type_from_address(ref) or IEC_TYPE_UNKNOWN
            try:
                fc_val = self._connection.get_fc_value(fc)
                result = iec61850.IedConnection_readObject(self._connection.connection, mms_ref, fc_val)
                if isinstance(result, (list, tuple)):
                    mms_value = result[0] if len(result) > 0 else None
                    error = result[1] if len(result) > 1 else 0
                else:
                    mms_value = result
                    error = 0
                if error != iec61850.IED_ERROR_OK or mms_value is None:
                    log.debug(f"Read DataSet member failed: ref={ref}, mms_ref={mms_ref}, fc={fc}, error={error}")
                    continue
                value = mms_value_to_python(mms_value, iec_type)
                if value is not None:
                    values[ref] = value
                with contextlib.suppress(Exception):
                    iec61850.MmsValue_delete(mms_value)
            except Exception as e:
                log.debug(f"Read DataSet member exception: ref={ref}, mms_ref={mms_ref}, fc={fc}, error={e}")

        if values:
            log.warning(
                f"Read DataSet values fallback succeeded: ref={dataset_ref}, values={len(values)}, reason={reason}"
            )
        else:
            log.warning(
                "Read DataSet values fallback got no values: "
                f"ref={dataset_ref}, members={len(members)}, reason={reason}"
            )
        return values

    def read_dataset_values(self, dataset_ref: str) -> dict[str, Any]:
        """通过 DataSet 一次 MMS 调用读取所有成员的值

        Args:
            dataset_ref: DataSet 引用路径，如 "LD0/LLN0$dsGOOSE1"

        Returns:
            {fcda_ref: value} 字典
        """
        if not self._connection or not self._connection.ensure_connected():
            log.warning(f"Read DataSet values skipped: connection is not active, ref={dataset_ref}")
            return {}

        values = self._read_dataset_values_once(dataset_ref)
        if values:
            return values

        if self._connection.reconnect_if_unhealthy(f"read dataset {dataset_ref}"):
            return self._read_dataset_values_once(dataset_ref)
        return values

    def _read_dataset_values_once(self, dataset_ref: str) -> dict[str, Any]:
        # 直接走 MMS 层原语: MmsConnection_readNamedVariableListValues
        # 不使用 IedConnection_readDataSetValues, 因为 pyiec61850 的 SWIG wrapper
        # 对 ClientDataSet 参数应用了 NULL-safety typemap, 拒绝 None 作为
        # "allocate a new one" 哨兵, 在 Python 中不可用。
        mms_values = self._read_dataset_values_by_mms(dataset_ref)
        if mms_values:
            return mms_values

        # Fallback: 逐成员读取 (慢路径)
        return self._read_dataset_values_by_members(
            dataset_ref, reason="MMS readNamedVariableListValues returned no values"
        )
