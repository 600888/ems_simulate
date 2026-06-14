"""IEC 61850 服务端 DataSet 与 GOOSE 管理

从 iec61850_server.py 的 DataSet/GOOSE 逻辑提取。
"""

import contextlib
from typing import Any

from ...defs.constants import HAS_IEC61850
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class ServerDataSetManager:
    """服务端 DataSet 与 GOOSE 管理器

    职责:
    - 注册 DataSet 到 IedModel
    - 添加 FCDA 条目到 DataSet
    - 添加 GOOSE 控制块
    - 浏览已注册的 DataSet
    - 管理 GoEna 状态
    """

    def __init__(self, builder, model_name: str = "EMS"):
        self._builder = builder
        self.model_name = model_name

        # GOOSE 发布配置
        self._goose_interface: str = "eth0"
        self._goose_publishing_enabled: bool = False
        self._goose_cb_list: list[dict[str, Any]] = []

        # DataSet 信息目录
        self._dataset_catalog: list[dict[str, Any]] = []

        # 模型变更标记
        self._model_changed: bool = False

        # 待注册队列
        self._pending_goose_registrations: list[dict[str, Any]] = []

    @property
    def dataset_catalog(self) -> list[dict[str, Any]]:
        return self._dataset_catalog

    @property
    def goose_cb_list(self) -> list[dict[str, Any]]:
        return self._goose_cb_list

    @property
    def model_changed(self) -> bool:
        return self._model_changed

    @model_changed.setter
    def model_changed(self, value: bool):
        self._model_changed = value

    @property
    def goose_interface(self) -> str:
        return self._goose_interface

    @goose_interface.setter
    def goose_interface(self, value: str):
        self._goose_interface = value

    @property
    def goose_publishing_enabled(self) -> bool:
        return self._goose_publishing_enabled

    @property
    def pending_registrations(self) -> list[dict[str, Any]]:
        return self._pending_goose_registrations

    # ===== DataSet 注册 =====

    def register_dataset(
        self,
        ld_inst: str,
        ds_name: str,
        data_set_ref: str,
        entries: list[dict[str, Any]] | None = None,
        dataset_catalog: list[dict[str, Any]] | None = None,
    ) -> bool:
        """注册 DataSet 并在 MMS 模型中创建真实数据集"""
        if not self._builder.model:
            log.warning(f"register_dataset [{ds_name}]: 模型未初始化")
            return False

        # 检查是否已注册过同名 DataSet（避免重复创建）
        catalog = dataset_catalog if dataset_catalog is not None else self._dataset_catalog
        if any(ds.get("ref") == data_set_ref for ds in catalog):
            log.info(f"register_dataset [{ds_name}]: DataSet 已存在，跳过重复创建 (ref={data_set_ref})")
            return True

        lln0_key = f"{ld_inst}/LLN0"
        lln0 = self._builder.ln_map.get(lln0_key)
        log.info(f"register_dataset [{ds_name}]: 查找 LLN0 key={lln0_key}, found={lln0 is not None}")
        if lln0 is None:
            if ld_inst == self._builder.ld_name:
                self._builder.ensure_base_ld()
                lln0 = self._builder.ln_map.get(lln0_key)
            else:
                self._builder.get_or_create_ld(ld_inst)
                lln0 = self._builder.ln_map.get(lln0_key)
                log.info(f"为 register_dataset 自动创建 LD/LLN0: {ld_inst}")
        if not lln0:
            log.warning(f"无法注册 DataSet: LLN0 未找到 (ld_inst={ld_inst})")
            return False

        try:
            data_set = iec61850.DataSet_create(ds_name, lln0)
            if not data_set:
                log.warning(f"register_dataset [{ds_name}]: DataSet_create 失败")
                return False
            self._builder.keep_alive.append(data_set)
            self._add_fcda_entries_to_dataset(data_set, entries, ld_inst)

            # 构建 catalog 条目
            ds_members = self._build_ds_members(entries)
            ds_ln = ""
            if "$" in data_set_ref:
                ref_ln_part = data_set_ref.split("/")[-1] if "/" in data_set_ref else data_set_ref
                ds_ln = ref_ln_part.split("$")[0]

            catalog_item = {
                "ref": data_set_ref,
                "name": ds_name,
                "ld": ld_inst,
                "ln": ds_ln,
                "member_count": len(ds_members),
                "members": ds_members,
            }
            catalog = dataset_catalog if dataset_catalog is not None else self._dataset_catalog
            catalog.append(catalog_item)
            log.info(f"DataSet 已注册到 MMS 模型: name={ds_name}, ld={ld_inst}, members={len(ds_members)}")
            return True
        except Exception as e:
            log.error(f"注册 DataSet 失败: {e}", exc_info=True)
            return False

    # ===== GOOSE 控制块 =====

    def add_goose_control_block(
        self,
        name: str,
        app_id: int,
        data_set_ref: str,
        conf_rev: int,
        go_id: str = "",
        min_time: int = 10,
        max_time: int = 1000,
        ld_inst: str = None,
        entries: list[dict[str, Any]] | None = None,
        dst_mac: list[int] | None = None,
        vlan_id: int = 0,
        vlan_prio: int = 4,
    ) -> bool:
        """在 LLN0 下创建 GSEControlBlock"""
        if not self._builder.model:
            log.warning("无法添加 GSEControlBlock: 模型未初始化")
            return False

        ld_inst = ld_inst or self._builder.ld_name
        lln0_key = f"{ld_inst}/LLN0"
        lln0 = self._builder.ln_map.get(lln0_key)
        if lln0 is None:
            if ld_inst == self._builder.ld_name:
                self._builder.ensure_base_ld()
                lln0 = self._builder.ln_map.get(lln0_key)
            else:
                self._builder.get_or_create_ld(ld_inst)
                lln0 = self._builder.ln_map.get(lln0_key)
                log.info(f"为 GSEControlBlock 自动创建 LD/LLN0: {ld_inst}")
        if not lln0:
            log.warning(f"无法添加 GSEControlBlock: LLN0 未找到 (ld_inst={ld_inst})")
            return False

        try:
            # 1. 创建 DataSet
            ds_name = data_set_ref.split("$")[-1] if "$" in data_set_ref else f"ds{name}"
            data_set = iec61850.DataSet_create(ds_name, lln0)
            if not data_set:
                log.warning(f"创建 DataSet {ds_name} 失败")
                return False
            self._builder.keep_alive.append(data_set)
            self._add_fcda_entries_to_dataset(data_set, entries, ld_inst)

            # 记录 DataSet 到目录
            ds_members = self._build_ds_members(entries)
            ds_ln = ""
            if "$" in data_set_ref:
                ref_ln_part = data_set_ref.split("/")[-1] if "/" in data_set_ref else data_set_ref
                ds_ln = ref_ln_part.split("$")[0]
            self._dataset_catalog.append(
                {
                    "ref": data_set_ref,
                    "name": ds_name,
                    "ld": ld_inst,
                    "ln": ds_ln,
                    "member_count": len(ds_members),
                    "members": ds_members,
                }
            )

            # 2. 创建 GSEControlBlock
            app_id_str = f"{app_id:04X}" if isinstance(app_id, int) else str(app_id)
            gse_cb = iec61850.GSEControlBlock_create(
                name,
                lln0,
                app_id_str,
                ds_name,
                conf_rev,
                False,
                min_time,
                max_time,
            )
            log.info(f"GSEControlBlock_create: {name}, {app_id_str}, {ds_name}, {conf_rev}")
            if not gse_cb:
                log.warning(f"创建 GSEControlBlock {name} 失败")
                return False
            self._builder.keep_alive.append(gse_cb)
            log.info(f"GSEControlBlock 创建成功: name={name}, app_id=0x{app_id:04X}")

            # 3. 添加 PhyComAddress
            try:
                if dst_mac and len(dst_mac) == 6:
                    phy_addr = iec61850.PhyComAddress_create(vlan_prio, vlan_id, app_id, dst_mac)
                    if phy_addr:
                        iec61850.GSEControlBlock_addPhyComAddress(gse_cb, phy_addr)
                        self._builder.keep_alive.append(phy_addr)
                        log.info(f"GoCB {name} PhyComAddress 已设置: MAC={':'.join(f'{b:02X}' for b in dst_mac)}")
            except Exception as phy_err:
                log.debug(f"添加 PhyComAddress 不可用 (非致命): {phy_err}")

            # 4. 记录 GoCB 信息
            self._goose_cb_list.append({"ld_inst": ld_inst, "name": name, "app_id": app_id})
            log.info(f"GSEControlBlock 已添加: name={name}, app_id=0x{app_id:04X}, entries={len(entries or [])}")
            return True
        except Exception as e:
            log.error(f"添加 GSEControlBlock 失败: {e}", exc_info=True)
            return False

    # ===== FCDA 条目 =====

    def _add_fcda_entries_to_dataset(
        self,
        data_set,
        entries: list[dict[str, Any]] | None,
        default_ld_inst: str,
    ) -> int:
        """向 DataSet 添加 FCDA 条目"""
        if not entries:
            return 0

        da_to_fc = {
            "stVal": "ST",
            "ctlVal": "CO",
            "Oper": "CO",
            "SBOw": "CO",
            "Cancel": "CO",
            "origin": "CO",
            "setVal": "CO",
            "dU": "DC",
            "cmdQual": "CO",
        }
        type_to_fc = {
            "boolean": "ST",
            "float": "MX",
            "integer": "ST",
            "string": "DC",
            "bitstring": "ST",
            "timestamp": "ST",
        }

        added_count = 0
        for idx, entry in enumerate(entries):
            try:
                fcda_ref = entry.get("name", "")
                if not fcda_ref:
                    continue

                if "/" in fcda_ref:
                    slash_idx = fcda_ref.index("/")
                    ld_part = fcda_ref[:slash_idx]
                    rest_part = fcda_ref[slash_idx + 1 :]
                else:
                    ld_part = default_ld_inst
                    rest_part = fcda_ref

                dot_idx = rest_part.find(".")
                if dot_idx > 0:
                    ln_name = rest_part[:dot_idx]
                    do_da_part = rest_part[dot_idx + 1 :]

                    fc = entry.get("fc", "")
                    if not fc:
                        da_name = do_da_part.rsplit(".", 1)[-1] if "." in do_da_part else do_da_part
                        fc = da_to_fc.get(da_name, "")
                    if not fc:
                        fc = type_to_fc.get(entry.get("iec_type", ""), "")
                    if not fc:
                        fc = "MX"

                    self._builder.ensure_fcda_model_nodes(ld_part, ln_name, do_da_part, fc, entry.get("iec_type", ""))

                    do_da_mms = do_da_part.replace(".", "$")
                    variable_ref = f"{ld_part}/{ln_name}${fc}${do_da_mms}"
                else:
                    continue

                try:
                    ds_entry = iec61850.DataSetEntry_create(data_set, variable_ref, idx, None)
                    if ds_entry:
                        self._builder.keep_alive.append(ds_entry)
                        added_count += 1
                except Exception as create_err:
                    log.warning(f"DataSetEntry_create 失败: {variable_ref}, error={create_err}")
            except Exception as e:
                log.warning(f"添加 FCDA 条目异常 (fcda_ref={entry.get('name', '')}): {e}")

        if added_count > 0:
            log.info(f"DataSet 已添加 {added_count}/{len(entries)} 个 FCDA 条目")
        elif entries:
            log.warning(
                f"DataSet 未添加任何 FCDA 条目 (共 {len(entries)} 个)，DataSet 将为空，关联的 GoCB/RCB 无数据可发布"
            )
        return added_count

    def _build_ds_members(self, entries: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """从 entries 列表构建成员信息"""
        ds_members = []
        if not entries:
            return ds_members
        entry_to_fc_map = {
            "stVal": "ST",
            "ctlVal": "CO",
            "mag.f": "MX",
            "mag": "MX",
            "f": "MX",
            "q": "MX",
            "t": "MX",
            "dU": "DC",
            "setVal": "CO",
        }
        type_to_fc_map = {
            "boolean": "ST",
            "float": "MX",
            "integer": "ST",
            "string": "DC",
        }
        for entry in entries:
            entry_ref = entry.get("name", "")
            entry_iec_type = entry.get("iec_type", "")
            entry_fc = type_to_fc_map.get(entry_iec_type, "")
            if not entry_fc and "/" in entry_ref:
                da_part = entry_ref.rsplit(".", 1)[-1] if "." in entry_ref else ""
                entry_fc = entry_to_fc_map.get(da_part, "MX")
            ds_members.append({"ref": entry_ref, "fc": entry_fc or "MX", "iec_type": entry_iec_type})
        return ds_members

    # ===== 浏览 =====

    def browse_datasets(self) -> list[dict[str, Any]]:
        """返回服务器上所有已注册的数据集目录"""
        return list(self._dataset_catalog)

    # ===== 待注册处理 =====

    def apply_pending_registrations(self, add_goose_cb_func, register_dataset_func) -> None:
        """处理待注册的 GoCB/DataSet 队列"""
        if not self._pending_goose_registrations:
            return
        applied = 0
        for item in self._pending_goose_registrations:
            reg_type = item.get("_type", "")
            try:
                if reg_type == "gocb":
                    add_goose_cb_func(
                        name=item.get("name", ""),
                        app_id=item.get("app_id", 0x0001),
                        data_set_ref=item.get("data_set_ref", ""),
                        conf_rev=item.get("conf_rev", 1),
                        go_id=item.get("go_id", ""),
                        min_time=item.get("min_time", 10),
                        max_time=item.get("max_time", 1000),
                        ld_inst=item.get("ld_inst"),
                        entries=item.get("entries"),
                        dst_mac=item.get("dst_mac"),
                        vlan_id=item.get("vlan_id", 0),
                        vlan_prio=item.get("vlan_prio", 4),
                    )
                    applied += 1
                elif reg_type == "dataset":
                    register_dataset_func(
                        ld_inst=item.get("ld_inst", ""),
                        ds_name=item.get("ds_name", ""),
                        data_set_ref=item.get("data_set_ref", ""),
                        entries=item.get("entries"),
                    )
                    applied += 1
            except Exception as e:
                log.warning(f"处理待注册 {reg_type} 失败: {e}")
        self._pending_goose_registrations.clear()
        if applied > 0:
            log.info(f"已处理 {applied} 个待注册 GoCB/DataSet 配置")

    # ===== GoEna 管理 =====

    def enable_single_goose_cb(
        self,
        server,
        port: int,
        model_name: str,
        ld_inst: str,
        cb_name: str,
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ):
        """设置单个 GoCB 的 GoEna=TRUE"""
        if not server:
            return
        ref = f"{model_name}{ld_inst}/LLN0.{cb_name}.GoEna"
        for attempt in range(1, max_retries + 1):
            conn = None
            try:
                conn = iec61850.IedConnection_create()
                result = iec61850.IedConnection_connect(conn, "127.0.0.1", port)
                error = result if not isinstance(result, (list, tuple)) else result[1]
                if error != 0:
                    if attempt < max_retries:
                        import time as _time

                        _time.sleep(retry_delay)
                        continue
                    log.warning(f"设置 GoCB GoEna 时无法连接 (已重试{max_retries}次)")
                    return
                iec61850.IedConnection_writeBooleanValue(conn, ref, iec61850.IEC61850_FC_GO, True)
                log.info(f"GoCB GoEna 已设为 TRUE: ld={ld_inst}, cb={cb_name}")
                return
            except Exception as e:
                if attempt < max_retries:
                    import time as _time

                    _time.sleep(retry_delay)
                    continue
                log.warning(f"设置 GoCB GoEna 失败 (ld={ld_inst}, cb={cb_name}): {e}")
            finally:
                if conn:
                    with contextlib.suppress(Exception):
                        iec61850.IedConnection_destroy(conn)

    def enable_all_goose_cbs(self, server, port: int, model_name: str):
        """设置所有已注册 GoCB 的 GoEna=TRUE"""
        for cb_info in self._goose_cb_list:
            self.enable_single_goose_cb(server, port, model_name, cb_info["ld_inst"], cb_info["name"])
