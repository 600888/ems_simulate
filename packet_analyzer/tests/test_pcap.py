"""网卡抓包引擎回归。

分两部分：
* 纯逻辑用例（BPF 构造、IP 过滤、角色判定）—— 任何机器都能跑
* 真实抓包用例 —— 需要 Npcap/libpcap，缺失时自动跳过
"""

import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from packet_analyzer.core import pcapfile, registry, wpcap  # noqa: E402
from packet_analyzer.core.ifaces import capture_available, list_interfaces  # noqa: E402
from packet_analyzer.core.pcap import PcapCaptureEngine, PcapConfig, describe_bpf  # noqa: E402
from packet_analyzer.core.store import MessageStore  # noqa: E402

SAMPLES = json.loads((ROOT / "samples" / "samples.json").read_text(encoding="utf-8"))
LOOPBACK_HINTS = ("loopback", "lo")


def raw_of(key: str, name: str = "request") -> bytes:
    return bytes.fromhex(SAMPLES[key][name].replace(" ", ""))


def loopback_interface() -> str:
    for item in list_interfaces():
        if item.is_loopback or any(hint in item.name.lower() for hint in LOOPBACK_HINTS):
            return item.id
    return ""


class ConfigTests(unittest.TestCase):
    def test_bpf_includes_hosts_and_port(self):
        config = PcapConfig(ip_filter="192.168.1.10, 192.168.1.20", port_filter=502)
        bpf = config.bpf()
        self.assertIn("host 192.168.1.10", bpf)
        self.assertIn("host 192.168.1.20", bpf)
        self.assertIn("port 502", bpf)
        self.assertIn("tcp or udp", bpf)

    def test_bpf_without_filters(self):
        bpf = PcapConfig().bpf()
        self.assertIn("tcp or udp", bpf)
        self.assertIn("全部", describe_bpf(PcapConfig()))

    def test_bpf_without_filters_includes_goose(self):
        """无过滤时必须带上 GOOSE，否则二层 GOOSE 抓不到。"""
        self.assertIn("ether proto 0x88b8", PcapConfig().bpf())

    def test_bpf_with_ip_filter_excludes_goose(self):
        """指定 IP 过滤后 GOOSE 无 IP 可言，不应再出现在表达式里。"""
        bpf = PcapConfig(ip_filter="10.0.0.1").bpf()
        self.assertIn("host 10.0.0.1", bpf)
        self.assertNotIn("88b8", bpf)

    def test_has_filter(self):
        self.assertFalse(PcapConfig().has_filter())
        self.assertTrue(PcapConfig(ip_filter="10.0.0.1").has_filter())
        self.assertTrue(PcapConfig(port_filter=502).has_filter())

    def test_filter_list_accepts_multiple_separators(self):
        config = PcapConfig(ip_filter=" 10.0.0.1,10.0.0.2; 10.0.0.3 ")
        self.assertEqual(config.filter_list(), ["10.0.0.1", "10.0.0.2", "10.0.0.3"])

    def test_config_roundtrip(self):
        original = PcapConfig(interface="以太网", ip_filter="10.1.1.1", port_filter=2404, master_ip="10.1.1.2")
        restored = PcapConfig.from_dict(original.to_dict())
        self.assertEqual(restored, original)


