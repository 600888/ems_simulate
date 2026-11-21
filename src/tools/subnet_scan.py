"""Bounded IPv4 subnet discovery using the operating system's ping command."""

import asyncio
from dataclasses import dataclass, field
from ipaddress import IPv4Network
import math
import re
import subprocess
import sys
import time
from uuid import uuid4


def parse_subnet(value: str) -> IPv4Network:
    value = value.strip()
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){2}", value):
        value += ".0/24"
    try:
        network = IPv4Network(value, strict=False)
    except ValueError as exc:
        raise ValueError("请输入有效的 IPv4 子网，例如 192.168.1 或 192.168.1.0/24") from exc
    if network.prefixlen < 24:
        raise ValueError("每次最多探测一个 /24 子网（254 个地址），请使用 /24 到 /32 的子网")
    if network.network_address.is_multicast or network.network_address.is_unspecified:
        raise ValueError("请输入有效的单播 IPv4 子网")
    return network


async def ping_host(ip: str, timeout_ms: int) -> dict:
    """Require an echo reply (TTL), since Windows can return 0 for unreachable replies."""
    if sys.platform == "win32":
        args = ["ping", "-4", "-n", "1", "-w", str(timeout_ms), ip]
    else:
        timeout = timeout_ms if sys.platform == "darwin" else math.ceil(timeout_ms / 1000)
        args = ["ping", "-n", "-c", "1", "-W", str(timeout), ip]
    # The application uses SelectorEventLoop for MQTT on Windows, where asyncio
    # subprocess transports are unavailable. Drain pipes in a worker thread.
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}),
    )
    communication = asyncio.create_task(asyncio.to_thread(process.communicate, timeout=timeout_ms / 1000 + 1.5))
    try:
        try:
            output, error = await asyncio.shield(communication)
        except subprocess.TimeoutExpired:
            return {"ip": ip, "reachable": False, "latency_ms": None}
        if process.returncode not in (0, 1):
            reason = error.decode(errors="replace").strip() or output.decode(errors="replace").strip()
            raise RuntimeError(reason or f"ping exited with code {process.returncode}")
        reachable = process.returncode == 0 and re.search(rb"ttl[=\s:]\s*\d+", output, re.I) is not None
        latency = re.search(rb"([=<])\s*(\d+(?:[.,]\d+)?)\s*ms", output, re.I) if reachable else None
        return {
            "ip": ip,
            "reachable": reachable,
            "latency_ms": float(latency[2].replace(b",", b".")) if latency else None,
        }
    finally:
        # Stop also terminates in-flight child processes, including on service shutdown.
        if process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        outcome = await asyncio.gather(communication, return_exceptions=True)
        if isinstance(outcome[0], subprocess.TimeoutExpired):
            await asyncio.to_thread(process.communicate)


@dataclass
class SubnetScan:
    id: str
    subnet: str
    total: int
    status: str = "running"
    results: list[dict] = field(default_factory=list)
    error: str | None = None
    finished_at: float | None = None
    task: asyncio.Task | None = None

    def snapshot(self) -> dict:
        reachable = sum(row["reachable"] for row in self.results)
        return {
            "id": self.id,
            "subnet": self.subnet,
            "total": self.total,
            "completed": len(self.results),
            "reachable": reachable,
            "unreachable": len(self.results) - reachable,
            "status": self.status,
            "error": self.error,
            "results": sorted(self.results, key=lambda row: tuple(map(int, row["ip"].split(".")))),
        }


class SubnetScanner:
    def __init__(self):
        self.scans: dict[str, SubnetScan] = {}

    def start(self, subnet: str, timeout_ms: int) -> SubnetScan:
        network = parse_subnet(subnet)
        for scan_id, scan in list(self.scans.items()):
            if scan.finished_at is not None and time.monotonic() - scan.finished_at > 600:
                del self.scans[scan_id]
        if sum(scan.status == "running" for scan in self.scans.values()) >= 4:
            raise ValueError("同时最多运行 4 个探测任务，请等待已有任务完成")
        # Retain a bounded number of recent results, even during frequent rescans.
        finished = [scan for scan in self.scans.values() if scan.finished_at is not None]
        for scan in sorted(finished, key=lambda item: item.finished_at or 0)[: max(0, len(self.scans) - 15)]:
            del self.scans[scan.id]
        hosts = [str(ip) for ip in network.hosts()]
        scan = SubnetScan(id=uuid4().hex, subnet=str(network), total=len(hosts))
        self.scans[scan.id] = scan
        scan.task = asyncio.create_task(self._run(scan, hosts, timeout_ms), name=f"subnet-scan-{scan.id}")
        return scan

    async def _run(self, scan: SubnetScan, hosts: list[str], timeout_ms: int):
        semaphore = asyncio.Semaphore(32)

        async def probe(ip: str):
            async with semaphore:
                scan.results.append(await ping_host(ip, timeout_ms))

        tasks = [asyncio.create_task(probe(ip)) for ip in hosts]
        try:
            await asyncio.gather(*tasks)
            scan.status = "completed"
        except asyncio.CancelledError:
            scan.status = "cancelled"
            raise
        except Exception as exc:
            scan.status = "failed"
            scan.error = str(exc)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            scan.finished_at = time.monotonic()

    async def cancel(self, scan: SubnetScan):
        if scan.task is not None and not scan.task.done():
            scan.task.cancel()
            await asyncio.gather(scan.task, return_exceptions=True)
            # Cancellation may precede the task's first execution.
            if scan.status == "running":
                scan.status = "cancelled"
                scan.finished_at = time.monotonic()

    async def close(self):
        await asyncio.gather(*(self.cancel(scan) for scan in self.scans.values()))
