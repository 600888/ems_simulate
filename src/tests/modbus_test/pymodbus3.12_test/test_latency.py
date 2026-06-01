import time
import unittest

from src.device.core.message.message_capture import MessageCapture


class TestMessageCaptureLatency(unittest.TestCase):
    def setUp(self):
        self.capture = MessageCapture()

    def test_client_mode_latency(self):
        """Test Client Mode: TX -> RX"""
        print("\nTesting Client Mode (TX -> RX)...")
        # TX
        self.capture.add_tx(b"\x01\x03\x00\x00\x00\x01")
        time.sleep(0.1)
        # RX
        self.capture.add_rx(b"\x01\x03\x02\x00\x00")

        stats = self.capture.get_avg_time()
        print(f"Client Stats: {stats}")
        self.assertEqual(stats["pair_count"], 1)
        self.assertAlmostEqual(stats["avg_latency_ms"], 100, delta=20)  # Allow some tolerance

    def test_server_mode_latency(self):
        """Test Server Mode: RX -> TX"""
        print("\nTesting Server Mode (RX -> TX)...")
        self.capture.clear()

        # RX
        self.capture.add_rx(b"\x01\x03\x00\x00\x00\x01")
        time.sleep(0.1)
        # TX
        self.capture.add_tx(b"\x01\x03\x02\x00\x00")

        stats = self.capture.get_avg_time()
        print(f"Server Stats: {stats}")
        self.assertEqual(stats["pair_count"], 1)
        self.assertAlmostEqual(stats["avg_latency_ms"], 100, delta=20)

    def test_mixed_mode(self):
        """Test Mixed Mode (should not interfere)"""
        print("\nTesting Mixed Mode...")
        self.capture.clear()

        # Client TX -> wait -> RX
        self.capture.add_tx(b"REQ1")
        time.sleep(0.05)
        self.capture.add_rx(b"RESP1")

        # Server RX -> wait -> TX
        self.capture.add_rx(b"REQ2")
        time.sleep(0.05)
        self.capture.add_tx(b"RESP2")

        stats = self.capture.get_avg_time()
        print(f"Mixed Stats: {stats}")
        self.assertEqual(stats["pair_count"], 2)
        self.assertAlmostEqual(stats["avg_latency_ms"], 50, delta=10)


if __name__ == "__main__":
    unittest.main()
