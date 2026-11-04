"""抓包引擎回归：本机回环验证客户端/服务端两种模式。"""

import json
from pathlib import Path
import socket
import sys
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from packet_analyzer.core.capture import CaptureConfig, CaptureEngine  # noqa: E402

SAMPLES = json.loads((ROOT / "samples" / "samples.json").read_text(encoding="utf-8"))


def raw_of(key: str, name: str = "request") -> bytes:
    return bytes.fromhex(SAMPLES[key][name].replace(" ", ""))


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class CaptureEngineTests(unittest.TestCase):
    def test_client_mode_receives_and_splits_frames(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        request, response = raw_of("modbus_tcp"), raw_of("modbus_tcp", "response")

        def serve():
            conn, _ = server.accept()
            conn.sendall(request + response)
            time.sleep(0.3)
            conn.close()
            server.close()

        threading.Thread(target=serve, daemon=True).start()
        received: list[bytes] = []
        engine = CaptureEngine(
            CaptureConfig(host="127.0.0.1", port=port, protocol="modbus_tcp"),
            on_frame=lambda raw, _direction, _meta: received.append(raw),
        )
        engine.start()
        deadline = time.time() + 3
        while time.time() < deadline and len(received) < 2:
            time.sleep(0.02)
        engine.stop()
        self.assertEqual(received, [request, response])

    def test_server_mode_accepts_device_connection(self):
        port = free_port()
        received: list[tuple[bytes, str]] = []
        engine = CaptureEngine(
            CaptureConfig(mode="server", host="127.0.0.1", port=port, protocol="iec104"),
            on_frame=lambda raw, direction, _meta: received.append((raw, direction)),
        )
        engine.start()
        deadline = time.time() + 3
        while time.time() < deadline:
            try:
                client = socket.create_connection(("127.0.0.1", port), timeout=0.5)
                break
            except OSError:
                time.sleep(0.05)
        else:
            self.fail("监听端口未就绪")
        frame = raw_of("iec104")
        client.sendall(frame)
        time.sleep(0.3)
        client.close()
        engine.stop()
        self.assertIn((frame, "RX"), received)

    def test_poll_frame_is_reported_as_tx(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        poll = raw_of("modbus_tcp")
        received: list[tuple[bytes, str]] = []
        got_poll = threading.Event()

        def serve():
            conn, _ = server.accept()
            conn.settimeout(2)
            try:
                conn.recv(1024)
                got_poll.set()
            except OSError:
                pass
            conn.close()
            server.close()

        threading.Thread(target=serve, daemon=True).start()
        engine = CaptureEngine(
            CaptureConfig(
                host="127.0.0.1",
                port=port,
                protocol="modbus_tcp",
                poll_hex=poll.hex(),
                poll_interval=0.2,
            ),
            on_frame=lambda raw, direction, _meta: received.append((raw, direction)),
        )
        engine.start()
        got_poll.wait(3)
        engine.stop()
        self.assertTrue(any(item == (poll, "TX") for item in received))


if __name__ == "__main__":
    unittest.main(verbosity=2)
