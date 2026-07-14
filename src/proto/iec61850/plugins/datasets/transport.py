"""使用单次 MMS 请求读取 DataSet 的原生传输层。"""

from __future__ import annotations

import contextlib
from typing import Any

from ...core.mms_value import mms_value_to_python
from ...defs.constants import IEC_TYPE_UNKNOWN
from ...defs.mms_types import MmsType, mms_type_from_native
from ...log import log
from .models import DatasetDescriptor, DatasetMemberError, DatasetReadResult


class DatasetTransport:
    """在连接锁内读取持久 DataSet，并统一管理原生资源生命周期。"""

    def __init__(self, connection: Any, native: Any):
        """注入连接管理器和原生绑定，便于隔离测试。"""
        self._connection = connection
        self._native = native

    def read(self, dataset: DatasetDescriptor) -> DatasetReadResult:
        """在 ``native_operation`` 保护下执行一次 DataSet 读取。"""
        with self._connection.native_operation() as conn:
            if conn is None:
                return self._failure(dataset, "connection is not active", request_count=0)
            return self._read_locked(conn, dataset)

    def _read_locked(self, conn: Any, dataset: DatasetDescriptor) -> DatasetReadResult:
        """调用 NamedVariableList 原语，并保证所有返回资源最终释放。"""
        native = self._native
        mms_ref = self._connection.build_dataset_ref(dataset.ref)
        if "/" not in mms_ref:
            return self._failure(dataset, f"invalid DataSet reference: {mms_ref}", request_count=0)
        domain_id, item_id = mms_ref.split("/", 1)
        item_id = item_id.replace(".", "$")

        try:
            mms_conn = native.IedConnection_getMmsConnection(conn)
        except Exception as exc:
            return self._failure(dataset, f"get MmsConnection failed: {exc}", request_count=0)
        if not mms_conn:
            return self._failure(dataset, "MmsConnection is unavailable", request_count=0)

        mms_error = None
        values_array = None
        try:
            mms_error = native.MmsError_create()
            values_array = native.MmsConnection_readNamedVariableListValues(
                mms_conn,
                mms_error,
                domain_id,
                item_id,
                # 部分 IED 在 False 时返回 object-constraint-conflict；
                # True 要求响应携带访问规格，现场设备与标准服务均可解析。
                True,
            )
            error_code = int(native.MmsError_getValue(mms_error))
            if error_code != 0:
                error_text = ""
                to_string = getattr(native, "MmsError_toString", None)
                if callable(to_string):
                    with contextlib.suppress(Exception):
                        error_text = str(to_string(error_code) or "")
                detail = f" ({error_text})" if error_text else ""
                return self._failure(dataset, f"MMS error {error_code}{detail}")
            if values_array is None:
                return self._failure(dataset, "server returned no values")

            array_size = int(native.MmsValue_getArraySize(values_array))
            if array_size != len(dataset.members):
                return self._failure(
                    dataset,
                    f"member count mismatch: directory={len(dataset.members)}, values={array_size}",
                )
            return self._decode_values(dataset, values_array)
        except Exception as exc:
            log.debug(f"MMS DataSet read exception: ref={dataset.ref}, error={exc}")
            return self._failure(dataset, f"native exception: {exc}")
        finally:
            if values_array is not None:
                with contextlib.suppress(Exception):
                    native.MmsValue_delete(values_array)
            if mms_error is not None:
                destroy = getattr(native, "MmsErrror_destroy", None) or getattr(native, "MmsError_destroy", None)
                if callable(destroy):
                    with contextlib.suppress(Exception):
                        destroy(mms_error)

    def _decode_values(self, dataset: DatasetDescriptor, values_array: Any) -> DatasetReadResult:
        """按成员序号解码；单个成员失败不会丢弃其他成员的成功结果。"""
        values: list[tuple[str, Any]] = []
        member_values: list[tuple[str, Any]] = []
        runtime_types: list[tuple[str, str]] = []
        errors: list[DatasetMemberError] = []

        for member in dataset.members:
            element = self._native.MmsValue_getElement(values_array, member.index)
            if element is None:
                errors.append(DatasetMemberError(member.index, member.ref, "missing value"))
                continue
            element_type = self._runtime_type(element)
            if element_type is MmsType.DATA_ACCESS_ERROR:
                errors.append(DatasetMemberError(member.index, member.ref, "data access error"))
                continue

            top_value = mms_value_to_python(element, member.iec_type)
            if top_value is not None:
                member_values.append((member.ref, top_value))

            leaves = self._flatten_scalars(element)
            if not member.leaf_refs:
                errors.append(DatasetMemberError(member.index, member.ref, "member has no safe model projection"))
                continue
            # 部分厂商/模拟服务的目录将 FCDA 暴露为 DO 级引用，但线上
            # NamedVariableList 只返回主值标量，而不是完整的 value/q/t 结构。
            # 只有目录构建时已证明存在唯一业务测点，才允许兼容映射。
            if len(leaves) == 1 and len(member.leaf_refs) != 1 and member.scalar_ref:
                leaf = leaves[0]
                runtime_type = self._runtime_type(leaf)
                value = mms_value_to_python(leaf, IEC_TYPE_UNKNOWN)
                if runtime_type is not MmsType.DATA_ACCESS_ERROR and value is not None:
                    values.append((member.scalar_ref, value))
                    runtime_types.append((member.scalar_ref, runtime_type.value))
                    continue
            if len(leaves) != len(member.leaf_refs):
                errors.append(
                    DatasetMemberError(
                        member.index,
                        member.ref,
                        f"projection mismatch: model={len(member.leaf_refs)}, values={len(leaves)}",
                    )
                )
                continue

            member_failed = False
            decoded: list[tuple[str, Any, MmsType]] = []
            for ref, leaf in zip(member.leaf_refs, leaves, strict=True):
                runtime_type = self._runtime_type(leaf)
                if runtime_type is MmsType.DATA_ACCESS_ERROR:
                    member_failed = True
                    break
                value = mms_value_to_python(leaf, IEC_TYPE_UNKNOWN)
                if value is None:
                    member_failed = True
                    break
                decoded.append((ref, value, runtime_type))
            if member_failed:
                errors.append(DatasetMemberError(member.index, member.ref, "leaf decode failed"))
                continue
            for ref, value, runtime_type in decoded:
                values.append((ref, value))
                runtime_types.append((ref, runtime_type.value))

        return DatasetReadResult(
            dataset_ref=dataset.ref,
            values=tuple(values),
            member_values=tuple(member_values),
            runtime_types=tuple(runtime_types),
            errors=tuple(errors),
            request_count=1,
        )

    def _flatten_scalars(self, value: Any) -> list[Any]:
        """按 MMS 结构原始顺序递归展开标量叶子。"""
        value_type = self._runtime_type(value)
        if value_type not in (MmsType.ARRAY, MmsType.STRUCTURE):
            return [value]
        leaves: list[Any] = []
        try:
            size = int(self._native.MmsValue_getArraySize(value))
            for index in range(size):
                child = self._native.MmsValue_getElement(value, index)
                if child is not None:
                    leaves.extend(self._flatten_scalars(child))
        except Exception:
            return []
        return leaves

    def _runtime_type(self, value: Any) -> MmsType:
        """读取原生 MMS 类型，异常时返回 UNKNOWN 而不是猜测。"""
        try:
            return mms_type_from_native(int(self._native.MmsValue_getType(value)), self._native)
        except Exception:
            return MmsType.UNKNOWN

    @staticmethod
    def _failure(
        dataset: DatasetDescriptor,
        reason: str,
        *,
        request_count: int = 1,
    ) -> DatasetReadResult:
        """将整个 DataSet 级错误展开为可诊断的逐成员失败。"""
        errors = tuple(DatasetMemberError(member.index, member.ref, reason) for member in dataset.members)
        if not errors:
            errors = (DatasetMemberError(-1, dataset.ref, reason),)
        return DatasetReadResult(dataset_ref=dataset.ref, errors=errors, request_count=request_count)
