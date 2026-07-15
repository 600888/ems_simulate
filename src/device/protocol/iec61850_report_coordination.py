"""Coordinate in-process IEC 61850 server simulation and client RCB operations."""

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
        # an RCB operation while that update is still finishing recreates the
        # native race this coordination is intended to prevent.
        if not simulation.stop_simulation(timeout=30.0):
            raise RuntimeError(
                f"本地 IEC61850 服务端模拟未能在 30 秒内停止: device={getattr(device, 'name', '')}, port={target_port}"
            )
        paused.append(simulation)
        log.info(
            f"报告控制操作期间已暂停匹配的本地 IEC61850 服务端模拟: "
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


def trigger_gi_with_local_server_coordination(
    reports: Any,
    rcb_ref: str,
    request: Any,
    log: Any,
    *,
    report_timeout: float = 3.0,
) -> bool:
    """Trigger GI without racing an in-process server simulation batch.

    A local server update and a client report callback share the Python
    process but run on different native threads.  Keeping the simulator
    paused until the GI report has been copied into Python-owned cache avoids
    concurrent access to libIEC61850/SWIG report objects.
    """
    paused = pause_matching_local_server_simulations(reports, request, log)
    try:
        state_getter = getattr(reports, "get_report_data_state", None)
        previous_uid = 0
        if paused and callable(state_getter):
            _, previous_uid = state_getter(rcb_ref)

        success = bool(reports.trigger_gi(rcb_ref=rcb_ref))
        if not success or not paused:
            return success

        wait_for_report = getattr(reports, "wait_for_report_after", None)
        if callable(wait_for_report) and not wait_for_report(rcb_ref, previous_uid, timeout=report_timeout):
            log.warning(f"GI 已触发但等待报告回调超时: ref={rcb_ref}, timeout={report_timeout:.1f}s")
        return True
    finally:
        resume_local_server_simulations(paused, log)
