"""IEC 61850 数据写入器

使用策略模式，按 IecType 分派不同的写入方法。
从 iec61850_client.py 的写入逻辑提取。
"""

from typing import Any

from ..defs.address import infer_fc_from_address, infer_iec_type_from_address
from ..defs.constants import (
    HAS_IEC61850,
    IEC_TYPE_BOOLEAN,
    IEC_TYPE_FLOAT,
    IEC_TYPE_INTEGER,
    IEC_TYPE_STRING,
    IEC_TYPE_UNKNOWN,
)
from ..log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class Iec61850Writer:
    """数据写入器 (策略模式)

    根据 iec_type 选择正确的 IEC 61850 写入方法。
    """

    def __init__(self, connection, registry=None):
        """
        Args:
            connection: Iec61850Connection 实例
            registry: PointRegistry 实例 (可选)
        """
        self._connection = connection
        self._registry = registry

    def write(self, address: str, value: Any, fc: str = "") -> bool:
        """写入测点值

        Args:
            address: 测点地址
            value: 要写入的值
            fc: 功能约束 (为空时自动推断)

        Returns:
            是否写入成功
        """
        conn = self._connection.connection
        if not conn or not self._connection.is_connected:
            return False

        addr_str = str(address)
        ref = self._build_ref(addr_str)
        fc_val = self._resolve_fc(addr_str, fc)
        iec_type = self._resolve_iec_type(addr_str)

        try:
            if iec_type == IEC_TYPE_FLOAT:
                error = iec61850.IedConnection_writeFloatValue(conn, ref, fc_val, float(value))
                return error == iec61850.IED_ERROR_OK

            elif iec_type == IEC_TYPE_BOOLEAN:
                error = iec61850.IedConnection_writeBooleanValue(conn, ref, fc_val, bool(value))
                return error == iec61850.IED_ERROR_OK

            elif iec_type == IEC_TYPE_INTEGER:
                if hasattr(iec61850, "IedConnection_writeIntegerValue"):
                    error = iec61850.IedConnection_writeIntegerValue(conn, ref, fc_val, int(value))
                    return error == iec61850.IED_ERROR_OK
                else:
                    log.error(f"pyiec61850 不支持 writeIntegerValue: ref={ref}")
                    return False

            elif iec_type == IEC_TYPE_STRING:
                if hasattr(iec61850, "IedConnection_writeStringValue"):
                    error = iec61850.IedConnection_writeStringValue(conn, ref, fc_val, str(value))
                    return error == iec61850.IED_ERROR_OK
                else:
                    log.error(f"pyiec61850 不支持 writeStringValue: ref={ref}")
                    return False

            else:
                # UNKNOWN: 根据 value 类型选择
                if isinstance(value, float):
                    error = iec61850.IedConnection_writeFloatValue(conn, ref, fc_val, float(value))
                    return error == iec61850.IED_ERROR_OK
                elif isinstance(value, bool):
                    error = iec61850.IedConnection_writeBooleanValue(conn, ref, fc_val, bool(value))
                    return error == iec61850.IED_ERROR_OK
                elif isinstance(value, int):
                    if hasattr(iec61850, "IedConnection_writeIntegerValue"):
                        error = iec61850.IedConnection_writeIntegerValue(conn, ref, fc_val, int(value))
                        return error == iec61850.IED_ERROR_OK
                    # 回退: 用浮点写入
                    error = iec61850.IedConnection_writeFloatValue(conn, ref, fc_val, float(value))
                    return error == iec61850.IED_ERROR_OK
                elif isinstance(value, str):
                    if hasattr(iec61850, "IedConnection_writeStringValue"):
                        error = iec61850.IedConnection_writeStringValue(conn, ref, fc_val, str(value))
                        return error == iec61850.IED_ERROR_OK
                    return False
                else:
                    log.error(f"不支持写入的数据类型: ref={ref}, value_type={type(value)}")
                    return False

        except Exception as e:
            log.error(f"IEC61850 写入异常: address={address}, error={e}")
            return False

    def _build_ref(self, address: str) -> str:
        """构建 MMS 引用路径"""
        if self._registry:
            ref = self._registry.get_ref(address)
            if ref:
                return ref

        from ..defs.address import is_full_ref, parse_ref

        if is_full_ref(address):
            parsed = parse_ref(address)
            if parsed:
                ld_inst = parsed[0]
                rest = address.split("/", 1)[1]
                return f"{self._connection.model_name}{ld_inst}/{rest}"

        safe_addr = str(address).replace(".", "_").replace("/", "_").replace("\\", "_").replace("-", "_")
        iec_type = self._resolve_iec_type(address)
        if iec_type == IEC_TYPE_FLOAT:
            return f"{self._connection.model_name}{self._connection.ld_name}/MMXU1.MV_{safe_addr}.mag.f"
        else:
            return f"{self._connection.model_name}{self._connection.ld_name}/GGIO1.SPS_{safe_addr}.stVal"

    def _resolve_fc(self, address: str, fc: str = ""):
        """解析 FC"""
        if not fc and self._registry:
            fc = self._registry.get_fc(address)
        if not fc:
            fc = infer_fc_from_address(address)
        return self._connection.get_fc_value(fc)

    def _resolve_iec_type(self, address: str) -> str:
        """解析 iec_type"""
        iec_type = ""
        if self._registry:
            iec_type = self._registry.get_iec_type(address)
        if iec_type == IEC_TYPE_UNKNOWN or not iec_type:
            iec_type = infer_iec_type_from_address(address)
        return iec_type