class RoleTests(unittest.TestCase):
    def _engine(self, **kwargs) -> PcapCaptureEngine:
        return PcapCaptureEngine(PcapConfig(**kwargs))

    def test_master_ip_overrides_heuristics(self):
        engine = self._engine(master_ip="10.0.0.1")
        self.assertEqual(engine._role("10.0.0.1", 40000, "10.0.0.2", 502), registry.ROLE_REQUEST)
        self.assertEqual(engine._role("10.0.0.2", 502, "10.0.0.1", 40000), registry.ROLE_RESPONSE)

    def test_learned_client_endpoint_wins_on_same_ip(self):
        """回环场景两端 IP 相同，必须靠端点区分客户端。"""
        from packet_analyzer.core.pcap import _flow_key

        engine = self._engine()
        key = _flow_key("127.0.0.1", 40001, "127.0.0.1", 15020)
        engine._clients[key] = ("127.0.0.1", 40001)
        self.assertEqual(engine._role("127.0.0.1", 40001, "127.0.0.1", 15020), registry.ROLE_REQUEST)
        self.assertEqual(engine._role("127.0.0.1", 15020, "127.0.0.1", 40001), registry.ROLE_RESPONSE)

    def test_known_service_port_heuristic(self):
        engine = self._engine()
        self.assertEqual(engine._role("10.0.0.5", 51000, "10.0.0.9", 502), registry.ROLE_REQUEST)
        self.assertEqual(engine._role("10.0.0.9", 502, "10.0.0.5", 51000), registry.ROLE_RESPONSE)

    def test_ip_filter_rejects_other_hosts(self):
        engine = self._engine(ip_filter="10.0.0.1")
        self.assertTrue(engine._ip_allowed("10.0.0.1", "10.0.0.2"))
        self.assertTrue(engine._ip_allowed("10.0.0.2", "10.0.0.1"))
        self.assertFalse(engine._ip_allowed("10.0.0.2", "10.0.0.3"))


class RecordTests(unittest.TestCase):
    def test_record_exposes_endpoint_and_matches_ip(self):
        store = MessageStore()
        record = store.append(
            "RX",
            raw_of("modbus_tcp"),
            "modbus_tcp",
            role="Response",
            src_ip="192.168.1.20",
            src_port=502,
            dst_ip="192.168.1.10",
            dst_port=41234,
            transport="TCP",
        )
        self.assertEqual(record.endpoint_text, "192.168.1.20:502 → 192.168.1.10:41234")
        self.assertTrue(record.matches_ip("192.168.1.20"))
        self.assertTrue(record.matches_ip("1.10"))
        self.assertFalse(record.matches_ip("10.9.9.9"))

    def test_imported_record_without_ip_never_matches_ip_filter(self):
        store = MessageStore()
        record = store.append("TX", raw_of("iec104"), "iec104", role="Request")
        self.assertEqual(record.endpoint_text, "")
        self.assertFalse(record.matches_ip("192.168.1.1"))


class NonModbusTrafficTests(unittest.TestCase):
    def test_modbus_tcp_splitter_rejects_non_modbus_stream(self):
        """协议标识不为 0 时不应按 MBAP 长度切帧，避免把普通 TCP 流量误当报文。"""
        splitter = registry.FrameSplitter("modbus_tcp")
        payload = b"GET / HTTP/1.1\r\nHost: example\r\n\r\n"
        self.assertEqual(splitter.feed(payload), [])

    def test_modbus_tcp_splitter_accepts_real_frame(self):
        splitter = registry.FrameSplitter("modbus_tcp")
        self.assertEqual(splitter.feed(raw_of("modbus_tcp")), [raw_of("modbus_tcp")])


