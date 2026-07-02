"""DataSet 引用规范化、目录索引与读取计划。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import re
from types import MappingProxyType
from typing import Any

from .models import DatasetDescriptor, DatasetMember, DatasetReadPlan

_FC_SUFFIX_RE = re.compile(r"\[([A-Za-z]{2})\]\s*$")
_KNOWN_FCS = frozenset(
    {"ST", "MX", "SP", "SV", "CF", "DC", "SG", "SE", "SR", "OR", "BL", "EX", "CO", "US", "MS", "RP", "BR", "LG", "GO"}
)


def strip_fc_suffix(ref: str) -> tuple[str, str]:
    """移除 libIEC61850 返回的 ``[FC]`` 后缀，并保留真实 FC。"""
    text = str(ref or "").strip()
    match = _FC_SUFFIX_RE.search(text)
    if not match:
        return text, ""
    return text[: match.start()].strip(), match.group(1).upper()


def _with_model_prefix(ref: str, model_name: str) -> str:
    """为不含 IED 前缀的 LD 引用补齐模型名称。"""
    if not ref or "/" not in ref or not model_name:
        return ref
    ld_name, rest = ref.split("/", 1)
    if ld_name.startswith(model_name):
        return ref
    return f"{model_name}{ld_name}/{rest}"


def normalize_dataset_ref(ref: str, model_name: str = "") -> str:
    """将 DataSet 引用统一为稳定的 ``LD/LN$dataset`` 目录键。"""
    cleaned, _ = strip_fc_suffix(ref)
    cleaned = _with_model_prefix(cleaned, model_name)
    if "/" not in cleaned:
        return cleaned
    ld_name, item = cleaned.split("/", 1)
    if "$" not in item and "." in item:
        ln_name, dataset_name = item.split(".", 1)
        item = f"{ln_name}${dataset_name}"
    return f"{ld_name}/{item}"


def normalize_point_ref(ref: str, model_name: str = "") -> str:
    """统一 ACSI 点号语法与 MMS ``$FC$`` 变量语法的对象引用。"""
    cleaned, _ = strip_fc_suffix(ref)
    cleaned = _with_model_prefix(cleaned, model_name)
    if "/" not in cleaned:
        return cleaned
    ld_name, item = cleaned.split("/", 1)
    if "$" not in item:
        return f"{ld_name}/{item}"

    parts = item.split("$")
    ln_name = parts[0]
    tail = parts[1:]
    if tail and tail[0].upper() in _KNOWN_FCS:
        tail = tail[1:]
    return f"{ld_name}/{ln_name}{'.' if tail else ''}{'.'.join(tail)}"


class DatasetCatalog:
    """不可变 DataSet 目录，并提供测点到 DataSet 的反向索引。"""

    def __init__(
        self,
        datasets: Sequence[DatasetDescriptor] = (),
        address_to_ref: Mapping[str, str] | None = None,
    ) -> None:
        """冻结目录内容并一次性建立正反向索引，读取热路径不再遍历全表。"""
        self.datasets = tuple(datasets)
        normalized_addresses = dict(address_to_ref or {})
        self.address_to_ref = MappingProxyType(normalized_addresses)

        ref_to_addresses: dict[str, list[str]] = {}
        for address, ref in normalized_addresses.items():
            ref_to_addresses.setdefault(ref, []).append(address)
        self.ref_to_addresses = MappingProxyType({ref: tuple(addresses) for ref, addresses in ref_to_addresses.items()})

        point_to_datasets: dict[str, list[DatasetDescriptor]] = {}
        for dataset in self.datasets:
            covered_refs = {leaf_ref for member in dataset.members for leaf_ref in member.leaf_refs}
            for ref in covered_refs:
                for address in ref_to_addresses.get(ref, ()):
                    point_to_datasets.setdefault(address, []).append(dataset)
        self.point_to_datasets = MappingProxyType(
            {address: tuple(items) for address, items in point_to_datasets.items()}
        )

    @classmethod
    def from_sources(
        cls,
        datasets: Iterable[Mapping[str, Any]],
        *,
        registry: Any = None,
        model: Any = None,
        model_name: str = "",
    ) -> DatasetCatalog:
        """从注册表、统一模型和兼容字典构造强类型目录。"""
        address_to_ref = cls._address_index(registry, model_name)
        leaf_index = cls._model_leaf_index(model, model_name)
        descriptors: list[DatasetDescriptor] = []

        for raw_dataset in datasets:
            dataset_ref = normalize_dataset_ref(str(raw_dataset.get("ref", "")), model_name)
            if not dataset_ref:
                continue
            members: list[DatasetMember] = []
            for ordinal, raw_member in enumerate(raw_dataset.get("members", ()) or ()):
                raw_ref, suffix_fc = strip_fc_suffix(str(raw_member.get("ref", "")))
                member_ref = normalize_point_ref(raw_ref, model_name)
                if not member_ref:
                    continue
                fc = str(raw_member.get("fc", "") or suffix_fc).upper()
                leaf_refs = cls._project_member(member_ref, fc, leaf_index, address_to_ref.values())
                members.append(
                    DatasetMember(
                        index=ordinal,
                        ref=member_ref,
                        fc=fc,
                        iec_type=str(raw_member.get("iec_type", "unknown") or "unknown"),
                        mms_type=str(raw_member.get("mms_type", "MMS_UNKNOWN") or "MMS_UNKNOWN"),
                        leaf_refs=leaf_refs,
                    )
                )
            descriptors.append(
                DatasetDescriptor(
                    ref=dataset_ref,
                    name=str(raw_dataset.get("name", "") or dataset_ref.rsplit("$", 1)[-1]),
                    members=tuple(members),
                )
            )

        descriptors.sort(key=lambda item: item.ref)
        return cls(descriptors, address_to_ref)

    @staticmethod
    def _address_index(registry: Any, model_name: str) -> dict[str, str]:
        """构造应用测点地址到规范 MMS 引用的映射。"""
        if registry is None:
            return {}
        raw_refs = getattr(registry, "point_refs", {}) or {}
        return {str(address): normalize_point_ref(str(ref), model_name) for address, ref in raw_refs.items()}

    @staticmethod
    def _model_leaf_index(model: Any, model_name: str) -> tuple[tuple[str, str], ...]:
        """按 IedModel 原始顺序收集全部 DA/BDA 叶子，供结构值投影。"""
        if model is None:
            return ()
        leaves: list[tuple[str, str]] = []
        try:
            for _, _, data_object, data_attribute in model.iter_da_leaves():
                ref = normalize_point_ref(f"{data_object.ref}.{data_attribute.path}", model_name)
                leaves.append((ref, str(data_attribute.fc or "").upper()))
        except Exception:
            return ()
        return tuple(leaves)

    @staticmethod
    def _project_member(
        member_ref: str,
        fc: str,
        model_leaves: tuple[tuple[str, str], ...],
        point_refs: Iterable[str],
    ) -> tuple[str, ...]:
        """把 FCDA 投影为叶子引用；不能由模型证明时只接受精确匹配。"""
        exact_model = tuple(ref for ref, leaf_fc in model_leaves if ref == member_ref and (not fc or leaf_fc == fc))
        if exact_model:
            return exact_model

        aggregate = tuple(
            ref for ref, leaf_fc in model_leaves if ref.startswith(f"{member_ref}.") and (not fc or leaf_fc == fc)
        )
        if aggregate:
            return aggregate

        # 仅从 ICD 加载时可能没有 IedModel。精确匹配仍然安全，
        # 但不能证明顺序的结构成员绝不猜测展开，交由单点回退。
        exact_registry = tuple(dict.fromkeys(ref for ref in point_refs if ref == member_ref))
        return exact_registry

    def addresses_for_ref(self, ref: str) -> tuple[str, ...]:
        """查找一个规范 MMS 引用对应的全部应用测点地址。"""
        return self.ref_to_addresses.get(ref, ())


class DatasetReadPlanner:
    """处理重叠 DataSet 的纯函数式、确定性贪心规划器。"""

    def __init__(self, catalog: DatasetCatalog):
        """注入只读目录，规划过程不访问网络也不修改缓存。"""
        self._catalog = catalog

    def plan(self, addresses: Sequence[str]) -> DatasetReadPlan:
        """优先选择覆盖未读点最多、成员更少、引用排序更前的 DataSet。"""
        requested = tuple(dict.fromkeys(str(address) for address in addresses))
        remaining = set(requested)
        selected: list[DatasetDescriptor] = []

        candidates = {
            dataset.ref: dataset
            for address in requested
            for dataset in self._catalog.point_to_datasets.get(address, ())
        }
        while remaining and candidates:
            ranked: list[tuple[int, int, str, DatasetDescriptor, set[str]]] = []
            for dataset in candidates.values():
                covered = {
                    address for address in remaining if dataset in self._catalog.point_to_datasets.get(address, ())
                }
                if covered:
                    ranked.append((-len(covered), len(dataset.members), dataset.ref, dataset, covered))
            if not ranked:
                break
            _, _, _, chosen, covered = min(ranked, key=lambda item: item[:3])
            selected.append(chosen)
            remaining.difference_update(covered)
            candidates.pop(chosen.ref, None)

        uncovered = tuple(address for address in requested if address in remaining)
        return DatasetReadPlan(requested=requested, datasets=tuple(selected), uncovered=uncovered)
