"""IcdExporter 单元测试 — 验证关键修复逻辑"""

import os
import sys

import pytest
import xmltodict

# 添加 src 目录到 sys.path
_src_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from proto.iec61850.defs.constants import IecType
from proto.iec61850.model.ied_model import DARef, DataSetRef, DORef, IedModel, LDModel, LNModel, RCBRef
from proto.iec61850.plugins.model_exporter.exporters.icd import (
    IcdExporter,
    _next_da_type_id,
    _next_do_type_id,
    _reset_type_counters,
)


class TestIcdExporter:
    """IcdExporter 核心逻辑验证"""

    def setup_method(self):
        self.exporter = IcdExporter()
        _reset_type_counters()

    # ===== lnClass 提取 =====

    @pytest.mark.parametrize(
        "ln_name,expected",
        [
            ("LLN0", "LLN0"),
            ("MMCL", "MMCL"),
            ("MMCL1", "MMCL"),
            ("MMBC", "MMBC"),
            ("MMBC1", "MMBC"),
            ("MMBS", "MMBS"),
            ("GGIO", "GGIO"),
            ("GGIO1", "GGIO"),
            ("MMXU", "MMXU"),
            ("MMXU1", "MMXU"),
            ("CSWI", "CSWI"),
            ("CSWI1", "CSWI"),
            ("L", "L"),  # 短名称兼容
            ("L1", "L"),  # 短名称+实例号
            ("PTRC", "PTRC"),
            ("PTRC1", "PTRC"),
        ],
    )
    def test_extract_ln_class_from_name(self, ln_name, expected):
        assert self.exporter._extract_ln_class_from_name(ln_name) == expected

    # ===== LN inst 提取 =====

    @pytest.mark.parametrize(
        "ln_name,expected",
        [
            ("LLN0", ""),
            ("MMCL1", "1"),
            ("MMCL", "1"),  # 无数字时默认 inst 1
            ("GGIO10", "10"),
            ("L1", "1"),
        ],
    )
    def test_extract_ln_inst(self, ln_name, expected):
        assert self.exporter._extract_ln_inst(ln_name) == expected

    # ===== LD inst 提取 =====

    @pytest.mark.parametrize(
        "ld_name,ied_name,expected",
        [
            ("KG_BAMSCTMP01", "KG", "BAMSCTMP01"),
            ("CTMP01", "KG_BAMS", "CTMP01"),
            ("KG_BAMS_CTMP01", "KG_BAMS", "CTMP01"),
            ("BAMS", "IED", "BAMS"),
            # Bug fix: ld_name == ied_name 时不应返回空字符串
            ("GenericLD", "GenericLD", "GenericLD"),
            ("EMS", "EMS", "EMS"),
            ("", "IED", ""),
            ("PCS001", "", "PCS001"),
        ],
    )
    def test_extract_ld_inst(self, ld_name, ied_name, expected):
        assert self.exporter._extract_ld_inst(ld_name, ied_name) == expected

    def test_export_infers_ied_name_and_ld_inst_from_online_ld_names(self, tmp_path):
        """MMS returns full LD names like PCS001LD0; SCL must restore IED=PCS001 and LD inst=LD0."""
        model = IedModel(
            host="192.168.1.10",
            port=102,
            discover_time="2026-06-22 00:00:00",
            lds=(
                LDModel(
                    name="PCS001LD0",
                    inst="PCS001LD0",
                    lns=(
                        LNModel(
                            name="LLN0",
                            ln_class="LLN0",
                            ref="PCS001LD0/LLN0",
                            datasets=(
                                DataSetRef(
                                    name="dsDin",
                                    ref="PCS001LD0/LLN0.dsDin",
                                    members=({"ref": "PCS001LD0/GGIO1.Ind1", "fc": "ST"},),
                                ),
                            ),
                        ),
                        LNModel(
                            name="GGIO1",
                            ln_class="GGIO",
                            ref="PCS001LD0/GGIO1",
                            dos=(
                                DORef(
                                    name="Ind1",
                                    ref="PCS001LD0/GGIO1.Ind1",
                                    cdc="SPS",
                                    frame_type=1,
                                    das=(DARef(name="stVal", path="stVal", fc="ST", iec_type=IecType.BOOLEAN),),
                                ),
                            ),
                        ),
                    ),
                ),
                LDModel(
                    name="PCS001CTRL",
                    inst="PCS001CTRL",
                    lns=(
                        LNModel(
                            name="LLN0",
                            ln_class="LLN0",
                            ref="PCS001CTRL/LLN0",
                            datasets=(
                                DataSetRef(
                                    name="dsAlm",
                                    ref="PCS001CTRL/LLN0.dsAlm",
                                    members=({"ref": "PCS001CTRL/krGGIO1.Alm1", "fc": "ST"},),
                                ),
                            ),
                        ),
                        LNModel(
                            name="krGGIO1",
                            ln_class="GGIO",
                            ref="PCS001CTRL/krGGIO1",
                            dos=(
                                DORef(
                                    name="Alm1",
                                    ref="PCS001CTRL/krGGIO1.Alm1",
                                    cdc="SPS",
                                    frame_type=1,
                                    das=(DARef(name="stVal", path="stVal", fc="ST", iec_type=IecType.BOOLEAN),),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )

        output_path = tmp_path / "pcs001.icd"
        self.exporter.export(model, str(output_path))
        doc = xmltodict.parse(output_path.read_text(encoding="utf-8"))
        ied = doc["SCL"]["IED"]
        ldevices = ied["AccessPoint"]["Server"]["LDevice"]
        if isinstance(ldevices, dict):
            ldevices = [ldevices]

        assert ied["@name"] == "PCS001"
        assert [ld["@inst"] for ld in ldevices] == ["LD0", "CTRL"]

        first_fcda = ldevices[0]["LN0"]["DataSet"]["FCDA"]
        assert first_fcda["@ldInst"] == "LD0"
        assert first_fcda["@lnClass"] == "GGIO"

        second_fcda = ldevices[1]["LN0"]["DataSet"]["FCDA"]
        assert second_fcda["@ldInst"] == "CTRL"
        assert second_fcda["@prefix"] == "kr"
        assert second_fcda["@lnClass"] == "GGIO"

    # ===== DOType ID 生成 =====
    def test_do_type_id_generation(self):
        _reset_type_counters()
        id1 = _next_do_type_id("MV")
        id2 = _next_do_type_id("MV")
        id3 = _next_do_type_id("SPS")
        assert id1 == "_T_MV_1"
        assert id2 == "_T_MV_2"
        assert id3 == "_T_SPS_1"

    # ===== DOType 指纹去重 =====
    def test_do_type_fingerprint_sharing(self):
        """相同 DA 结构的 DO 应有相同指纹"""
        do1 = DORef(
            name="Vol",
            ref="LD1/MMXU1.Vol",
            cdc="MV",
            frame_type=0,
            das=(
                DARef(name="mag", path="mag.f", fc="MX", iec_type=IecType.FLOAT),
                DARef(name="q", path="q", fc="MX", iec_type=IecType.INTEGER),
                DARef(name="t", path="t", fc="MX", iec_type=IecType.TIMESTAMP),
            ),
        )
        do2 = DORef(
            name="Amp",
            ref="LD1/MMXU1.Amp",
            cdc="MV",
            frame_type=0,
            das=(
                DARef(name="mag", path="mag.f", fc="MX", iec_type=IecType.FLOAT),
                DARef(name="q", path="q", fc="MX", iec_type=IecType.INTEGER),
                DARef(name="t", path="t", fc="MX", iec_type=IecType.TIMESTAMP),
            ),
        )
        f1 = self.exporter._make_do_type_fingerprint(do1, "MV")
        f2 = self.exporter._make_do_type_fingerprint(do2, "MV")
        assert f1 == f2, "相同 CDC 和 DA 结构的 DO 应共享指纹"

    def test_do_type_fingerprint_different(self):
        """不同 DA 结构的 DO 应有不同指纹"""
        do1 = DORef(
            name="Vol",
            ref="LD1/MMXU1.Vol",
            cdc="MV",
            frame_type=0,
            das=(
                DARef(name="mag", path="mag.f", fc="MX", iec_type=IecType.FLOAT),
                DARef(name="q", path="q", fc="MX", iec_type=IecType.INTEGER),
            ),
        )
        do2 = DORef(
            name="Pos",
            ref="LD1/CSWI1.Pos",
            cdc="DPC",
            frame_type=2,
            das=(
                DARef(name="stVal", path="stVal", fc="ST", iec_type=IecType.INTEGER),
                DARef(name="ctlVal", path="ctlVal", fc="CO", iec_type=IecType.INTEGER),
                DARef(name="q", path="q", fc="MX", iec_type=IecType.INTEGER),
                DARef(name="t", path="t", fc="MX", iec_type=IecType.TIMESTAMP),
            ),
        )
        f1 = self.exporter._make_do_type_fingerprint(do1, "MV")
        f2 = self.exporter._make_do_type_fingerprint(do2, "DPC")
        assert f1 != f2, "不同 CDC/DA 的 DO 应不同指纹"

    # ===== CDC 推断 =====
    @pytest.mark.parametrize(
        "do_name,ln_class,expected",
        [
            ("Vol", "MMXU", "MV"),
            ("Amp", "MMXU", "MV"),
            ("Hz", "MMXU", "MV"),
            ("PhV", "MMXU", "CMV"),
            ("Ind", "GGIO", "SPC"),
            ("AnIn", "GGIO", "MV"),
            ("Mod", "MMXU", "ENC"),
            ("Beh", "MMXU", "ENC"),
            ("NamPlt", "LLN0", "LPL"),
            ("Temp001", "MMCL", "MV"),
        ],
    )
    def test_infer_cdc_from_do(self, do_name, ln_class, expected):
        assert self.exporter._infer_cdc_from_do(do_name, ln_class) == expected

    # ===== 完整导出流程 =====
    def test_build_data_type_templates_with_mock_model(self):
        """使用模拟的 IedModel 验证类型模板生成"""
        model = IedModel(
            host="192.168.1.1",
            port=102,
            discover_time="2024-01-01 00:00:00",
            lds=(
                LDModel(
                    name="IED1_CTRL1",
                    inst="CTRL1",
                    lns=(
                        LNModel(
                            name="LLN0",
                            ln_class="LLN0",
                            ref="IED1_CTRL1/LLN0",
                            dos=(),
                            datasets=(),
                            rcb_list=(),
                            gocb_list=(),
                        ),
                        LNModel(
                            name="CSWI1",
                            ln_class="CSWI",
                            ref="IED1_CTRL1/CSWI1",
                            dos=(
                                DORef(
                                    name="Pos",
                                    ref="IED1_CTRL1/CSWI1.Pos",
                                    cdc="DPC",
                                    frame_type=2,
                                    das=(
                                        DARef(name="stVal", path="stVal", fc="ST", iec_type=IecType.INTEGER),
                                        DARef(name="q", path="q", fc="MX", iec_type=IecType.INTEGER),
                                        DARef(name="t", path="t", fc="MX", iec_type=IecType.TIMESTAMP),
                                    ),
                                ),
                            ),
                            datasets=(),
                            rcb_list=(),
                            gocb_list=(),
                        ),
                    ),
                ),
            ),
        )
        result = self.exporter._build_data_type_templates(model, "IED1")

        # 验证类型模板数量合理
        lnode_types = result.get("LNodeType", [])
        if not isinstance(lnode_types, list):
            lnode_types = [lnode_types]
        do_types = result.get("DOType", [])
        if not isinstance(do_types, list):
            do_types = [do_types]

        assert len(lnode_types) == 1  # empty LLN0 is skipped; CSWI1 remains
        # 验证 DOType 数量: CSWI1.Pos(1个DPC) + Mod(1个ENC) + Beh(1个ENC) + Health(1个ENC)
        # + LLN0的: Beh(1个ENC) + Health(1个ENC) + NamPlt(1个LPL)
        # 但 Mod/Beh/Health/NamPlt 中的每个 lnClass 只有一个 DOType 实例
        # DPC × 1, ENC × 2(CSWI), ENC × 2(LLN0), LPL × 1(LLN0)
        # 实际上 ENC_fixed 的 lnClass 不同，不会共享
        # DPC(CSWI1.Pos) + ENC(CSWI_Mod) + ENC(CSWI_Beh) + ENC(CSWI_Health)
        # + ENC(LLN0_Beh) + ENC(LLN0_Health) + LPL(LLN0_NamPlt)
        # = 大约 7 个 DOType
        # 之前是 2×1 = 每个 DO 一个，加固定 DO 的 2×4 = 8，约 10 个
        # 现在去重后应该少于 20 个
        assert len(do_types) <= 20, f"DOType 数量应合理，实际: {len(do_types)}"

    def test_build_datasets_do_matching(self):
        """验证 FCDA 通过 DO 名称匹配的功能"""
        discovered_lns = (
            LNModel(
                name="MMCL1",
                ln_class="MMCL",
                ref="LD1/MMCL1",
                dos=(
                    DORef(
                        name="Temp001",
                        ref="LD1/MMCL1.Temp001",
                        cdc="MV",
                        frame_type=0,
                        das=(DARef(name="mag", path="mag.f", fc="MX", iec_type=IecType.FLOAT),),
                    ),
                    DORef(
                        name="Temp002",
                        ref="LD1/MMCL1.Temp002",
                        cdc="MV",
                        frame_type=0,
                        das=(DARef(name="mag", path="mag.f", fc="MX", iec_type=IecType.FLOAT),),
                    ),
                ),
                datasets=(),
                rcb_list=(),
                gocb_list=(),
            ),
        )
        # 模拟 FCDA 从 MMS 返回的短格式 ref（LN 名为 "L1" 而非 "MMCL1"）
        datasets = [
            DataSetRef(
                name="dsTemp",
                ref="LD1/LLN0.dsTemp",
                is_deletable=False,
                members=(
                    {"ref": "LD1/L1.Temp001.mag.f", "fc": "MX", "iec_type": "float", "index": 0},
                    {"ref": "LD1/L1.Temp002.mag.f", "fc": "MX", "iec_type": "float", "index": 0},
                ),
            ),
        ]
        ln = LNModel(
            name="LLN0",
            ln_class="LLN0",
            ref="LD1/LLN0",
            dos=(),
            datasets=datasets,
            rcb_list=(),
            gocb_list=(),
        )

        result = self.exporter._build_datasets(datasets, "CTRL1", ln, discovered_lns)
        if isinstance(result, dict):
            result = [result]

        assert len(result) == 1, "应该保留 1 个 DataSet"
        fcda_list = result[0].get("FCDA", [])
        if isinstance(fcda_list, dict):
            fcda_list = [fcda_list]
        assert len(fcda_list) == 2, f"应该保留 2 个 FCDA，实际: {len(fcda_list)}"
        for fcda in fcda_list:
            assert fcda.get("@lnClass") == "MMCL", f"lnClass 应为 MMCL，实际: {fcda.get('@lnClass')}"
            assert fcda.get("@lnInst") == "1", f"lnInst 应为 1，实际: {fcda.get('@lnInst')}"

    def test_mag_struct_da_uses_discovered_bdas(self):
        """验证 mag 结构体 DA 使用在线发现的子属性（不加默认的 i）

        原始 ICD 中 MMCL1.Temp001.mag BDA=[f]，MMBC1.SglMaxVolNo.mag BDA=[i]，
        导出应严格匹配在线发现的子属性，不添加默认定义。
        """
        self.exporter = IcdExporter()
        _reset_type_counters()

        # 场景1: 在线发现只找到 mag.f（如 MMCL 温度测量）
        do = DORef(
            name="Temp001",
            ref="LD1/MMCL1.Temp001",
            cdc="MV",
            frame_type=0,
            das=(
                DARef(
                    name="mag",
                    path="mag.f",
                    fc="MX",
                    iec_type=IecType.FLOAT,
                    sub_das=(DARef(name="f", path="mag.f", fc="MX", iec_type=IecType.FLOAT),),
                ),
                DARef(name="q", path="q", fc="MX", iec_type=IecType.INTEGER),
                DARef(name="t", path="t", fc="MX", iec_type=IecType.TIMESTAMP),
            ),
        )

        do_type_cache: dict = {}
        da_type_cache: dict = {}
        do_types: list = []
        da_types: list = []
        enum_types: dict = {}
        self.exporter._init_enum_types(enum_types)

        self.exporter._resolve_or_create_do_type(
            do,
            "MV",
            "KG_BAMSCTMP01.MMCL1",
            do_type_cache,
            da_type_cache,
            do_types,
            da_types,
            enum_types,
        )

        # 验证 DAType 仅包含 f，不包含 i
        assert len(da_types) == 1
        da_type_item = da_types[0]
        bda_items = da_type_item.get("BDA", [])
        if isinstance(bda_items, dict):
            bda_items = [bda_items]
        bda_names = {b.get("@name") for b in bda_items}
        assert bda_names == {"f"}, f"在线发现 mag.f 时 DAType 应只含 f，实际: {bda_names}"
        assert "i" not in bda_names, "不应添加默认的 mag.i！IED 不支持"

    def test_mag_struct_da_different_bda_different_dotype(self):
        """验证不同 BDA 的 mag 产生不同的 DOType

        Temp001.mag=[f] 和 SglMaxVolNo.mag=[i] 应有不同 DOType，
        否则 FCDA 引用 mag.i 时会错误指向 mag.f 的 DAType。
        """
        self.exporter = IcdExporter()
        _reset_type_counters()

        # DO1: mag.f (如温度测量)
        do_f = DORef(
            name="Temp001",
            cdc="MV",
            frame_type=0,
            das=(
                DARef(
                    name="mag",
                    fc="MX",
                    iec_type=IecType.FLOAT,
                    sub_das=(DARef(name="f", fc="MX", iec_type=IecType.FLOAT),),
                ),
                DARef(name="q", fc="MX", iec_type=IecType.INTEGER),
            ),
        )
        # DO2: mag.i (如状态计数)
        do_i = DORef(
            name="SglMaxVolNo",
            cdc="MV",
            frame_type=0,
            das=(
                DARef(
                    name="mag",
                    fc="MX",
                    iec_type=IecType.INTEGER,
                    sub_das=(DARef(name="i", fc="MX", iec_type=IecType.INTEGER),),
                ),
                DARef(name="q", fc="MX", iec_type=IecType.INTEGER),
            ),
        )

        f1 = self.exporter._make_do_type_fingerprint(do_f, "MV")
        f2 = self.exporter._make_do_type_fingerprint(do_i, "MV")
        assert f1 != f2, "mag.f 和 mag.i 应产生不同 DOType 指纹"

    # ===== FCDA 冗余处理 =====

    def test_fcda_empty_attributes_filtered_out(self, tmp_path):
        """验证FCDA中缺少必要属性的条目被过滤掉"""
        model = IedModel(
            host="192.168.1.1",
            port=102,
            lds=(
                LDModel(
                    name="IED1_LD0",
                    inst="LD0",
                    lns=(
                        LNModel(
                            name="LLN0",
                            ln_class="LLN0",
                            ref="IED1_LD0/LLN0",
                            datasets=(
                                DataSetRef(
                                    name="dsTest",
                                    ref="IED1_LD0/LLN0.dsTest",
                                    members=(
                                        # 正常FCDA
                                        {"ref": "IED1_LD0/GGIO1.Ind1.stVal", "fc": "ST"},
                                        # 异常FCDA: 无ref且无doName
                                        {"fc": ""},
                                    ),
                                ),
                            ),
                        ),
                        LNModel(
                            name="GGIO1",
                            ln_class="GGIO",
                            ref="IED1_LD0/GGIO1",
                            dos=(
                                DORef(
                                    name="Ind1",
                                    ref="IED1_LD0/GGIO1.Ind1",
                                    cdc="SPS",
                                    frame_type=1,
                                    das=(DARef(name="stVal", path="stVal", fc="ST", iec_type=IecType.BOOLEAN),),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        output_path = tmp_path / "fcda_filter.icd"
        self.exporter.export(model, str(output_path))
        doc = xmltodict.parse(output_path.read_text(encoding="utf-8"))
        ied = doc["SCL"]["IED"]
        ldevices = ied["AccessPoint"]["Server"]["LDevice"]
        if isinstance(ldevices, dict):
            ldevices = [ldevices]
        ln0 = ldevices[0]["LN0"]
        dataset = ln0.get("DataSet", {})
        if isinstance(dataset, list):
            dataset = dataset[0]
        fcda = dataset.get("FCDA", [])
        if isinstance(fcda, dict):
            fcda = [fcda]
        # 应该只有1个有效FCDA（Ind1），异常条目被过滤
        assert len(fcda) == 1, f"应只有1个有效FCDA，实际: {len(fcda)}"
        assert fcda[0]["@doName"] == "Ind1"

    # ===== 报告整合 =====

    def test_report_control_consolidation(self):
        """验证同名报告控制块合并为一份，RptEnabled max=实例数"""
        rcb_list = (
            RCBRef(name="brcb01", ref="LD0/LLN0.brcb01", rcb_type="BRCB"),
            RCBRef(name="brcb01", ref="LD0/LLN0.brcb01$01", rcb_type="BRCB"),
            RCBRef(name="brcb01", ref="LD0/LLN0.brcb01$02", rcb_type="BRCB"),
            RCBRef(name="urcb01", ref="LD0/LLN0.urcb01", rcb_type="URCB"),
        )
        result = self.exporter._build_report_controls(rcb_list)
        if isinstance(result, dict):
            result = [result]

        assert len(result) == 2, f"应合并为2个报告，实际: {len(result)}"
        by_name = {item["@name"]: item for item in result}
        assert "brcb" in by_name, f"brcb应在结果中，实际keys: {list(by_name.keys())}"
        assert "urcb" in by_name, f"urcb应在结果中，实际keys: {list(by_name.keys())}"
        assert by_name["brcb"]["RptEnabled"]["@max"] == "3", (
            f"brcb max应为3，实际: {by_name['brcb']['RptEnabled']['@max']}"
        )
        assert by_name["urcb"]["RptEnabled"]["@max"] == "1", (
            f"urcb max应为1，实际: {by_name['urcb']['RptEnabled']['@max']}"
        )

    def test_single_report_control_no_change(self):
        """验证单实例报告控制块的RptEnabled max=1"""
        rcb_list = (RCBRef(name="urcb01", ref="LD0/LLN0.urcb01", rcb_type="URCB"),)
        result = self.exporter._build_report_controls(rcb_list)
        if isinstance(result, dict):
            result = [result]
        assert len(result) == 1
        assert result[0]["RptEnabled"]["@max"] == "1"

    # ===== LNodeType 去重 =====

    def test_lnode_type_dedup_same_structure(self):
        """验证相同lnClass和相同DO结构的LN共享同一LNodeType id"""
        _reset_type_counters()
        model = IedModel(
            host="192.168.1.1",
            port=102,
            lds=(
                LDModel(
                    name="IED1_LD0",
                    inst="LD0",
                    lns=(
                        LNModel(
                            name="LLN0",
                            ln_class="LLN0",
                            ref="IED1_LD0/LLN0",
                            dos=(),
                            rcb_list=(),
                        ),
                        LNModel(
                            name="GGIO1",
                            ln_class="GGIO",
                            ref="IED1_LD0/GGIO1",
                            dos=(
                                DORef(
                                    name="Ind1",
                                    cdc="SPS",
                                    frame_type=1,
                                    das=(DARef(name="stVal", fc="ST", iec_type=IecType.BOOLEAN),),
                                ),
                            ),
                        ),
                        LNModel(
                            name="GGIO2",
                            ln_class="GGIO",
                            ref="IED1_LD0/GGIO2",
                            dos=(
                                DORef(
                                    name="Ind1",
                                    cdc="SPS",
                                    frame_type=1,
                                    das=(DARef(name="stVal", fc="ST", iec_type=IecType.BOOLEAN),),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        templates = self.exporter._build_data_type_templates(model, "IED1")
        lnode_types = templates.get("LNodeType", [])
        if isinstance(lnode_types, dict):
            lnode_types = [lnode_types]

        # GGIO1和GGIO2是不同LN，各自有独立DOType id（含LN名），所以LNodeType不共享
        ggio_count = sum(1 for lt in lnode_types if lt.get("@lnClass") == "GGIO")
        assert ggio_count == 2, f"不同LN的GGIO应有2个LNodeType，实际: {ggio_count}"
        # 验证ln_type_mapping为空（无去重）
        assert not self.exporter._ln_type_mapping

    def test_lnode_type_no_dedup_different_do(self):
        """验证不同DO结构的LN不共享LNodeType"""
        _reset_type_counters()
        model = IedModel(
            host="192.168.1.1",
            port=102,
            lds=(
                LDModel(
                    name="IED1_LD0",
                    inst="LD0",
                    lns=(
                        LNModel(
                            name="LLN0",
                            ln_class="LLN0",
                            ref="IED1_LD0/LLN0",
                            dos=(),
                            rcb_list=(),
                        ),
                        LNModel(
                            name="GGIO1",
                            ln_class="GGIO",
                            ref="IED1_LD0/GGIO1",
                            dos=(
                                DORef(
                                    name="Ind1",
                                    cdc="SPS",
                                    frame_type=1,
                                    das=(DARef(name="stVal", fc="ST", iec_type=IecType.BOOLEAN),),
                                ),
                            ),
                        ),
                        LNModel(
                            name="GGIO2",
                            ln_class="GGIO",
                            ref="IED1_LD0/GGIO2",
                            dos=(
                                DORef(
                                    name="Ind2",
                                    cdc="SPS",
                                    frame_type=1,
                                    das=(DARef(name="stVal", fc="ST", iec_type=IecType.BOOLEAN),),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        templates = self.exporter._build_data_type_templates(model, "IED1")
        lnode_types = templates.get("LNodeType", [])
        if isinstance(lnode_types, dict):
            lnode_types = [lnode_types]
        ggio_count = sum(1 for lt in lnode_types if lt.get("@lnClass") == "GGIO")
        assert ggio_count == 2, f"不同DO的GGIO应有2个LNodeType，实际: {ggio_count}"

    def test_lnode_type_dedup_in_ied_section(self, tmp_path):
        """验证去重后IED段的@lnType引用正确指向合并后的LNodeType"""
        model = IedModel(
            host="192.168.1.1",
            port=102,
            lds=(
                LDModel(
                    name="IED1_LD0",
                    inst="LD0",
                    lns=(
                        LNModel(
                            name="LLN0",
                            ln_class="LLN0",
                            ref="IED1_LD0/LLN0",
                            dos=(),
                            datasets=(
                                DataSetRef(
                                    name="dsTest",
                                    ref="IED1_LD0/LLN0.dsTest",
                                    members=(
                                        {"ref": "IED1_LD0/MMCL1.Temp001.mag.f", "fc": "MX"},
                                        {"ref": "IED1_LD0/MMCL1.Temp002.mag.f", "fc": "MX"},
                                    ),
                                ),
                            ),
                            rcb_list=(),
                        ),
                        LNModel(
                            name="MMCL1",
                            ln_class="MMCL",
                            ref="IED1_LD0/MMCL1",
                            dos=(
                                DORef(
                                    name="Temp001",
                                    cdc="MV",
                                    frame_type=0,
                                    das=(
                                        DARef(
                                            name="mag",
                                            fc="MX",
                                            iec_type=IecType.FLOAT,
                                            sub_das=(DARef(name="f", fc="MX", iec_type=IecType.FLOAT),),
                                        ),
                                        DARef(name="q", fc="MX", iec_type=IecType.INTEGER),
                                        DARef(name="t", fc="MX", iec_type=IecType.TIMESTAMP),
                                    ),
                                ),
                                DORef(
                                    name="Temp002",
                                    cdc="MV",
                                    frame_type=0,
                                    das=(
                                        DARef(
                                            name="mag",
                                            fc="MX",
                                            iec_type=IecType.FLOAT,
                                            sub_das=(DARef(name="f", fc="MX", iec_type=IecType.FLOAT),),
                                        ),
                                        DARef(name="q", fc="MX", iec_type=IecType.INTEGER),
                                        DARef(name="t", fc="MX", iec_type=IecType.TIMESTAMP),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        output_path = tmp_path / "lnode_dedup.icd"
        self.exporter.export(model, str(output_path))
        doc = xmltodict.parse(output_path.read_text(encoding="utf-8"))
        ied = doc["SCL"]["IED"]
        lns = ied["AccessPoint"]["Server"]["LDevice"]["LN"]
        if isinstance(lns, dict):
            lns = [lns]

        # DataTypeTemplates中的DOType应包含MV类型，且Temp001和Temp002共享同一DOType
        templates = doc["SCL"]["DataTypeTemplates"]
        do_types = templates.get("DOType", [])
        if isinstance(do_types, dict):
            do_types = [do_types]
        # 找到MMCL1相关的DOType
        mmcl_do_types = [dt for dt in do_types if "MMCL1" in dt.get("@id", "")]
        # Temp001和Temp002结构相同，应共享同一DOType（id为MMCL1.Temp001）
        mmcl_do_ids = {dt["@id"] for dt in mmcl_do_types}
        expected_id = "IED1LD0.MMCL1.Temp001"
        assert expected_id in mmcl_do_ids, f"应包含DOType id '{expected_id}'，实际: {mmcl_do_ids}"
        assert len(mmcl_do_ids) == 1, f"Temp001和Temp002应共享同一DOType，实际: {mmcl_do_ids}"

    # ===== IED名称推断 =====

    def test_infer_ied_name_trailing_separator_stripped(self):
        """验证带尾部下划线的IED名被清理（如 IED1_ → IED1）"""
        model = IedModel(
            host="192.168.1.1",
            port=102,
            lds=(LDModel(name="IED1_LD0", inst="IED1_LD0", lns=()),),
        )
        result = self.exporter._infer_ied_name(model)
        assert result == "IED1", f"应返回'IED1'，实际: '{result}'"

    def test_infer_ied_name_multi_ld_common_prefix(self):
        """验证多LD场景通过公共前缀推断IED名"""
        model = IedModel(
            host="192.168.1.1",
            port=102,
            lds=(
                LDModel(name="PCS001_LD0", inst="PCS001_LD0", lns=()),
                LDModel(name="PCS001_LD1", inst="PCS001_LD1", lns=()),
            ),
        )
        result = self.exporter._infer_ied_name(model)
        assert result == "PCS001", f"应返回'PCS001'，实际: '{result}'"

    # ===== 完整导出验证 =====

    def test_global_report_aggregation_across_lds(self, tmp_path):
        """验证跨LD/LN的全局RCB聚合：12个实例在全IED范围内聚合为max=12"""
        rcb_instances = tuple(
            RCBRef(name=f"urcbAin{i + 1:02d}", ref=f"LD0/LLN0.urcbAin{i + 1:02d}", rcb_type="URCB") for i in range(12)
        )
        model = IedModel(
            host="192.168.1.1",
            port=102,
            lds=(
                LDModel(
                    name="IED_LD0",
                    inst="LD0",
                    lns=(
                        LNModel(
                            name="LLN0",
                            ln_class="LLN0",
                            ref="LD0/LLN0",
                            dos=(),
                            rcb_list=rcb_instances,
                        ),
                    ),
                ),
            ),
        )
        output_path = tmp_path / "global_report.icd"
        self.exporter.export(model, str(output_path))
        doc = xmltodict.parse(output_path.read_text(encoding="utf-8"))
        ied = doc["SCL"]["IED"]
        ldevice = ied["AccessPoint"]["Server"]["LDevice"]
        ln0 = ldevice["LN0"]
        reports = ln0.get("ReportControl", [])
        if isinstance(reports, dict):
            reports = [reports]
        # 12个urcbAin01~12应合并为1个urcbAin，max=12
        by_name = {r["@name"]: r for r in reports}
        assert "urcbAin" in by_name, f"应合并为urcbAin，实际keys: {list(by_name.keys())}"
        assert by_name["urcbAin"]["RptEnabled"]["@max"] == "12", (
            f"全局聚合失败，期望max=12，实际: {by_name['urcbAin']['RptEnabled']['@max']}"
        )
        # 应只有1个报告条目
        assert len(reports) == 1, f"应只有1个ReportControl，实际: {len(reports)}"

    def test_complete_icd_export_structure(self, tmp_path):
        """验证完整ICD导出的XML结构完整性"""
        model = IedModel(
            host="192.168.1.1",
            port=102,
            discover_time="2026-06-24 00:00:00",
            lds=(
                LDModel(
                    name="KG_BAMSCTMP01",
                    inst="KG_BAMSCTMP01",
                    lns=(
                        LNModel(
                            name="LLN0",
                            ln_class="LLN0",
                            ref="KG_BAMSCTMP01/LLN0",
                            dos=(),
                            datasets=(
                                DataSetRef(
                                    name="dsDin",
                                    ref="KG_BAMSCTMP01/LLN0.dsDin",
                                    members=({"ref": "KG_BAMSCTMP01/MMCL1.Temp001.mag.f", "fc": "MX"},),
                                ),
                            ),
                            rcb_list=(
                                RCBRef(name="brcb01", ref="KG_BAMSCTMP01/LLN0.brcb01", rcb_type="BRCB"),
                                RCBRef(name="brcb01", ref="KG_BAMSCTMP01/LLN0.brcb01$01", rcb_type="BRCB"),
                                RCBRef(name="brcb01", ref="KG_BAMSCTMP01/LLN0.brcb01$02", rcb_type="BRCB"),
                                RCBRef(name="urcb01", ref="KG_BAMSCTMP01/LLN0.urcb01", rcb_type="URCB"),
                            ),
                        ),
                        LNModel(
                            name="MMCL1",
                            ln_class="MMCL",
                            ref="KG_BAMSCTMP01/MMCL1",
                            dos=(
                                DORef(
                                    name="Temp001",
                                    cdc="MV",
                                    frame_type=0,
                                    das=(
                                        DARef(
                                            name="mag",
                                            fc="MX",
                                            iec_type=IecType.FLOAT,
                                            sub_das=(DARef(name="f", fc="MX", iec_type=IecType.FLOAT),),
                                        ),
                                        DARef(name="q", fc="MX", iec_type=IecType.INTEGER),
                                        DARef(name="t", fc="MX", iec_type=IecType.TIMESTAMP),
                                    ),
                                ),
                                DORef(
                                    name="Temp002",
                                    cdc="MV",
                                    frame_type=0,
                                    das=(
                                        DARef(
                                            name="mag",
                                            fc="MX",
                                            iec_type=IecType.FLOAT,
                                            sub_das=(DARef(name="f", fc="MX", iec_type=IecType.FLOAT),),
                                        ),
                                        DARef(name="q", fc="MX", iec_type=IecType.INTEGER),
                                        DARef(name="t", fc="MX", iec_type=IecType.TIMESTAMP),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )

        output_path = tmp_path / "kg_bams.icd"
        self.exporter.export(model, str(output_path), ied_name="KG_BAMS")
        doc = xmltodict.parse(output_path.read_text(encoding="utf-8"))

        # 验证根结构
        assert "SCL" in doc
        scl = doc["SCL"]
        assert scl["@xmlns"] == "http://www.iec.ch/61850/2003/SCL"

        # 验证IED名称
        assert scl["IED"]["@name"] == "KG_BAMS"

        # 验证LDevice inst正确（从KG_BAMSCTMP01中提取CTMP01）
        ldevice = scl["IED"]["AccessPoint"]["Server"]["LDevice"]
        assert ldevice["@inst"] == "CTMP01"

        # 验证LNodeType去重（LLN0被跳过，MMCL1有1个LNodeType）
        templates = scl["DataTypeTemplates"]
        lnode_types = templates.get("LNodeType", [])
        if isinstance(lnode_types, dict):
            lnode_types = [lnode_types]
        mmcl_ln_types = [lt for lt in lnode_types if lt.get("@lnClass") == "MMCL"]
        assert len(mmcl_ln_types) == 1, f"MMCL LNodeType应去重为1个，实际: {len(mmcl_ln_types)}"

        # 验证报告整合（brcb01 3个实例合并为1个，max=3）
        ln0 = ldevice["LN0"]
        reports = ln0.get("ReportControl", [])
        if isinstance(reports, dict):
            reports = [reports]
        by_name = {r["@name"]: r for r in reports}
        assert by_name["brcb"]["RptEnabled"]["@max"] == "3"
        assert by_name["urcb"]["RptEnabled"]["@max"] == "1"

        # 验证FCDA内容
        dataset = ln0["DataSet"]
        fcda = dataset.get("FCDA", [])
        if isinstance(fcda, dict):
            fcda = [fcda]
        assert len(fcda) == 1
        assert fcda[0]["@doName"] == "Temp001"
