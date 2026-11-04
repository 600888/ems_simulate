"""链路层解析与 libpcap 绑定回归。

链路层用例用程序构造的帧，任何机器都能跑；
libpcap 相关用例在未安装 Npcap/libpcap 时自动跳过。
"""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from packet_analyzer.core import (
    linklayer,  # noqa: E402
    wpcap,  # noqa: E402
)


def ipv4_tcp(
    src: str,
    dst: str,
    sport: int,
    dport: int,
    *,
    seq: int = 1000,
    flags: int = 0x18,
    payload: bytes = b"",
) -> bytes:
    tcp = (
        sport.to_bytes(2, "big")
        + dport.to_bytes(2, "big")
        + seq.to_bytes(4, "big")
        + (0).to_bytes(4, "big")
        + bytes([0x50, flags])
        + (8192).to_bytes(2, "big")
        + (0).to_bytes(2, "big")
        + (0).to_bytes(2, "big")
        + payload
    )
    total = 20 + len(tcp)
    header = (
        bytes([0x45, 0])
        + total.to_bytes(2, "big")
        + (0).to_bytes(2, "big")
        + (0x4000).to_bytes(2, "big")
        + bytes([64, 6])
        + (0).to_bytes(2, "big")
        + bytes(map(int, src.split(".")))
        + bytes(map(int, dst.split(".")))
    )
    return header + tcp


def ipv4_udp(src: str, dst: str, sport: int, dport: int, payload: bytes = b"") -> bytes:
    length = 8 + len(payload)
    udp = sport.to_bytes(2, "big") + dport.to_bytes(2, "big") + length.to_bytes(2, "big") + (0).to_bytes(2, "big")
    total = 20 + length
    header = (
        bytes([0x45, 0])
        + total.to_bytes(2, "big")
        + (0).to_bytes(2, "big")
        + (0x4000).to_bytes(2, "big")
        + bytes([64, 17])
        + (0).to_bytes(2, "big")
        + bytes(map(int, src.split(".")))
        + bytes(map(int, dst.split(".")))
    )
    return header + udp + payload


def ether(ethertype: int, body: bytes) -> bytes:
    return bytes.fromhex("ffffffffffff001122334455") + ethertype.to_bytes(2, "big") + body


def null_frame(body: bytes) -> bytes:
    return (2).to_bytes(4, "little") + body


class NullLinkTests(unittest.TestCase):
    """回环设备用 DLT_NULL：4 字节地址族 + IP。"""

    def test_ipv4_tcp(self):
        segment = linklayer.parse_link_frame(null_frame(ipv4_tcp("127.0.0.1", "127.0.0.1", 51000, 502, payload=b"AB")), linklayer.DLT_NULL)
        self.assertIsNotNone(segment)
        self.assertEqual(segment.src_ip, "127.0.0.1")
        self.assertEqual(segment.dst_port, 502)
        self.assertEqual(segment.transport, "TCP")
        self.assertEqual(segment.payload, b"AB")

    def test_big_endian_family_is_also_accepted(self):
        frame = (2).to_bytes(4, "big") + ipv4_udp("10.0.0.1", "10.0.0.2", 5000, 53)
        segment = linklayer.parse_link_frame(frame, linklayer.DLT_NULL)
        self.assertEqual(segment.transport, "UDP")


class EthernetTests(unittest.TestCase):
    def test_ipv4_tcp(self):
        frame = ether(linklayer.ETHERTYPE_IPV4, ipv4_tcp("192.168.3.10", "192.168.3.20", 51234, 502, seq=77))
        segment = linklayer.parse_link_frame(frame, linklayer.DLT_EN10MB)
        self.assertEqual((segment.src_ip, segment.dst_ip), ("192.168.3.10", "192.168.3.20"))
        self.assertEqual((segment.src_port, segment.dst_port), (51234, 502))
        self.assertEqual(segment.seq, 77)
        self.assertEqual(segment.transport, "TCP")

    def test_single_and_double_vlan(self):
        single = (
            bytes.fromhex("ffffffffffff001122334455")
            + bytes.fromhex("8100")
            + bytes.fromhex("00640800")
            + ipv4_tcp("10.1.1.1", "10.1.1.2", 1000, 2404)
        )
        segment = linklayer.parse_link_frame(single, linklayer.DLT_EN10MB)
        self.assertEqual(segment.dst_port, 2404)

        double = (
            bytes.fromhex("ffffffffffff001122334455")
            + bytes.fromhex("88a8")
            + bytes.fromhex("00648100")
            + bytes.fromhex("00640800")
            + ipv4_tcp("10.1.1.1", "10.1.1.2", 1000, 2404)
        )
        self.assertEqual(linklayer.parse_link_frame(double, linklayer.DLT_EN10MB).dst_port, 2404)

    def test_goose_frame_is_passed_through(self):
        goose = bytes.fromhex("010ccd010001020304050607") + (0x88B8).to_bytes(2, "big") + bytes(40)
        segment = linklayer.parse_link_frame(goose, linklayer.DLT_EN10MB)
        self.assertTrue(segment.is_goose)
        self.assertEqual(segment.goose_frame, goose)
        self.assertEqual(segment.transport, "")

    def test_ipv6_tcp(self):
        ipv6 = (
            bytes.fromhex("60000000")
            + (20).to_bytes(2, "big")
            + bytes([6, 64])
            + bytes.fromhex("20010db8" + "0000" * 5 + "0001")
            + bytes.fromhex("20010db8" + "0000" * 5 + "0002")
        )
        # TCP：端口 1024 → 502，数据偏移 5（20 字节头）
        tcp = (1024).to_bytes(2, "big") + (502).to_bytes(2, "big") + bytes(8) + bytes([0x50, 0x18]) + bytes(6)
        segment = linklayer.parse_link_frame(ether(linklayer.ETHERTYPE_IPV6, ipv6 + tcp), linklayer.DLT_EN10MB)
        self.assertEqual(segment.src_ip, "2001:db8::1")
        self.assertEqual(segment.dst_ip, "2001:db8::2")
        self.assertEqual(segment.dst_port, 502)

    def test_truncated_or_unknown_frames(self):
        self.assertIsNone(linklayer.parse_link_frame(b"", linklayer.DLT_EN10MB))
        self.assertIsNone(linklayer.parse_link_frame(bytes(10), linklayer.DLT_EN10MB))
        self.assertIsNone(linklayer.parse_link_frame(ether(0x1234, bytes(60)), linklayer.DLT_EN10MB))


