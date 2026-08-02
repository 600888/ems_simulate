import os
from pathlib import Path
import subprocess
import sys


def test_dlt645_logs_are_redirected_to_runtime_root(tmp_path):
    runtime_root = tmp_path / "runtime"
    env = os.environ.copy()
    env["EMS_ROOT_DIR"] = str(runtime_root)

    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from src.device.protocol.dlt645_compat import "
                "AsyncMeterClientService, AsyncMeterServerService; "
                "from dlt645.common.base_log import configure_logging; "
                "configure_logging(enabled=True); "
                "import dlt645.model.log, dlt645.protocol.log; "
                "import dlt645.transport.client.log, dlt645.transport.server.log; "
                "import dlt645.service.clientsvc.log, dlt645.service.serversvc.log; "
                "dlt645.model.log.log.info('p'); dlt645.protocol.log.log.info('p'); "
                "dlt645.transport.client.log.log.info('p'); "
                "dlt645.transport.server.log.log.info('p'); "
                "dlt645.service.clientsvc.log.log.info('p'); "
                "dlt645.service.serversvc.log.log.info('p'); "
                "assert AsyncMeterClientService; assert AsyncMeterServerService"
            ),
        ],
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert probe.returncode == 0, probe.stderr
    dlt645_log_dir = runtime_root / "log" / "dlt645"
    assert dlt645_log_dir.is_dir()
    assert {
        "client.log",
        "clientsvc.log",
        "data.log",
        "protocol.log",
        "server.log",
        "serversvc.log",
    }.issubset(path.name for path in dlt645_log_dir.iterdir())
