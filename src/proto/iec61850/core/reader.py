"""IEC 61850 数据读取器

使用策略模式，按 IecType 分派不同的读取方法。
从 iec61850_client.py 的读取逻辑提取。
"""

from typing import Any, Dict, List, Optional, Tuple

from ..defs.constants import (
    HAS_IEC61850,
    IEC_TYPE_FLOAT, IEC_TYPE_BOOLEAN, IEC_TYPE_INTEGER,
    IEC_TYPE_STRING, IEC_TYPE_TIMESTAMP, IEC_TYPE_UNKNOWN,
)
from ..defs.address import infer_fc_from_address, infer_iec_type_from_address
from ..log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class FloatReader:
    """浮点值读取策略"""

    def read(self, conn, ref: str, fc_val) -> Any:
        try:
            [value, error] = iec61850.IedConnection_readFloatValue(conn, ref, fc_val)
            if error == iec61850.IED_ERROR_OK:
                return float(value)
            log.debug(f"读取浮点值失败: ref={ref}, error={error}")
        except Exception as e:
            log.debug(f"读取浮点值异常: ref={ref}, error={e}")
        return None

    def read_batch(self, conn, items: list, results: dict) -> None:
        for addr_str, ref, fc_val, _ in items:
            try:
                [value, error] = iec61850.IedConnection_readFloatValue(conn, ref, fc_val)
                if error == iec61850.IED_ERROR_OK:
                    results[addr_str] = float(value)
                else:
                    log.debug(f"批量读取浮点值失败: ref={ref}, error={error}")
            except Exception as e:
                log.debug(f"批量读取浮点值异常: ref={ref}, error={e}")


class BooleanReader:
    """布尔值读取策略 (失败时回退整数读取)"""

    def read(self, conn, ref: str, fc_val) -> Any:
        try:
            [value, error] = iec61850.IedConnection_readBooleanValue(conn, ref, fc_val)
            if error == iec61850.IED_ERROR_OK:
                return bool(value)
            # 布尔读取失败, 尝试整数读取
            if hasattr(iec61850, 'IedConnection_readIntegerValue'):
                try:
                    [int_value, int_error] = iec61850.IedConnection_readIntegerValue(conn, ref, fc_val)
                    if int_error == iec61850.IED_ERROR_OK:
                        return int(int_value)
                except Exception:
                    pass
            log.debug(f"读取布尔值失败: ref={ref}, error={error}")
        except Exception as e:
            log.debug(f"读取布尔值异常: ref={ref}, error={e}")
        return None

    def read_batch(self, conn, items: list, results: dict) -> None:
        for addr_str, ref, fc_val, _ in items:
            try:
                [value, error] = iec61850.IedConnection_readBooleanValue(conn, ref, fc_val)
                if error == iec61850.IED_ERROR_OK:
                    results[addr_str] = bool(value)
                    continue
                # 布尔读取失败, 尝试整数读取
                if hasattr(iec61850, 'IedConnection_readIntegerValue'):
                    try:
                        [int_value, int_error] = iec61850.IedConnection_readIntegerValue(conn, ref, fc_val)
                        if int_error == iec61850.IED_ERROR_OK:
                            results[addr_str] = int(int_value)
                            continue
                    except Exception:
                        pass
                log.debug(f"批量读取布尔值失败: ref={ref}, error={error}")
            except Exception as e:
                log.debug(f"批量读取布尔值异常: ref={ref}, error={e}")


class IntegerReader:
    """整数值读取策略"""

    def read(self, conn, ref: str, fc_val) -> Any:
        if not hasattr(iec61850, 'IedConnection_readIntegerValue'):
            log.debug("pyiec61850 不支持 readIntegerValue")
            return None
        try:
            [value, error] = iec61850.IedConnection_readIntegerValue(conn, ref, fc_val)
            if error == iec61850.IED_ERROR_OK:
                return int(value)
            log.debug(f"读取整数值失败: ref={ref}, error={error}")
        except Exception as e:
            log.debug(f"读取整数值异常: ref={ref}, error={e}")
        return None

    def read_batch(self, conn, items: list, results: dict) -> None:
        if not hasattr(iec61850, 'IedConnection_readIntegerValue'):
            log.debug("pyiec61850 不支持 readIntegerValue, 跳过整批量读取")
            return
        for addr_str, ref, fc_val, _ in items:
            try:
                [value, error] = iec61850.IedConnection_readIntegerValue(conn, ref, fc_val)
                if error == iec61850.IED_ERROR_OK:
                    results[addr_str] = int(value)
                else:
                    log.debug(f"批量读取整数值失败: ref={ref}, error={error}")
            except Exception as e:
                log.debug(f"批量读取整数值异常: ref={ref}, error={e}")


class StringReader:
    """字符串值读取策略"""

    def read(self, conn, ref: str, fc_val) -> Any:
        if not hasattr(iec61850, 'IedConnection_readStringValue'):
            log.debug("pyiec61850 不支持 readStringValue")
            return None
        try:
            [value, error] = iec61850.IedConnection_readStringValue(conn, ref, fc_val)
            if error == iec61850.IED_ERROR_OK:
                return str(value).strip() if value else ""
            log.debug(f"读取字符串值失败: ref={ref}, error={error}")
        except Exception as e:
            log.debug(f"读取字符串值异常: ref={ref}, error={e}")
        return None

    def read_batch(self, conn, items: list, results: dict) -> None:
        if not hasattr(iec61850, 'IedConnection_readStringValue'):
            return
        for addr_str, ref, fc_val, _ in items:
            try:
                [value, error] = iec61850.IedConnection_readStringValue(conn, ref, fc_val)
                if error == iec61850.IED_ERROR_OK:
                    results[addr_str] = str(value).strip() if value else ""
                else:
                    log.debug(f"批量读取字符串值失败: ref={ref}, error={error}")
            except Exception as e:
                log.debug(f"批量读取字符串值异常: ref={ref}, error={e}")


