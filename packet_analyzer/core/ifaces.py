"""本机网卡枚举（基于 libpcap/Npcap，无第三方依赖）。

设备清单、地址、链路类型都直接来自 ``pcap_findalldevs``，
再借 psutil 把 IP 映射成 Windows 的中文连接名（如"以太网"），
仅用于展示；没有 psutil 时退化为硬件描述。
"""

from __future__ import annotations

from dataclasses import dataclass
import socket

from . import wpcap

# 这些是系统虚拟层，不是可抓包的物理网卡
_EXCLUDED_KEYWORDS = (
    "wan miniport",
    "wfp ",
    "qos packet scheduler",
    "lightweight filter",
    "native mac layer",
    "kernel debug",
)


@dataclass(frozen=True)
class Interface:
    """一块可抓包网卡。"""

    id: str
    name: str
    description: str
    ipv4: tuple[str, ...] = ()
    ipv6: tuple[str, ...] = ()
    is_loopback: bool = False

    @property
    def label(self) -> str:
        """下拉框展示文本：连接名 · IPv4 · 硬件描述。"""
        parts = [self.name]
        parts.append("/".join(self.ipv4) if self.ipv4 else "无 IPv4")
        if self.description and self.description.casefold() != self.name.casefold():
            parts.append(self.description)
        return "  ·  ".join(parts)


def _is_virtual_filter(name: str, description: str) -> bool:
    haystack = f"{name} {description}".lower()
    return any(keyword in haystack for keyword in _EXCLUDED_KEYWORDS)


def _friendly_names_by_ip() -> dict[str, str]:
    """用 psutil 建 IP → 连接名 的映射，把"以太网"这类名称补上。"""
    try:
        import psutil
    except ImportError:
        return {}
    try:
        addresses = psutil.net_if_addrs()
    except (OSError, RuntimeError):
        return {}
    mapping: dict[str, str] = {}
    for name, items in addresses.items():
        for item in items:
            if item.family == socket.AF_INET and item.address:
                mapping.setdefault(item.address, name)
    return mapping


def list_interfaces() -> list[Interface]:
    """列出本机可抓包网卡；有 IPv4 的、非虚拟的排前面。"""
    try:
        devices = wpcap.list_devices()
    except wpcap.PcapError:
        return _fallback_interfaces()

    friendly = _friendly_names_by_ip()
    interfaces: list[Interface] = []
    for device in devices:
        if _is_virtual_filter(device.name, device.description):
            continue
        name = ""
        for address in device.ipv4:
            name = friendly.get(address, "")
            if name:
                break
        if not name:
            name = "本机回环" if device.is_loopback else (device.description or device.name)
        interfaces.append(
            Interface(
                id=device.name,
                name=name,
                description=device.description,
                ipv4=device.ipv4,
                ipv6=device.ipv6,
                is_loopback=device.is_loopback,
            )
        )

    def sort_key(item: Interface) -> tuple[int, int, int, str]:
        return (
            0 if item.ipv4 else 1,
            1 if item.is_loopback else 0,
            1 if "virtual" in item.description.lower() else 0,
            item.name.casefold(),
        )

    return sorted(interfaces, key=sort_key)


def _fallback_interfaces() -> list[Interface]:
    """没有 Npcap 时仍给出可读列表（抓包会在启动阶段明确报错）。"""
    try:
        import psutil

        addresses = psutil.net_if_addrs()
    except (ImportError, OSError, RuntimeError):
        return []
    result: list[Interface] = []
    for name, items in addresses.items():
        if _is_virtual_filter(name, ""):
            continue
        ipv4 = tuple(item.address for item in items if item.family == socket.AF_INET)
        ipv6 = tuple(item.address.split("%", 1)[0] for item in items if item.family == socket.AF_INET6)
        result.append(
            Interface(
                id=name,
                name=name,
                description="",
                ipv4=ipv4,
                ipv6=ipv6,
                is_loopback=name.lower().startswith(("lo", "loopback")) or "127.0.0.1" in ipv4,
            )
        )
    return result


def find_interface(interface_id: str) -> Interface | None:
    return next((item for item in list_interfaces() if item.id == interface_id), None)


def local_addresses() -> set[str]:
    """本机所有 IPv4 地址，用于判断报文是发出（TX）还是收到（RX）。"""
    addresses = {ip for item in list_interfaces() for ip in item.ipv4}
    addresses.update({"127.0.0.1", "0.0.0.0"})
    return addresses


def capture_available() -> tuple[bool, str]:
    """检查网卡抓包是否具备条件，返回 (可用, 说明)。"""
    if not wpcap.is_available():
        return False, wpcap.availability_error()
    return True, ""


def capture_runtime_info() -> str:
    """一行环境信息，显示在抓包设置里。"""
    if not wpcap.is_available():
        return wpcap.availability_error()
    return wpcap.libpcap_version()
