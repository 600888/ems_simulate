"""DataSets 插件 - 客户端 DataSet 操作

封装数据集发现、浏览、读取等功能。
从 IEC61850Client 的 discover_datasets/browse_dataset_directory/read_dataset_values 方法迁移而来。
"""

from ctypes import byref, c_bool
from typing import Any, Dict, List, Optional

from ..base import Iec61850Plugin
from ...defs.constants import HAS_IEC61850, IEC_TYPE_UNKNOWN
from ...defs.address import infer_fc_from_address, infer_iec_type_from_address
from ...core.linked_list import get_list_from_linked_list
from ...core.mms_value import mms_value_to_python
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

    def discover_datasets(self) -> List[Dict[str, Any]]:
        """发现所有逻辑设备下的 DataSet (数据集) 引用

        Returns:
            DataSet 信息列表
        """
        if not self._connection or not self._connection.is_connected:
            return []
        if not hasattr(iec61850, 'IedConnection_getLogicalDeviceDataSets'):
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
                ds_refs_raw = iec61850.IedConnection_getLogicalDeviceDataSets(
                    self._connection.connection, ld
                )
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

                    if '/' in ds_ref_str:
                        _, rest = ds_ref_str.split('/', 1)
                        catalog_ref = f"{ld}/{rest}"
                        ds_ld = ld
                        ln_part = rest.split("$")[0] if "$" in rest else ""
                    else:
                        catalog_ref = f"{ld}/{ds_ref_str}"
                        ds_ld = ld
                        ln_part = ds_ref_str.split("$")[0] if "$" in ds_ref_str else ""

                    members = self.browse_dataset_directory(catalog_ref)

                    datasets_result.append({
                        "ref": catalog_ref,
                        "name": ds_name,
                        "ld": ds_ld,
                        "ln": ln_part,
                        "member_count": len(members),
                        "members": members,
                    })
                    log.info(f"发现 DataSet: {catalog_ref}, 成员数: {len(members)}")
            except Exception as e:
                log.debug(f"发现逻辑设备 {ld} 的 DataSet 时出错: {e}")
                continue

        log.info(f"DataSet 发现完成, 共发现 {len(datasets_result)} 个 DataSet")
        return datasets_result

    def browse_dataset_directory(self, dataset_ref: str) -> List[Dict[str, Any]]:
        """浏览 DataSet 目录, 获取其成员列表 (FCDA 条目)

        Args:
            dataset_ref: DataSet 引用路径，如 "LD0/LLN0$dsGOOSE1"

        Returns:
            成员信息列表
        """
        if not self._connection or not self._connection.is_connected:
            return []
        if not hasattr(iec61850, 'IedConnection_getDataSetDirectory'):
            log.warning("pyiec61850 不支持浏览 DataSet 目录")
            return []

        try:
            mms_ref = self._connection.build_dataset_ref(dataset_ref)
            is_deletable = c_bool()
            result = None
            success_method = -1
            try_methods = [
                lambda: iec61850.IedConnection_getDataSetDirectory(
                    self._connection.connection, mms_ref, byref(is_deletable)),
                lambda: iec61850.IedConnection_getDataSetDirectory(
                    self._connection.connection, mms_ref, False),
                lambda: iec61850.IedConnection_getDataSetDirectory(
                    self._connection.connection, mms_ref, is_deletable),
                lambda: iec61850.IedConnection_getDataSetDirectory(
                    self._connection.connection, mms_ref),
            ]
            log.debug(f"getDataSetDirectory 函数类型: {type(iec61850.IedConnection_getDataSetDirectory).__name__}, "
                       f"连接状态: {self._connection.is_connected}, mms_ref={mms_ref}")

            for idx, try_fn in enumerate(try_methods):
                try:
                    result = try_fn()
                    if result is not None:
                        success_method = idx
                        break
                except TypeError:
                    continue
                except Exception:
                    continue
            if result is None:
                log.debug(f"浏览 DataSet 目录失败: 所有 API 方法均失败, ref={mms_ref}")
                return []
            log.debug(f"getDataSetDirectory ref={mms_ref}, method={success_method}")
            if isinstance(result, (list, tuple)):
                s_data_set = result[0] if result[0] else None
                dir_error = result[1] if len(result) > 1 else 0
            else:
                s_data_set = result
                dir_error = 0

            if dir_error != iec61850.IED_ERROR_OK or s_data_set is None:
                return []

            fcdas = getattr(s_data_set, 'fcdas', None)
            is_direct_ll = False
            if fcdas is None:
                fcdas = s_data_set
                is_direct_ll = True

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
                            if s and s != 'None' and not s.startswith('<'):
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
                            if s and s != 'None' and not s.startswith('<'):
                                return s
                        except Exception:
                            pass
                except Exception:
                    pass
                return ""

            members = []
            node_count = 0
            it = fcdas
            while it:
                node_count += 1
                if is_direct_ll:
                    ref_str = _extract_fcda_ref(it)
                    if ref_str:
                        fc_str = infer_fc_from_address(ref_str) if ref_str else "MX"
                        iec_type = infer_iec_type_from_address(ref_str) if ref_str else IEC_TYPE_UNKNOWN
                        members.append({"ref": ref_str, "fc": fc_str, "iec_type": iec_type, "index": 0})
                else:
                    entry = iec61850.LinkedList_getData(it)
                    if entry:
                        try:
                            ld_name = getattr(entry, 'logicalDeviceName', '') or ''
                            var_name = getattr(entry, 'variableName', '') or ''
                            comp_name = getattr(entry, 'componentName', '') or ''
                            entry_index = getattr(entry, 'index', 0) or 0
                            if ld_name and var_name:
                                if comp_name:
                                    ref_str = f"{ld_name}/{var_name}.{comp_name}"
                                    if entry_index > 0:
                                        ref_str = f"{ld_name}/{var_name}[{entry_index}].{comp_name}"
                                else:
                                    ref_str = f"{ld_name}/{var_name}"
                            else:
                                ref_str = str(entry) if entry else ""
                            fc_str = infer_fc_from_address(ref_str) if ref_str else "MX"
                            iec_type = infer_iec_type_from_address(ref_str) if ref_str else IEC_TYPE_UNKNOWN
                            members.append({"ref": ref_str, "fc": fc_str, "iec_type": iec_type, "index": entry_index})
                        except Exception as e:
                            log.debug(f"解析 DataSetEntry 出错: {e}")
                it = iec61850.LinkedList_getNext(it)

            if node_count > 0 and len(members) == 0:
                log.debug(f"DataSet {dataset_ref}: 遍历了 {node_count} 个节点但未提取到成员, is_direct_ll={is_direct_ll}")

            try:
                iec61850.LinkedList_destroy(fcdas)
            except Exception:
                pass

            return members
        except Exception as e:
            log.error(f"浏览 DataSet 目录异常: {dataset_ref}, 错误: {e}")
            return []

    def read_dataset_values(self, dataset_ref: str) -> Dict[str, Any]:
        """通过 DataSet 一次 MMS 调用读取所有成员的值

        Args:
            dataset_ref: DataSet 引用路径，如 "LD0/LLN0$dsGOOSE1"

        Returns:
            {fcda_ref: value} 字典
        """
        if not self._connection or not self._connection.is_connected:
            return {}
        if not hasattr(iec61850, 'IedConnection_readDataSetValues'):
            log.warning("pyiec61850 不支持 IedConnection_readDataSetValues")
            return []

        mms_ref = self._connection.build_dataset_ref(dataset_ref)

        client_data_set = None
        read_error = -1
        created_ds = None
        if hasattr(iec61850, 'ClientDataSet_create'):
            try:
                created_ds = iec61850.ClientDataSet_create()
            except Exception:
                created_ds = None

        try:
            if created_ds is not None:
                result = iec61850.IedConnection_readDataSetValues(
                    self._connection.connection, mms_ref, created_ds
                )
            else:
                result = iec61850.IedConnection_readDataSetValues(
                    self._connection.connection, mms_ref
                )
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
                    result = iec61850.IedConnection_readDataSetValues(
                        self._connection.connection, mms_ref
                    )
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

        if not hasattr(iec61850, 'ClientDataSet_getValues'):
            return {}

        mms_array = iec61850.ClientDataSet_getValues(client_data_set)
        if mms_array is None:
            return {}

        values = {}
        array_size = iec61850.MmsValue_getArraySize(mms_array) if hasattr(iec61850, 'MmsValue_getArraySize') else 0

        for i in range(min(array_size, len(members))):
            element = iec61850.MmsValue_getElement(mms_array, i) if hasattr(iec61850, 'MmsValue_getElement') else None
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

        try:
            iec61850.MmsValue_delete(mms_array)
        except Exception:
            pass
        try:
            iec61850.ClientDataSet_destroy(client_data_set)
        except Exception:
            pass

        return values