class FlagsTests(unittest.TestCase):
    def test_syn_detection(self):
        syn = null_frame(ipv4_tcp("10.0.0.1", "10.0.0.2", 50000, 502, flags=0x02))
        syn_ack = null_frame(ipv4_tcp("10.0.0.2", "10.0.0.1", 502, 50000, flags=0x12))
        push_ack = null_frame(ipv4_tcp("10.0.0.1", "10.0.0.2", 50000, 502, flags=0x18))
        for frame, expected in ((syn, True), (syn_ack, False), (push_ack, False)):
            self.assertEqual(linklayer.parse_link_frame(frame, linklayer.DLT_NULL).is_syn, expected)

    def test_udp_payload_honours_length_field(self):
        frame = null_frame(ipv4_udp("10.0.0.1", "10.0.0.2", 5000, 5001, payload=b"HELLO"))
        self.assertEqual(linklayer.parse_link_frame(frame, linklayer.DLT_NULL).payload, b"HELLO")


class OtherLinkTypesTests(unittest.TestCase):
    def test_raw_ip(self):
        segment = linklayer.parse_link_frame(ipv4_tcp("10.0.0.1", "10.0.0.2", 1000, 2000), linklayer.DLT_RAW)
        self.assertEqual(segment.dst_port, 2000)

    def test_linux_sll(self):
        header = bytes.fromhex("000000010006") + bytes.fromhex("001122334455") + bytes.fromhex("0000") + b"\x08\x00"
        segment = linklayer.parse_link_frame(header + ipv4_tcp("10.0.0.1", "10.0.0.2", 1000, 2000), linklayer.DLT_LINUX_SLL)
        self.assertEqual(segment.dst_port, 2000)


@unittest.skipUnless(wpcap.is_available(), "未安装 Npcap/libpcap")
class WpcapBindingTests(unittest.TestCase):
    def test_version_string(self):
        self.assertIn("pcap", wpcap.libpcap_version().lower())

    def test_list_devices_returns_entries(self):
        devices = wpcap.list_devices()
        self.assertTrue(devices)
        self.assertTrue(all(device.name for device in devices))
        self.assertTrue(any(device.is_loopback for device in devices), "应能识别回环设备")

    def test_pkthdr_layout_matches_platform(self):
        """Windows 的 long 是 32 位，Linux/macOS 是 64 位，布局必须分开。"""
        if sys.platform == "win32":
            self.assertEqual(wpcap.ctypes.sizeof(wpcap._Timeval32), 8)  # noqa: SLF001
            self.assertEqual(wpcap.ctypes.sizeof(wpcap._PktHdr32), 16)  # noqa: SLF001
        else:
            self.assertEqual(wpcap.ctypes.sizeof(wpcap._Timeval64), 16)  # noqa: SLF001
            self.assertEqual(wpcap.ctypes.sizeof(wpcap._PktHdr64), 24)  # noqa: SLF001

    def test_bad_filter_raises_clear_error(self):
        device = next((item.name for item in wpcap.list_devices() if item.is_loopback), "")
        if not device:
            self.skipTest("无回环设备")
        with self.assertRaises(wpcap.PcapError):
            wpcap.PcapHandle(device, filter_text="this is not bpf")

    def test_invalid_device_raises(self):
        with self.assertRaises(wpcap.PcapError):
            wpcap.PcapHandle("\\Device\\NPF_NOT_EXIST")


if __name__ == "__main__":
    unittest.main(verbosity=2)
