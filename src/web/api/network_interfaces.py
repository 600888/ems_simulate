"""本机网卡发现与 GOOSE 二层通信校验 API。"""

from __future__ import annotations

import re
import socket
from typing import Any

from fastapi import APIRouter

from src.web.api.exceptions import ValidationError
from src.web.api.schemas import BaseResponse

router = APIRouter(prefix="/api/network-interfaces", tags=["network-interfaces"])


def list_network_interfaces() -> list[dict[str, Any]]:
    """返回本机可用网卡列表。

    优先使用 psutil 获取友好名称（如"以太网"、"Wi-Fi"）及完整地址信息；
    psutil 不可用时退回 socket.if_nameindex，仅保证最基本的接口发现。
    """
    try:
        import psutil

        addresses = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        names = sorted(addresses.keys(), key=str.casefold)
    except ImportError:
        addresses = {}
        stats = {}
        names = [name for _, name in socket.if_nameindex()]

    # 匹配 xx:xx:xx:xx:xx:xx 或 xx-xx-xx-xx-xx-xx 两种格式
    _MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[-:]){5}[0-9A-Fa-f]{2}$")

    result: list[dict[str, Any]] = []
    for name in names:
        ipv4: list[str] = []
        ipv6: list[str] = []
        mac = ""
        for addr in addresses.get(name, []):
            if addr.family == socket.AF_INET:
                ipv4.append(addr.address)
            elif addr.family == socket.AF_INET6:
                ipv6.append(addr.address.split("%", 1)[0])
            elif _MAC_RE.match(addr.address or ""):
                mac = addr.address or ""
        stat = stats.get(name)
        is_up = bool(stat.isup) if stat is not None else True
        is_loopback = name.lower().startswith(("lo", "loopback")) or "127.0.0.1" in ipv4
        result.append(
            {
                "id": name,
                "name": name,
                "display_name": name,
                "mac": mac,
                "ipv4": ipv4,
                "ipv6": ipv6,
                "is_up": is_up,
                "is_loopback": is_loopback,
                "supports_raw_ethernet": bool(mac) and not is_loopback,
            }
        )
    return result


def validate_network_interface(interface_id: str) -> dict[str, Any]:
    item = next((item for item in list_network_interfaces() if item["id"] == interface_id), None)
    if item is None:
        raise ValidationError(f"网卡不存在: {interface_id}")
    if not item["is_up"]:
        raise ValidationError(f"网卡未启用: {interface_id}")
    if not item["supports_raw_ethernet"]:
        raise ValidationError(f"网卡不支持 GOOSE 二层通信: {interface_id}")
    return item


@router.get("")
async def get_network_interfaces():
    return BaseResponse(message="获取网卡列表成功", data={"items": list_network_interfaces()})


@router.post("/validate")
async def validate_interface(body: dict[str, str]):
    item = validate_network_interface(body.get("interface_id", ""))
    return BaseResponse(message="网卡可用", data=item)
