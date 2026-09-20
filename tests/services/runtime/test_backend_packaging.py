from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize(
    ("mode", "bundle_config", "contents", "expects_config"),
    [
        ("onedir", None, "_internal", False),
        ("onedir", "0", "_internal", False),
        ("onedir", "1", "ems_simulate_backend_runtime", True),
        ("onefile", None, "_internal", True),
    ],
)
def test_backend_spec_config_placement(monkeypatch, mode, bundle_config, contents, expects_config):
    project = Path(__file__).resolve().parents[3]
    monkeypatch.setenv("EMS_PYINSTALLER_MODE", mode)
    monkeypatch.setenv("EMS_PYINSTALLER_CONTENTS_DIR", contents)
    monkeypatch.delenv("EMS_PYINSTALLER_BUNDLE_CONFIG", raising=False)
    if bundle_config is not None:
        monkeypatch.setenv("EMS_PYINSTALLER_BUNDLE_CONFIG", bundle_config)
    monkeypatch.setitem(sys.modules, "PyInstaller.utils.hooks", SimpleNamespace(collect_all=lambda name: ([], [], [])))
    analysis = MagicMock()
    collect = MagicMock()

    runpy.run_path(
        str(project / "ems_simulate_backend.spec"),
        init_globals={
            "SPECPATH": str(project),
            "Analysis": analysis,
            "PYZ": MagicMock(),
            "EXE": MagicMock(),
            "COLLECT": collect,
        },
    )

    data_files = analysis.call_args.kwargs["datas"]
    bundled_ini = [(source, target) for source, target in data_files if Path(source).suffix == ".ini"]
    assert bundled_ini == ([(str(project / "config.ini"), ".")] if expects_config else [])
    assert (str(project / "www"), "www") in data_files
    if mode == "onedir":
        collect.assert_called_once()
