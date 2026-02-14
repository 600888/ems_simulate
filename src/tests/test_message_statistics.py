"""
测试 MessageCapture 的平均收发时间统计功能

平均收发时间 = TX→RX 配对的平均延迟（请求到响应的耗时）
"""
import time
import pytest
from src.device.core.message.message_capture import MessageCapture


def test_empty_statistics():
    """空状态下统计值应为零"""
    capture = MessageCapture()
    stats = capture.get_avg_time()

    assert stats["tx_count"] == 0
    assert stats["rx_count"] == 0
    assert stats["total_count"] == 0
    assert stats["pair_count"] == 0
    assert stats["avg_latency_ms"] == 0.0


def test_tx_only_no_pair():
    """只有 TX 没有 RX 时，不应有配对"""
    capture = MessageCapture()
    capture.add_tx(b"\x01\x03\x00\x00\x00\x01")

    stats = capture.get_avg_time()
    assert stats["tx_count"] == 1
    assert stats["rx_count"] == 0
    assert stats["pair_count"] == 0
    assert stats["avg_latency_ms"] == 0.0


def test_single_tx_rx_pair():
    """一对 TX→RX 应正确计算延迟"""
    capture = MessageCapture()
    capture.add_tx(b"\x01\x03\x00\x00\x00\x01")
    time.sleep(0.05)  # 50ms
    capture.add_rx(b"\x01\x03\x02\x00\x64")

    stats = capture.get_avg_time()
    assert stats["tx_count"] == 1
    assert stats["rx_count"] == 1
    assert stats["pair_count"] == 1
    # 延迟应接近 50ms（允许误差）
    assert 30 < stats["avg_latency_ms"] < 100


def test_multiple_pairs():
    """多对 TX→RX 应取平均延迟"""
    capture = MessageCapture()

    # 第一对：约 50ms
    capture.add_tx(b"\x01")
    time.sleep(0.05)
    capture.add_rx(b"\x02")

    # 第二对：约 50ms
    capture.add_tx(b"\x03")
    time.sleep(0.05)
    capture.add_rx(b"\x04")

    stats = capture.get_avg_time()
    assert stats["pair_count"] == 2
    assert 30 < stats["avg_latency_ms"] < 100


def test_rx_without_pending_tx():
    """RX 没有待配对的 TX 时，不应计入配对"""
    capture = MessageCapture()

    # 先来 RX（无 TX 配对）
    capture.add_rx(b"\x01")

    stats = capture.get_avg_time()
    assert stats["rx_count"] == 1
    assert stats["pair_count"] == 0


def test_duplicate_rx_only_pairs_once():
    """一条 TX 后跟两条 RX，只配对第一条 RX"""
    capture = MessageCapture()

    capture.add_tx(b"\x01")
    time.sleep(0.05)
    capture.add_rx(b"\x02")  # 配对成功
    capture.add_rx(b"\x03")  # 不配对

    stats = capture.get_avg_time()
    assert stats["pair_count"] == 1


def test_clear_resets_statistics():
    """clear() 应重置所有统计数据"""
    capture = MessageCapture()
    capture.add_tx(b"\x01")
    time.sleep(0.01)
    capture.add_rx(b"\x02")

    # 确保有数据
    stats = capture.get_avg_time()
    assert stats["pair_count"] == 1

    # 清空后应重置
    capture.clear()
    stats = capture.get_avg_time()
    assert stats["tx_count"] == 0
    assert stats["rx_count"] == 0
    assert stats["pair_count"] == 0
    assert stats["avg_latency_ms"] == 0.0


def test_disabled_capture_no_statistics():
    """禁用状态下不应累计统计"""
    capture = MessageCapture()
    capture.disable()

    capture.add_tx(b"\x01")
    capture.add_rx(b"\x02")

    stats = capture.get_avg_time()
    assert stats["tx_count"] == 0
    assert stats["rx_count"] == 0
    assert stats["pair_count"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