@unittest.skipUnless(capture_available()[0], f"缺少抓包能力：{capture_available()[1]}")
class LiveCaptureTests(unittest.TestCase):
    """在回环网卡上真实抓取一次 Modbus TCP 往返。"""

    @classmethod
    def setUpClass(cls):
        cls.interface = loopback_interface()
        if not cls.interface:
            raise unittest.SkipTest("未找到回环网卡")

    def test_capture_modbus_request_and_response(self):
        frames: list[tuple[bytes, str, object]] = []
        errors: list[str] = []
        engine = PcapCaptureEngine(
            PcapConfig(interface=self.interface, protocol="modbus_tcp", ip_filter="127.0.0.1"),
            on_frame=lambda raw, direction, meta: frames.append((raw, direction, meta)),
            on_error=errors.append,
        )
        self.assertTrue(engine.start())
        time.sleep(1.5)

        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        request, response = raw_of("modbus_tcp"), raw_of("modbus_tcp", "response")

        def serve():
            conn, _ = server.accept()
            conn.recv(1024)
            time.sleep(0.15)
            conn.sendall(response)
            time.sleep(0.3)
            conn.close()
            server.close()

        threading.Thread(target=serve, daemon=True).start()
        client = socket.create_connection(("127.0.0.1", port))
        client.sendall(request)
        time.sleep(0.8)
        client.close()

        deadline = time.time() + 5
        while time.time() < deadline and len(frames) < 2:
            time.sleep(0.05)
        engine.stop()

        self.assertEqual(errors, [])
        self.assertGreaterEqual(len(frames), 2)
        payloads = [item[0] for item in frames]
        self.assertIn(request, payloads)
        self.assertIn(response, payloads)

        by_payload = {item[0]: item for item in frames}
        req_meta = by_payload[request][2]
        rsp_meta = by_payload[response][2]
        self.assertEqual(req_meta.role, registry.ROLE_REQUEST)
        self.assertEqual(rsp_meta.role, registry.ROLE_RESPONSE)
        self.assertEqual(req_meta.dst_port, port)
        self.assertEqual(rsp_meta.src_port, port)
        self.assertEqual(req_meta.transport, "TCP")

    def test_ip_filter_excludes_unrelated_addresses(self):
        frames: list[bytes] = []
        engine = PcapCaptureEngine(
            PcapConfig(interface=self.interface, protocol="modbus_tcp", ip_filter="203.0.113.77"),
            on_frame=lambda raw, _d, _m: frames.append(raw),
        )
        self.assertTrue(engine.start())
        time.sleep(1.0)

        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        def serve():
            conn, _ = server.accept()
            conn.recv(1024)
            conn.close()
            server.close()

        threading.Thread(target=serve, daemon=True).start()
        client = socket.create_connection(("127.0.0.1", port))
        client.sendall(raw_of("modbus_tcp"))
        time.sleep(0.6)
        client.close()
        engine.stop()
        self.assertEqual(frames, [], "不匹配 IP 过滤条件的报文不应上报")


class GooseCaptureTests(unittest.TestCase):
    """GOOSE 是二层帧，无需 Npcap 即可验证引擎的转发路径。"""

    def test_goose_frame_reaches_callback_as_whole_ethernet_frame(self):
        from packet_analyzer.core import linklayer

        goose = raw_of("goose")
        captured: list[tuple[bytes, str, object]] = []
        engine = PcapCaptureEngine(
            PcapConfig(interface="dummy", protocol="goose"),
            on_frame=lambda raw, direction, meta: captured.append((raw, direction, meta)),
        )
        engine._datalink = linklayer.DLT_EN10MB  # noqa: SLF001
        engine._process(goose)  # noqa: SLF001

        self.assertEqual(len(captured), 1)
        payload, direction, meta = captured[0]
        self.assertEqual(payload, goose, "GOOSE 应整帧透传（含 MAC 头）")
        self.assertEqual(meta.transport, "ETH")

    def test_non_goose_ethernet_is_ignored_without_ip(self):
        from packet_analyzer.core import linklayer

        captured: list[bytes] = []
        engine = PcapCaptureEngine(
            PcapConfig(interface="dummy", protocol="goose"),
            on_frame=lambda raw, _d, _m: captured.append(raw),
        )
        engine._datalink = linklayer.DLT_EN10MB  # noqa: SLF001
        engine._process(bytes.fromhex("ffffffffffff001122334455") + b"\xab\xcd" + bytes(40))  # noqa: SLF001
        self.assertEqual(captured, [])


