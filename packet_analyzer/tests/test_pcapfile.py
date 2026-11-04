"""报文日志（pcap 读写）回归。"""

import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from packet_analyzer.core import pcapfile  # noqa: E402

SAMPLES = json.loads((ROOT / "samples" / "samples.json").read_text(encoding="utf-8"))


def raw_of(key: str, name: str = "request") -> bytes:
    return bytes.fromhex(SAMPLES[key][name].replace(" ", ""))


class WriterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "logs" / "test.pcap"

    def test_roundtrip_preserves_frames_and_timestamps(self):
        frames = [raw_of("modbus_tcp"), raw_of("iec104"), raw_of("dlt645")]
        stamps = [1793000000.0, 1793000000.25, 1793000001.5]
        with pcapfile.PcapWriter(self.path, linktype=1) as writer:
            for frame, stamp in zip(frames, stamps, strict=True):
                self.assertTrue(writer.write(frame, stamp))
            self.assertEqual(writer.count, 3)
        # 目录会被自动创建
        self.assertTrue(self.path.exists())

        linktype, records = pcapfile.read_pcap(self.path)
        self.assertEqual(linktype, 1)
        self.assertEqual([item.data for item in records], frames)
        for record, expected in zip(records, stamps, strict=True):
            self.assertAlmostEqual(record.timestamp, expected, places=5)

    def test_file_header_is_valid_pcap(self):
        with pcapfile.PcapWriter(self.path, linktype=0) as writer:
            writer.write(raw_of("modbus_tcp"), 1793000000.0)
        blob = self.path.read_bytes()
        magic, major, minor, zone, sigfigs, snaplen, network = struct.unpack("<IHHiIII", blob[:24])
        self.assertEqual(magic, pcapfile.MAGIC_MICRO)
        self.assertEqual((major, minor), (2, 4))
        self.assertEqual((zone, sigfigs), (0, 0))
        self.assertEqual(snaplen, pcapfile.DEFAULT_SNAPLEN)
        self.assertEqual(network, 0)

    def test_snaplen_truncates_payload(self):
        with pcapfile.PcapWriter(self.path, linktype=1, snaplen=64) as writer:
            writer.write(bytes(200), 1793000000.0)
        blob = self.path.read_bytes()
        incl_len, orig_len = struct.unpack("<II", blob[24 + 8 : 24 + 16])
        self.assertEqual(incl_len, 64)
        self.assertEqual(orig_len, 200)

    def test_empty_frame_is_ignored(self):
        with pcapfile.PcapWriter(self.path, linktype=1) as writer:
            self.assertFalse(writer.write(b"", 1793000000.0))
            self.assertEqual(writer.count, 0)

    def test_write_after_close_is_safe(self):
        writer = pcapfile.PcapWriter(self.path, linktype=1)
        writer.close()
        self.assertFalse(writer.write(raw_of("modbus_tcp"), 1793000000.0))
        writer.close()  # 幂等

    def test_count_and_size_survive_close(self):
        writer = pcapfile.PcapWriter(self.path, linktype=1)
        writer.write(raw_of("modbus_tcp"), 1793000000.0)
        inside = writer.size()
        writer.close()
        self.assertGreater(inside, 24, "size() 应包含未落盘的缓冲")
        self.assertEqual(writer.count, 1)
        self.assertGreater(writer.size(), 24)

    def test_unwritable_path_raises(self):
        bad = Path(self._tmp.name) / "test.pcap"
        bad.mkdir()  # 同名目录，无法当文件写
        with self.assertRaises(pcapfile.PcapFileError):
            pcapfile.PcapWriter(bad, linktype=1)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "test.pcap"

    def test_reads_big_endian_file(self):
        """其它工具可能写出大端 pcap，需要兼容。"""
        frame = raw_of("modbus_tcp")
        blob = struct.pack(">IHHiIII", pcapfile.MAGIC_MICRO, 2, 4, 0, 0, 65535, 1)
        blob += struct.pack(">IIII", 1793000000, 500000, len(frame), len(frame)) + frame
        self.path.write_bytes(blob)
        linktype, records = pcapfile.read_pcap(self.path)
        self.assertEqual(linktype, 1)
        self.assertEqual(records[0].data, frame)
        self.assertAlmostEqual(records[0].timestamp, 1793000000.5, places=5)

    def test_reads_nanosecond_file(self):
        frame = raw_of("iec104")
        blob = struct.pack("<IHHiIII", pcapfile.MAGIC_NANO, 2, 4, 0, 0, 65535, 1)
        blob += struct.pack("<IIII", 1793000000, 250_000_000, len(frame), len(frame)) + frame
        self.path.write_bytes(blob)
        _linktype, records = pcapfile.read_pcap(self.path)
        self.assertAlmostEqual(records[0].timestamp, 1793000000.25, places=6)

    def test_truncated_tail_keeps_complete_records(self):
        """抓包程序异常退出会留下半截记录，应保留能读的部分。"""
        frame = raw_of("modbus_tcp")
        blob = struct.pack("<IHHiIII", pcapfile.MAGIC_MICRO, 2, 4, 0, 0, 65535, 1)
        blob += struct.pack("<IIII", 1793000000, 0, len(frame), len(frame)) + frame
        blob += struct.pack("<IIII", 1793000001, 0, 100, 100) + frame  # 声明 100 字节但只有 12
        self.path.write_bytes(blob)
        _linktype, records = pcapfile.read_pcap(self.path)
        self.assertEqual(len(records), 1)

    def test_non_pcap_file_raises(self):
        self.path.write_bytes(b"this is not a pcap file at all")
        with self.assertRaises(pcapfile.PcapFileError):
            pcapfile.read_pcap(self.path)

    def test_short_file_raises(self):
        self.path.write_bytes(b"\xa1\xb2")
        with self.assertRaises(pcapfile.PcapFileError):
            pcapfile.read_pcap(self.path)

    def test_is_pcap_file_by_magic(self):
        with pcapfile.PcapWriter(self.path, linktype=1) as writer:
            writer.write(raw_of("modbus_tcp"), 1793000000.0)
        self.assertTrue(pcapfile.is_pcap_file(self.path))
        other = Path(self._tmp.name) / "x.txt"
        other.write_text("hello", encoding="utf-8")
        self.assertFalse(pcapfile.is_pcap_file(other))


class NamingTests(unittest.TestCase):
    def test_log_name_sanitises_interface(self):
        from datetime import datetime

        name = pcapfile.default_log_name("\\Device\\NPF_{ABC-123}", datetime(2026, 10, 27, 19, 30, 5))
        self.assertEqual(name, "NPF_ABC-123_20261027_193005.pcap")

    def test_log_name_without_interface(self):
        from datetime import datetime

        self.assertEqual(
            pcapfile.default_log_name("", datetime(2026, 10, 27, 19, 30, 5)),
            "capture_20261027_193005.pcap",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
