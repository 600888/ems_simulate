"""Coordinate an in-process IEC 61850 server with bulk client RCB setup."""

from typing import Any

from src.device.protocol.iec61850_handler import IEC61850ServerHandler


def pause_matching_local_server_simulations(reports: Any, request: Any, log: Any) -> list[Any]:
    """Pause only the local server simulator targeted by a report client."""
    client = getattr(reports, "_client", None)
    target_ip = str(getattr(client, "ip", "") or "").strip().lower()
    target_port = int(getattr(client, "port", 0) or 0)
    if target_ip not in {"127.0.0.1", "localhost", "::1"} or target_port <= 0:
        return []

    paused: list[Any] = []
    controller = request.app.state.device_controller
    for device in controller.device_list:
        handler = getattr(device, "protocol_handler", None)
        if not isinstance(handler, IEC61850ServerHandler):
            continue
        server = getattr(handler, "_server", None)
        if not server or int(getattr(server, "port", 0) or 0) != target_port:
            continue
        simulation = getattr(device, "simulation_controller", None)
        if simulation is None or not simulation.is_simulation_running():
            continue
        # With hundreds of enabled RCBs, one server-side batch update can take
        # several seconds while libIEC61850 builds every report.  The normal
        # one-second UI stop timeout is therefore insufficient here: starting
        # RCB writes while that update is still finishing recreates the native
        # race this coordination is intended to prevent.
        if not simulation.stop_simulation(timeout=30.0):
            raise RuntimeError(
                f"本地 IEC61850 服务端模拟未能在 30 秒内停止: device={getattr(device, 'name', '')}, port={target_port}"
            )
        paused.append(simulation)
        log.info(
            f"批量配置报告期间已暂停匹配的本地 IEC61850 服务端模拟: "
            f"device={getattr(device, 'name', '')}, port={target_port}"
        )
    return paused


def resume_local_server_simulations(simulations: list[Any], log: Any) -> None:
    """Restart every simulator paused for bulk RCB setup."""
    for simulation in simulations:
        try:
            simulation.start_simulation()
        except Exception as exc:
            log.error(f"恢复本地 IEC61850 服务端模拟失败: {exc}", exc_info=True)