class LogIntegrationTests(unittest.TestCase):
    """日志写的是完整链路帧，且只含通过过滤的报文。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "capture.pcap"

    def _engine(self, **config_kwargs) -> PcapCaptureEngine:
        from packet_analyzer.core import linklayer

        engine = PcapCaptureEngine(
            PcapConfig(interface="dummy", **config_kwargs),
            on_frame=lambda *_a: None,
        )
        engine._datalink = linklayer.DLT_EN10MB  # noqa: SLF001
        return engine

    def test_log_records_full_link_frame_not_payload(self):
        """pcap 头声明的是链路类型，必须写完整以太网帧，否则 Wireshark 解不出来。"""
        engine = self._engine(protocol="modbus_tcp")
        engine.set_log(str(self.path))
        engine._open_log_if_needed()  # noqa: SLF001 - 模拟抓包线程启动

        frame = bytes.fromhex("ffffffffffff001122334455") + bytes.fromhex("0800") + raw_of("modbus_tcp")
        # 补一个合法 IP 头 + TCP 头，让 _process 能继续走
        payload = raw_of("modbus_tcp")
        tcp = (50000).to_bytes(2, "big") + (502).to_bytes(2, "big") + bytes(16) + payload
        ip = (
            bytes([0x45, 0])
            + (20 + len(tcp)).to_bytes(2, "big")
            + bytes(4)
            + bytes([64, 6])
            + bytes(2)
            + bytes([10, 0, 0, 1])
            + bytes([10, 0, 0, 2])
        )
        frame = bytes.fromhex("ffffffffffff001122334455") + bytes.fromhex("0800") + ip + tcp
        engine._handle_packet(frame)  # noqa: SLF001
        engine.close_log()

        linktype, records = pcapfile.read_pcap(self.path)
        self.assertEqual(linktype, 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].data, frame, "日志应保存完整链路帧")

    def test_log_off_by_default(self):
        engine = self._engine()
        self.assertEqual(engine.log_count, 0)
        self.assertEqual(engine.log_path, "")

    def test_close_log_keeps_statistics(self):
        engine = self._engine()
        engine.set_log(str(self.path))
        engine._open_log_if_needed()  # noqa: SLF001
        engine._handle_packet(  # noqa: SLF001
            bytes.fromhex("ffffffffffff001122334455") + bytes.fromhex("88b8") + bytes(40)
        )
        engine.close_log()
        self.assertGreaterEqual(engine.log_count, 1, "停止后仍应能读到写入帧数")

    def test_log_uses_capture_timestamp_not_write_time(self):
        """日志时间戳必须是抓包时间。

        以前写的是 ``time.time()``，即「入库时刻」，比真实抓包时刻晚一个处理
        延迟；回放时与设备日志按时间对齐会整体偏移。这里用一个明显不是当前
        时刻的值来钉住这个行为。
        """
        engine = self._engine(protocol="modbus_tcp")
        engine.set_log(str(self.path))
        engine._open_log_if_needed()  # noqa: SLF001
        capture_time = 1_700_000_000.25
        engine._handle_packet(  # noqa: SLF001
            bytes.fromhex("ffffffffffff001122334455") + bytes.fromhex("88b8") + bytes(40),
            capture_time,
        )
        engine.close_log()

        _linktype, records = pcapfile.read_pcap(self.path)
        self.assertEqual(len(records), 1)
        self.assertAlmostEqual(records[0].timestamp, capture_time, places=3)


class CaptureTuningTests(unittest.TestCase):
    """抓包调优参数：默认走缓冲批量，低延迟按需开启。"""

    def _engine(self, **kwargs) -> PcapCaptureEngine:
        return PcapCaptureEngine(PcapConfig(interface="dummy", **kwargs))

    def test_defaults_are_buffered_not_immediate(self):
        config = PcapConfig()
        self.assertFalse(config.low_latency, "默认不应开立即模式（CPU 高 5 倍）")
        self.assertGreaterEqual(config.buffer_mb, 16, "内核缓冲区应比 libpcap 默认值宽裕")

    def test_old_saved_config_still_loads(self):
        """旧版本保存的配置里没有新字段，反序列化不能报错。"""
        config = PcapConfig.from_dict({"interface": "eth0", "protocol": "modbus_tcp", "promisc": False})
        self.assertEqual(config.interface, "eth0")
        self.assertFalse(config.low_latency)
        self.assertEqual(config.buffer_mb, PcapConfig().buffer_mb)

    def test_stats_default_to_zero_before_capture(self):
        engine = self._engine()
        self.assertEqual(engine.kernel_dropped, 0)
        self.assertEqual(engine.delivered_count, 0)
        self.assertEqual(engine.parse_dropped, 0)
        self.assertEqual(engine.stats_summary(), "", "无丢包时不应显示")

    def test_stats_summary_reports_drops(self):
        engine = self._engine()
        engine._kernel_dropped = 42  # noqa: SLF001 - 直接设定以验证展示逻辑
        self.assertEqual(engine.stats_summary(), "丢包 42")

    def test_batch_constants_are_sane(self):
        """批处理间隔太大则界面迟滞，太小则退化成逐包唤醒。"""
        from packet_analyzer.core import pcap

        self.assertLessEqual(pcap.BATCH_TIMEOUT_MS, 50)
        self.assertGreaterEqual(pcap.BATCH_TIMEOUT_MS, 5)
        self.assertGreater(pcap.BATCH_PACKETS, 1)


@unittest.skipUnless(wpcap.is_available(), "未安装 Npcap/libpcap")
class BatchReadTests(unittest.TestCase):
    """``read_batch`` 的返回值形状与 pcap_stats 的可调用性。"""

    def test_read_batch_returns_typed_pairs(self):
        """返回值必须是 (float 时间戳, bytes) 列表；回环上可能已有背景流量，不假设为空。"""
        device = next((item.name for item in wpcap.list_devices() if item.is_loopback), "")
        if not device:
            self.skipTest("未找到回环网卡")
        handle = wpcap.PcapHandle(device, timeout_ms=20, buffer_mb=8)
        try:
            batch = handle.read_batch(16)
            self.assertIsInstance(batch, list)
            self.assertLessEqual(len(batch), 16, "单次 dispatch 不得超过请求的包数")
            for timestamp, data in batch:
                self.assertIsInstance(timestamp, float)
                self.assertIsInstance(data, bytes)
                self.assertGreater(len(data), 0)
            delivered, dropped = handle.stats()
            self.assertIsInstance(delivered, int)
            self.assertIsInstance(dropped, int)
            self.assertGreaterEqual(dropped, 0)
        finally:
            handle.close()

    def test_pcap_stat_struct_covers_windows_layout(self):
        """Npcap 写 6 个 u_int；结构体小于 24 字节会导致越界写。"""
        size = wpcap.ctypes.sizeof(wpcap._PcapStat)  # noqa: SLF001
        self.assertGreaterEqual(size, 24)


class InferRoleTests(unittest.TestCase):
    def test_infer_role_shared_by_capture_and_replay(self):
        from packet_analyzer.core.pcap import infer_role

        self.assertEqual(infer_role("10.0.0.5", 51000, "10.0.0.9", 502), registry.ROLE_REQUEST)
        self.assertEqual(infer_role("10.0.0.9", 502, "10.0.0.5", 51000), registry.ROLE_RESPONSE)

    def test_master_ip_takes_priority(self):
        from packet_analyzer.core.pcap import infer_role

        self.assertEqual(
            infer_role("10.0.0.1", 40000, "10.0.0.2", 502, master_ip="10.0.0.1"), registry.ROLE_REQUEST
        )

    def test_client_endpoint_wins_over_ports(self):
        from packet_analyzer.core.pcap import infer_role

        # 回环两侧 IP 相同，只能靠端点区分
        self.assertEqual(
            infer_role("127.0.0.1", 40000, "127.0.0.1", 502, client_endpoint=("127.0.0.1", 40000)),
            registry.ROLE_REQUEST,
        )
        self.assertEqual(
            infer_role("127.0.0.1", 502, "127.0.0.1", 40000, client_endpoint=("127.0.0.1", 40000)),
            registry.ROLE_RESPONSE,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
