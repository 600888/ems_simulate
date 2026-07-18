"""IEC 61850 测点注册表

管理地址 -> MMS 引用路径、FC、iec_type 的映射缓存。
从 iec61850_client.py 的 _point_refs/_point_fc/_point_iec_type 提取。
"""

from ..defs.address import (
    infer_fc_from_address,
    infer_iec_type_from_address,
    is_full_ref,
    parse_ref,
)
from ..defs.constants import (
    IEC_TYPE_BOOLEAN,
    IEC_TYPE_FLOAT,
    IEC_TYPE_UNKNOWN,
)
from ..defs.mms_types import mms_type_from_iec_type
from ..log import log


class PointRegistry:
    """测点注册表

    管理测点地址到 MMS 引用、FC、iec_type 的映射关系。
    """

    def __init__(self, model_name: str = "EMS", ld_name: str = "GenericLD"):
        """创建测点引用、功能约束、IEC/MMS 类型和已发现数据集的线程安全索引。"""
        self.model_name = model_name
        self.ld_name = ld_name

        # 地址 -> MMS 引用路径的映射
        self._point_refs: dict[str, str] = {}
        # 地址 -> FC 的映射
        self._point_fc: dict[str, str] = {}
        # 地址 -> iec_type 的映射
        self._point_iec_type: dict[str, str] = {}
        # 地址 -> 原生 MMS 类型的映射
        self._point_mms_type: dict[str, str] = {}
        # 地址 -> 描述 (dU) 的映射
        self._point_name: dict[str, str] = {}
        # 发现的 GOOSE 控制块列表
        self._discovered_goose_items: list = []
        # 发现的 DataSet 列表
        self._discovered_datasets: list = []

    def add_point(self, address, frame_type: int = 0, fc: str = "") -> str:
        """注册测点

        Args:
            address: 测点地址 (简单地址或完整引用路径)
            frame_type: 帧类型 (0=遥测, 1=遥信, 2=遥控, 3=遥调)
            fc: 功能约束 (为空时自动推断)

        Returns:
            MMS 引用路径
        """
        addr_str = str(address)
        if addr_str in self._point_refs:
            return self._point_refs[addr_str]  # 已存在, 不重复添加

        # 推断 FC
        if not fc:
            fc = infer_fc_from_address(addr_str)
            # 简单地址模式：按 frame_type 推断
            if not fc and not is_full_ref(addr_str):
                fc_map = {0: "MX", 1: "ST", 2: "CO", 3: "CO"}
                fc = fc_map.get(frame_type, "MX")
        self._point_fc[addr_str] = fc

        # 推断 iec_type
        iec_type = infer_iec_type_from_address(addr_str)
        if iec_type == IEC_TYPE_UNKNOWN and not is_full_ref(addr_str):
            # 简单地址模式：按 frame_type 推断
            iec_type = IEC_TYPE_FLOAT if frame_type == 0 or frame_type == 3 else IEC_TYPE_BOOLEAN
        self._point_iec_type[addr_str] = iec_type
        self._point_mms_type[addr_str] = mms_type_from_iec_type(iec_type).value

        # 构建并存储 MMS 引用路径
        self._point_refs[addr_str] = self._build_ref(addr_str)
        return self._point_refs[addr_str]

    def get_ref(self, address) -> str | None:
        """获取测点的 MMS 引用路径"""
        return self._point_refs.get(str(address))

    def get_fc(self, address) -> str:
        """获取测点的 FC"""
        return self._point_fc.get(str(address), "")

    def get_iec_type(self, address) -> str:
        """获取测点的 iec_type"""
        return self._point_iec_type.get(str(address), "")

    def get_mms_type(self, address) -> str:
        """获取测点的原生 MMS 类型。"""
        return self._point_mms_type.get(str(address), "")

    def get_name(self, address) -> str:
        """获取测点的描述 (dU)"""
        return self._point_name.get(str(address), "")

    def has_point(self, address) -> bool:
        """判断测点是否已注册"""
        return str(address) in self._point_refs

    @property
    def point_refs(self) -> dict[str, str]:
        """所有已注册的地址 -> 引用映射"""
        return self._point_refs

    @property
    def point_fc(self) -> dict[str, str]:
        """所有已注册的地址 -> FC 映射"""
        return self._point_fc

    @property
    def point_iec_type(self) -> dict[str, str]:
        """所有已注册的地址 -> iec_type 映射"""
        return self._point_iec_type

    @property
    def point_mms_type(self) -> dict[str, str]:
        """返回测点注册表当前的测点MMS 类型类型。"""
        return self._point_mms_type

    def set_ref(self, address: str, ref: str) -> None:
        """直接设置地址的 MMS 引用路径"""
        self._point_refs[str(address)] = ref

    def set_fc(self, address: str, fc: str) -> None:
        """直接设置地址的 FC"""
        self._point_fc[str(address)] = fc

    def set_iec_type(self, address: str, iec_type: str) -> None:
        """直接设置地址的 iec_type"""
        self._point_iec_type[str(address)] = iec_type

    def set_mms_type(self, address: str, mms_type: str) -> None:
        """设置MMS 类型类型。"""
        self._point_mms_type[str(address)] = str(mms_type)

    def set_name(self, address: str, name: str) -> None:
        """直接设置地址的描述 (dU)"""
        self._point_name[str(address)] = name

    def clear(self) -> None:
        """清空当前模型派生的所有测点与结构缓存。

        远程重新发现和 ICD 重新加载都是“替换模型”操作。如果只覆盖
        同名 key，上一个模型已删除的测点会永久残留在内存中。
        """
        self._point_refs.clear()
        self._point_fc.clear()
        self._point_iec_type.clear()
        self._point_mms_type.clear()
        self._point_name.clear()
        self._discovered_goose_items.clear()
        self._discovered_datasets.clear()

    @property
    def discovered_goose_items(self) -> list:
        """发现的 GOOSE 控制块列表"""
        return self._discovered_goose_items

    @property
    def discovered_datasets(self) -> list:
        """发现的 DataSet 列表"""
        return self._discovered_datasets

    @discovered_datasets.setter
    def discovered_datasets(self, value: list):
        """更新测点注册表的已发现的数据集，使后续操作使用新值。"""
        self._discovered_datasets = value

    def _build_ref(self, address) -> str:
        """根据地址构建 MMS 引用路径

        对于完整引用路径 (含 '/'): 拼接 model_name 前缀构建完整 MMS 引用
        对于简单地址: 使用 MMXU1/GGIO1/GGIO2 固定结构
        """
        addr_str = str(address)

        if is_full_ref(addr_str):
            parsed = parse_ref(addr_str)
            if parsed:
                ld_inst = parsed[0]
                rest = addr_str.split("/", 1)[1]
                return f"{self.model_name}{ld_inst}/{rest}"
            log.warning(f"无法解析引用路径 {addr_str}，回退到简单模式")

        # 简单地址模式
        safe_addr = addr_str.replace(".", "_").replace("/", "_").replace("\\", "_").replace("-", "_")

        iec_type = self._point_iec_type.get(addr_str, "")
        if iec_type == IEC_TYPE_FLOAT:
            return f"{self.model_name}{self.ld_name}/MMXU1.MV_{safe_addr}.mag.f"
        else:
            return f"{self.model_name}{self.ld_name}/GGIO1.SPS_{safe_addr}.stVal"