class TimestampReader:
    """时标值读取策略"""

    def read(self, conn, ref: str, fc_val) -> Any:
        # 先尝试整数，再回退浮点
        if hasattr(iec61850, 'IedConnection_readIntegerValue'):
            try:
                [value, error] = iec61850.IedConnection_readIntegerValue(conn, ref, fc_val)
                if error == iec61850.IED_ERROR_OK:
                    return int(value)
            except Exception:
                pass
        try:
            [value, error] = iec61850.IedConnection_readFloatValue(conn, ref, fc_val)
            if error == iec61850.IED_ERROR_OK:
                return float(value)
        except Exception:
            pass
        log.debug(f"读取时标值失败: ref={ref}")
        return None

    def read_batch(self, conn, items: list, results: dict) -> None:
        for addr_str, ref, fc_val, _ in items:
            value = self.read(conn, ref, fc_val)
            if value is not None:
                results[addr_str] = value


class AutoDetectReader:
    """自动探测读取策略 - 依次尝试浮点、布尔、整数、字符串"""

    def read(self, conn, ref: str, fc_val) -> Any:
        # 尝试浮点
        try:
            [value, error] = iec61850.IedConnection_readFloatValue(conn, ref, fc_val)
            if error == iec61850.IED_ERROR_OK:
                return float(value)
        except Exception:
            pass

        # 尝试布尔
        try:
            [value, error] = iec61850.IedConnection_readBooleanValue(conn, ref, fc_val)
            if error == iec61850.IED_ERROR_OK:
                return bool(value)
        except Exception:
            pass

        # 尝试整数
        if hasattr(iec61850, 'IedConnection_readIntegerValue'):
            try:
                [value, error] = iec61850.IedConnection_readIntegerValue(conn, ref, fc_val)
                if error == iec61850.IED_ERROR_OK:
                    return int(value)
            except Exception:
                pass

        # 尝试字符串
        if hasattr(iec61850, 'IedConnection_readStringValue'):
            try:
                [value, error] = iec61850.IedConnection_readStringValue(conn, ref, fc_val)
                if error == iec61850.IED_ERROR_OK:
                    return str(value).strip() if value else ""
            except Exception:
                pass

        log.error(f"自动探测读取失败: ref={ref}")
        return None

    def read_batch(self, conn, items: list, results: dict) -> None:
        for addr_str, ref, fc_val, _ in items:
            value = self.read(conn, ref, fc_val)
            if value is not None:
                results[addr_str] = value


# 策略注册表
READ_STRATEGIES = {
    IEC_TYPE_FLOAT: FloatReader(),
    IEC_TYPE_BOOLEAN: BooleanReader(),
    IEC_TYPE_INTEGER: IntegerReader(),
    IEC_TYPE_STRING: StringReader(),
    IEC_TYPE_TIMESTAMP: TimestampReader(),
    IEC_TYPE_UNKNOWN: AutoDetectReader(),
}


class Iec61850Reader:
    """数据读取器 (组合模式)

    组合连接管理和策略分派，提供统一的读取接口。
    """

    def __init__(self, connection, registry=None):
        """
        Args:
            connection: Iec61850Connection 实例
            registry: PointRegistry 实例 (可选，用于地址映射)
        """
        self._connection = connection
        self._registry = registry

    def read(self, address: str, fc: str = "") -> Any:
        """读取单个测点值

        Args:
            address: 测点地址
            fc: 功能约束 (为空时自动推断)
        """
        conn = self._connection.connection
        if not conn or not self._connection.is_connected:
            return None

        addr_str = str(address)
        ref = self._build_ref(addr_str)
        fc_val = self._resolve_fc(addr_str, fc)
        iec_type = self._resolve_iec_type(addr_str)

        strategy = READ_STRATEGIES.get(iec_type, READ_STRATEGIES[IEC_TYPE_UNKNOWN])
        try:
            return strategy.read(conn, ref, fc_val)
        except Exception as e:
            log.error(f"IEC61850 读取异常: address={address}, error={e}")
            return None

    def read_batch(self, addresses: List[str], fc_map: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """批量读取多个测点值

        按 iec_type 分组批量读取。

        Args:
            addresses: 测点地址列表
            fc_map: 地址 -> FC 的映射 (可选)
        """
        conn = self._connection.connection
        if not conn or not self._connection.is_connected:
            return {}

        # 按 iec_type 分组
        groups: Dict[str, list] = {}
        for addr in addresses:
            addr_str = str(addr)
            ref = self._build_ref(addr_str)
            fc = ""
            if fc_map and addr_str in fc_map:
                fc = fc_map[addr_str]
            fc_val = self._resolve_fc(addr_str, fc)
            iec_type = self._resolve_iec_type(addr_str)

            if iec_type not in groups:
                groups[iec_type] = []
            groups[iec_type].append((addr_str, ref, fc_val, iec_type))

        results: Dict[str, Any] = {}
        for iec_type, items in groups.items():
            strategy = READ_STRATEGIES.get(iec_type, READ_STRATEGIES[IEC_TYPE_UNKNOWN])
            strategy.read_batch(conn, items, results)

        return results

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
                rest = address.split('/', 1)[1]
                return f"{self._connection.model_name}{ld_inst}/{rest}"

        safe_addr = str(address).replace('.', '_').replace('/', '_').replace('\\', '_').replace('-', '_')
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
