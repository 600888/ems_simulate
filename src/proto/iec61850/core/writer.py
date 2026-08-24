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
    IEC_TYPE_UNKNOWN,
)
from ..defs.error_codes import format_ied_error
from ..defs.mms_types import MmsType, mms_type_from_iec_type
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
        if not self._connection.ensure_connected():
            return False

        addr_str = str(address)
        ref = self._build_ref(addr_str)
        fc_name = fc or (self._registry.get_fc(addr_str) if self._registry else "")
        if fc_name == "CO":
            if self._write_control(ref, value, self._resolve_iec_type(addr_str)):
                return True
            if self._connection.reconnect_if_unhealthy(f"control {ref}"):
                return self._write_control(ref, value, self._resolve_iec_type(addr_str))
            return False

        fc_val = self._resolve_fc(addr_str, fc)
        iec_type = self._resolve_iec_type(addr_str)
        mms_type = self._resolve_mms_type(addr_str, iec_type)

        if self._write_once(addr_str, ref, value, fc_val, mms_type):
            return True

        if self._connection.reconnect_if_unhealthy(f"write {ref}"):
            return self._write_once(addr_str, ref, value, fc_val, mms_type)
        return False

    @staticmethod
    def _control_object_ref(ref: str) -> str:
        """从控制属性地址提取可执行 Oper 的控制对象引用。"""
        for suffix in (".Oper.ctlVal", ".SBOw.ctlVal", ".Cancel.ctlVal", ".ctlVal"):
            if ref.endswith(suffix):
                return ref[: -len(suffix)]
        return ref

    @staticmethod
    def _new_control_value(control, value: Any, iec_type: str):
        """按控制模型的数据类型创建供 ControlObjectClient 使用的 MmsValue。"""
        ctl_type = iec61850.ControlObjectClient_getCtlValType(control)
        if ctl_type == iec61850.MMS_BOOLEAN:
            return iec61850.MmsValue_newBoolean(Iec61850Writer._to_bool(value))
        if ctl_type == iec61850.MMS_FLOAT:
            return iec61850.MmsValue_newFloat(float(value))
        if ctl_type == iec61850.MMS_INTEGER:
            return iec61850.MmsValue_newIntegerFromInt32(Iec61850Writer._to_int(value))
        if ctl_type == iec61850.MMS_UNSIGNED:
            return iec61850.MmsValue_newUnsignedFromUint32(Iec61850Writer._to_int(value))
        if ctl_type == getattr(iec61850, "MMS_BIT_STRING", None):
            return Iec61850Writer._new_bit_string(value, 2)

        if iec_type == IEC_TYPE_BOOLEAN:
            return iec61850.MmsValue_newBoolean(Iec61850Writer._to_bool(value))
        if iec_type == IEC_TYPE_FLOAT:
            return iec61850.MmsValue_newFloat(float(value))
        if iec_type == IEC_TYPE_INTEGER:
            return iec61850.MmsValue_newIntegerFromInt32(Iec61850Writer._to_int(value))
        return None

    def _write_control(self, ref: str, value: Any, iec_type: str) -> bool:
        """通过 ControlObjectClient 执行控制命令，并确保控制对象和临时值得到释放。"""
        conn = self._connection.connection
        if not conn or not self._connection.is_connected:
            return False

        object_ref = self._control_object_ref(ref)
        control = None
        ctl_value = None
        try:
            control = iec61850.ControlObjectClient_create(object_ref, conn)
            if not control:
                log.error(f"创建 IEC61850 控制对象失败: ref={object_ref}")
                return False

            ctl_value = self._new_control_value(control, value, iec_type)
            if ctl_value is None:
                log.error(f"不支持的 IEC61850 控制值类型: ref={object_ref}, value={value!r}")
                return False

            control_model = iec61850.ControlObjectClient_getControlModel(control)
            if control_model == iec61850.CONTROL_MODEL_STATUS_ONLY:
                log.error(f"IEC61850 控制对象为只读状态模型: ref={object_ref}")
                return False
            if control_model == iec61850.CONTROL_MODEL_SBO_NORMAL:
                if not iec61850.ControlObjectClient_select(control):
                    log.error(f"IEC61850 控制对象选择失败: ref={object_ref}")
                    return False
            elif control_model == iec61850.CONTROL_MODEL_SBO_ENHANCED:
                if not iec61850.ControlObjectClient_selectWithValue(control, ctl_value):
                    log.error(f"IEC61850 控制对象带值选择失败: ref={object_ref}")
                    return False

            if not iec61850.ControlObjectClient_operate(control, ctl_value, 0):
                error = iec61850.ControlObjectClient_getLastError(control)
                log.error(f"IEC61850 控制操作失败: ref={object_ref}, error={format_ied_error(error)}")
                return False
            return True
        except Exception as e:
            log.error(f"IEC61850 控制操作异常: ref={object_ref}, error={e}")
            return False
        finally:
            if ctl_value is not None:
                iec61850.MmsValue_delete(ctl_value)
            if control is not None:
                iec61850.ControlObjectClient_destroy(control)

    def _write_once(
        self,
        address: str,
        ref: str,
        value: Any,
        fc_val,
        mms_type: MmsType,
    ) -> bool:
        """在当前连接上执行一次 MMS 写入，并确保临时 MmsValue 在结束时释放。"""
        conn = self._connection.connection
        if not conn or not self._connection.is_connected:
            return False

        try:
            if mms_type is MmsType.FLOAT:
                error = iec61850.IedConnection_writeFloatValue(conn, ref, fc_val, float(value))
                if isinstance(error, (list, tuple)):
                    error = error[1]
                if error != iec61850.IED_ERROR_OK:
                    log.error(
                        f"IEC61850 写入失败: ref={ref}, fc_val={fc_val}, mms_type=FLOAT, "
                        f"error={format_ied_error(error)}"
                    )
                return error == iec61850.IED_ERROR_OK

            if mms_type is MmsType.BOOLEAN:
                error = iec61850.IedConnection_writeBooleanValue(conn, ref, fc_val, self._to_bool(value))
                if isinstance(error, (list, tuple)):
                    error = error[1]
                if error != iec61850.IED_ERROR_OK:
                    log.error(
                        f"IEC61850 写入失败: ref={ref}, fc_val={fc_val}, mms_type=BOOLEAN, "
                        f"error={format_ied_error(error)}"
                    )
                return error == iec61850.IED_ERROR_OK

            if mms_type is MmsType.INTEGER:
                error = iec61850.IedConnection_writeInt32Value(conn, ref, fc_val, self._to_int(value))
                if isinstance(error, (list, tuple)):
                    error = error[1]
                if error != iec61850.IED_ERROR_OK:
                    log.error(
                        f"IEC61850 写入失败: ref={ref}, fc_val={fc_val}, mms_type=INTEGER, "
                        f"error={format_ied_error(error)}"
                    )
                return error == iec61850.IED_ERROR_OK

            if mms_type is MmsType.UNSIGNED:
                error = iec61850.IedConnection_writeUnsigned32Value(conn, ref, fc_val, self._to_int(value))
                if isinstance(error, (list, tuple)):
                    error = error[1]
                if error != iec61850.IED_ERROR_OK:
                    log.error(
                        f"IEC61850 写入失败: ref={ref}, fc_val={fc_val}, mms_type=UNSIGNED, "
                        f"error={format_ied_error(error)}"
                    )
                return error == iec61850.IED_ERROR_OK

            if mms_type is MmsType.VISIBLE_STRING:
                error = iec61850.IedConnection_writeVisibleStringValue(conn, ref, fc_val, str(value))
                if isinstance(error, (list, tuple)):
                    error = error[1]
                if error != iec61850.IED_ERROR_OK:
                    log.error(
                        f"IEC61850 写入失败: ref={ref}, fc_val={fc_val}, mms_type=VISIBLE_STRING, "
                        f"error={format_ied_error(error)}"
                    )
                return error == iec61850.IED_ERROR_OK

            mms_value = self._new_mms_value(address, value, mms_type)
            if mms_value is None:
                log.error(f"不支持写入的 MMS 类型: ref={ref}, mms_type={mms_type.value}")
                return False
            try:
                error = iec61850.IedConnection_writeObject(conn, ref, fc_val, mms_value)
                if isinstance(error, (list, tuple)):
                    error = error[1]
                if error != iec61850.IED_ERROR_OK:
                    log.error(
                        f"IEC61850 写入失败: ref={ref}, fc_val={fc_val}, mms_type={mms_type.value}, "
                        f"error={format_ied_error(error)}"
                    )
                return error == iec61850.IED_ERROR_OK
            finally:
                iec61850.MmsValue_delete(mms_value)
        except Exception as e:
            log.error(f"IEC61850 写入异常: address={address}, ref={ref}, mms_type={mms_type.value}, error={e}")
            return False

    @staticmethod
    def _to_bool(value: Any) -> bool:
        """把布尔、数字和常见文本表示规范化为布尔值。"""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "on", "yes"}:
                return True
            if normalized in {"0", "false", "off", "no"}:
                return False
            raise ValueError(f"无效布尔值: {value!r}")
        return bool(value)

    @staticmethod
    def _to_int(value: Any) -> int:
        """把输入转换为整数，并在转换失败时抛出明确的参数错误。"""
        if isinstance(value, str):
            return int(value.strip(), 0)
        return int(value)

    @staticmethod
    def _new_bit_string(value: Any, bit_size: int):
        """按目标位宽创建并填充 MMS BitString 值。"""
        result = iec61850.MmsValue_newBitString(max(bit_size, 1))
        iec61850.MmsValue_setBitStringFromInteger(result, Iec61850Writer._to_int(value))
        return result

    @staticmethod
    def _bit_string_size(address: str, value: Any) -> int:
        """根据 IEC 类型和数值计算 BitString 所需位宽。"""
        leaf = str(address).split(".")[-1]
        if leaf in {"Check", "ctlVal"}:
            return 2
        if leaf in {"q", "subQ"}:
            return 13
        return max(Iec61850Writer._to_int(value).bit_length(), 1)

    @staticmethod
    def _octets(value: Any) -> bytes:
        """把输入规范化为可写入 MMS OctetString 的字节序列。"""
        if isinstance(value, bytes):
            return value
        text = str(value).strip()
        if text.lower().startswith("0x"):
            text = text[2:]
        compact = text.replace(" ", "").replace(":", "").replace("-", "")
        if len(compact) % 2:
            compact = f"0{compact}"
        return bytes.fromhex(compact)

    @classmethod
    def _new_mms_value(cls, address: str, value: Any, mms_type: MmsType):
        """根据目标 MMS 类型创建底层 MmsValue，并填入待写值。"""
        if mms_type is MmsType.BIT_STRING:
            return cls._new_bit_string(value, cls._bit_string_size(address, value))
        if mms_type is MmsType.OCTET_STRING:
            octets = cls._octets(value)
            result = iec61850.MmsValue_newOctetString(len(octets), len(octets))
            for index, octet in enumerate(octets):
                iec61850.MmsValue_setOctetStringOctet(result, index, octet)
            return result
        if mms_type is MmsType.STRING:
            return iec61850.MmsValue_newMmsString(str(value))
        if mms_type is MmsType.UTC_TIME:
            return iec61850.MmsValue_newUtcTimeByMsTime(cls._to_int(value))
        if mms_type is MmsType.BINARY_TIME:
            result = iec61850.MmsValue_newBinaryTime(False)
            iec61850.MmsValue_setBinaryTime(result, cls._to_int(value))
            return result
        return None

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

    def _resolve_mms_type(self, address: str, iec_type: str) -> MmsType:
        """优先使用注册表已知类型，缺失时根据标准数据属性路径推断 MMS 类型。"""
        mms_type = ""
        if self._registry:
            get_mms_type = getattr(self._registry, "get_mms_type", None)
            if callable(get_mms_type):
                mms_type = get_mms_type(address)
        try:
            resolved = MmsType(mms_type)
        except (TypeError, ValueError):
            resolved = MmsType.UNKNOWN
        if resolved is MmsType.UNKNOWN:
            resolved = mms_type_from_iec_type(iec_type)
        return resolved
