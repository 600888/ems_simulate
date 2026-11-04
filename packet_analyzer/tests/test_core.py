"""核心功能回归（unittest，无第三方依赖）。

运行：python -m unittest discover -s packet_analyzer/tests -p "test_*.py" -v
"""

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from packet_analyzer.core import registry  # noqa: E402
from packet_analyzer.core.store import MessageStore  # noqa: E402

SAMPLES = json.loads((ROOT / "samples" / "samples.json").read_text(encoding="utf-8"))
STREAM_PROTOCOLS = ["modbus_tcp", "dlt645", "iec104", "iec101", "dnp3", "mms"]


def raw_of(key: str, name: str = "request") -> bytes:
    return bytes.fromhex(SAMPLES[key][name].replace(" ", ""))


class _SrcBlocker:
    """阻止导入主项目 ``src`` 包，用于验证本工具的自包含性。"""

    def find_spec(self, fullname, path=None, target=None):  # noqa: ARG002
        if fullname == "src" or fullname.startswith("src."):
            raise AssertionError(f"packet_analyzer 不应依赖主项目模块：{fullname}")
        return None


class ParserTests(unittest.TestCase):
    def test_all_samples_parse(self):
        for key, item in SAMPLES.items():
            for name, role in (("request", "Request"), ("response", "Response")):
                text = item.get(name) or ""
                if not text:
                    continue
                with self.subTest(protocol=key, direction=name):
                    detail = registry.parse_frame(bytes.fromhex(text.replace(" ", "")), key, role=role)
                    self.assertTrue(detail["valid"], detail["errors"])
                    self.assertTrue(detail["summary"])
                    self.assertEqual(detail["raw_length"], len(bytes.fromhex(text.replace(" ", ""))))

    def test_all_samples_autodetect(self):
        for key, item in SAMPLES.items():
            for name in ("request", "response"):
                text = item.get(name) or ""
                if not text:
                    continue
                with self.subTest(protocol=key, direction=name):
                    detected, score = registry.detect_protocol(bytes.fromhex(text.replace(" ", "")))
                    self.assertEqual(detected, key)
                    self.assertGreaterEqual(score, 70)

    def test_unknown_protocol_returns_error_detail(self):
        detail = registry.parse_frame(b"\x00\x11\x22\x33")
        self.assertFalse(detail["valid"])
        self.assertTrue(detail["errors"])

    def test_parsing_does_not_import_main_project(self):
        """所有协议解析都不应触发对主项目 src 包的导入（保证可独立分发）。"""
        blocker = _SrcBlocker()
        sys.meta_path.insert(0, blocker)
        try:
            for key, item in SAMPLES.items():
                for name in ("request", "response"):
                    text = item.get(name) or ""
                    if not text:
                        continue
                    registry.parse_frame(bytes.fromhex(text.replace(" ", "")), key, role="Request")
            # DNP3 走 pydnp3_pure，且 G52 注册模块已内置，必须能解析出对象
            dnp3_response = registry.parse_frame(raw_of("dnp3", "response"), "dnp3", role="Response")
            self.assertTrue(dnp3_response["objects"], "DNP3 响应应解析出数据对象")
        finally:
            sys.meta_path.remove(blocker)
        self.assertNotIn("src", sys.modules)

    def test_dnp3_supplementary_handler_is_bundled(self):
        """G52 等补充对象组来自本工具内置模块，而非主项目。"""
        from packet_analyzer.core import dnp3_objects

        self.assertEqual(dnp3_objects.Group52Handler().group, 52)
        self.assertEqual(dnp3_objects.Group52Handler().supported_variations, (1, 2))
        self.assertNotIn("src.proto.dnp3.objects", sys.modules)


class SplitterTests(unittest.TestCase):
    def test_explicit_protocol_split_byte_by_byte(self):
        for key in STREAM_PROTOCOLS:
            raw = raw_of(key)
            splitter = registry.FrameSplitter(key)
            frames = []
            for byte in raw:
                frames.extend(splitter.feed(bytes([byte])))
            with self.subTest(protocol=key):
                self.assertEqual(frames, [raw])

    def test_auto_split_multiple_frames_in_one_chunk(self):
        request, response = raw_of("modbus_tcp"), raw_of("modbus_tcp", "response")
        splitter = registry.FrameSplitter(registry.AUTO)
        self.assertEqual(splitter.feed(request + response), [request, response])

    def test_auto_split_iec104_short_frames(self):
        frame = raw_of("iec104")
        splitter = registry.FrameSplitter(registry.AUTO)
        self.assertEqual(splitter.feed(frame * 2), [frame, frame])

    def test_rtu_requires_idle_flush(self):
        raw = raw_of("modbus_rtu")
        splitter = registry.FrameSplitter("modbus_rtu")
        self.assertEqual(splitter.feed(raw), [])
        self.assertEqual(splitter.flush(), [raw])

    def test_noise_is_resynchronised(self):
        frame = raw_of("iec104")
        splitter = registry.FrameSplitter(registry.AUTO)
        self.assertEqual(splitter.feed(b"\xAA\xBB" + frame), [frame])


class StoreTests(unittest.TestCase):
    def test_modbus_request_response_correlation(self):
        store = MessageStore()
        request = store.append("TX", raw_of("modbus_tcp"), "modbus_tcp", role="Request")
        store.append("RX", raw_of("modbus_tcp", "response"), "modbus_tcp", role="Response")
        detail = store.detail(request.sequence + 1)
        self.assertIsNotNone(detail["correlation"])
        self.assertEqual(detail["correlation"]["request_sequence_id"], request.sequence)
        self.assertEqual(detail["correlation"]["match_method"], "transaction_id")

    def test_dnp3_response_correlation_by_application_sequence(self):
        store = MessageStore()
        request = store.append("TX", raw_of("dnp3"), "dnp3", role="Request")
        store.append("RX", raw_of("dnp3", "response"), "dnp3", role="Response")
        detail = store.detail(request.sequence + 1)
        self.assertIsNotNone(detail["correlation"])
        self.assertEqual(detail["correlation"]["request_sequence_id"], request.sequence)

    def test_store_trims_and_clears(self):
        store = MessageStore(max_size=3)
        for _ in range(5):
            store.append("TX", raw_of("iec104"), "iec104", role="Request")
        self.assertEqual(len(store), 3)
        self.assertEqual(store.stats()["tx_count"], 5)
        store.clear()
        self.assertEqual(len(store), 0)
        self.assertEqual(store.stats()["tx_count"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
