"""命令行版回归：参数解析、行结构、CSV 导出。

这些用例不需要 Npcap，任何机器都能跑。
"""

import csv
import io
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from packet_analyzer import cli  # noqa: E402
from packet_analyzer.core import registry  # noqa: E402
from packet_analyzer.core.pcap import FrameMeta  # noqa: E402

MODBUS_REQUEST = bytes.fromhex("000100000006010300000009")


class RowSchemaTests(unittest.TestCase):
    def test_make_row_covers_every_csv_column(self):
        detail = registry.parse_frame(MODBUS_REQUEST, "modbus_tcp")
        meta = FrameMeta(
            src_ip="10.0.0.1", src_port=50000, dst_ip="10.0.0.2", dst_port=502,
            transport="TCP", role=registry.ROLE_REQUEST,
        )
        row = cli._make_row(1, 1793000000.0, "TX", meta, detail, MODBUS_REQUEST, "摘要")
        for column in cli.ROW_COLUMNS:
            self.assertIn(column, row, f"缺少列 {column}")
        self.assertEqual(row["protocol"], "Modbus TCP")
        self.assertEqual(row["length"], len(MODBUS_REQUEST))
        self.assertEqual(row["hex"], MODBUS_REQUEST.hex().upper())

    def test_make_row_handles_goose_without_ip(self):
        detail = registry.parse_frame(bytes.fromhex("88b8"), "goose")
        row = cli._make_row(1, 1793000000.0, "RX", FrameMeta(transport="ETH", role="Publish"), detail, b"\x88\xb8", "")
        self.assertEqual(row["src_ip"], "")
        self.assertEqual(row["transport"], "ETH")

    def test_protocol_name_resolves_auto(self):
        detail = registry.parse_frame(MODBUS_REQUEST, registry.AUTO)
        self.assertEqual(cli._protocol_name(detail), "Modbus TCP")

    def test_protocol_name_never_empty(self):
        detail = registry.parse_frame(b"\x00\x01\x02", registry.AUTO)
        self.assertTrue(cli._protocol_name(detail))


class CsvExportTests(unittest.TestCase):
    def test_csv_written_with_bom_and_header(self):
        detail = registry.parse_frame(MODBUS_REQUEST, "modbus_tcp")
        meta = FrameMeta(src_ip="10.0.0.1", src_port=50000, dst_ip="10.0.0.2", dst_port=502, transport="TCP")
        rows = [cli._make_row(1, 1793000000.0, "TX", meta, detail, MODBUS_REQUEST, "摘要")]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            cli._write_csv(str(path), rows)
            raw = path.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "应带 UTF-8 BOM，Excel 才能正确识别中文")
            with path.open(encoding="utf-8-sig", newline="") as handle:
                parsed = list(csv.DictReader(handle))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["protocol"], "Modbus TCP")

    def test_csv_ignores_unknown_keys(self):
        """回放与抓包行结构不同时不能崩，多余字段应被忽略。"""
        row = {"seq": 1, "summary": "x", "unknown_field": "y"}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            cli._write_csv(str(path), [row])  # 不应抛异常
            self.assertTrue(path.exists())


class ParserTests(unittest.TestCase):
    def test_subcommands_registered(self):
        parser = cli.build_parser()
        cases = {
            "ifaces": ["ifaces"],
            "selftest": ["selftest"],
            "capture": ["capture"],
            "replay": ["replay", "some.pcap"],
            "parse": ["parse", MODBUS_REQUEST.hex()],
        }
        for name, argv in cases.items():
            args = parser.parse_args(argv)
            self.assertTrue(callable(args.func), f"{name} 未绑定处理函数")

    def test_parse_command_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "detail.json"
            code = cli.main(["parse", MODBUS_REQUEST.hex(), "--protocol", "modbus_tcp", "--json", str(out)])
            self.assertEqual(code, 0)
            self.assertTrue(out.exists())

    def test_replay_missing_file_returns_2(self):
        self.assertEqual(cli.main(["replay", "definitely_missing.pcap"]), 2)

    def test_parse_rejects_bad_hex(self):
        self.assertEqual(cli.main(["parse", "zzz"]), 2)

    def test_stdio_reconfigure_is_safe(self):
        cli._prepare_stdio()  # 不抛异常即可


class OutputEncodingTests(unittest.TestCase):
    def test_piped_output_uses_utf8(self):
        """重定向到文件时应写 UTF-8，避免 GBK 服务器上导出乱码。"""
        original = sys.stdout
        try:
            buffer = io.BytesIO()
            wrapper = io.TextIOWrapper(buffer, encoding="gbk")
            sys.stdout = wrapper
            cli._prepare_stdio()
            print("中文测试", flush=True)
            wrapper.flush()
            data = buffer.getvalue()
        finally:
            sys.stdout = original
        self.assertEqual(data.decode("utf-8").strip(), "中文测试")


if __name__ == "__main__":
    unittest.main(verbosity=2)
