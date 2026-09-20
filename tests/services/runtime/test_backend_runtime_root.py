from pathlib import Path
import sys

import pytest

from src.config.config import Config, resolve_config_path
import start_back_end


def _create_bundle(bundle_dir: Path, database: bytes = b"seed database") -> None:
    (bundle_dir / "data" / "point_csv").mkdir(parents=True)
    (bundle_dir / "config.ini").write_text("[database]\ntype = sqlite\n", encoding="utf-8")
    (bundle_dir / "data" / "ems.db").write_bytes(database)
    (bundle_dir / "data" / "point_csv" / "example.csv").write_text(
        "name,value\nexample,1\n",
        encoding="utf-8",
    )


def test_prepare_runtime_root_copies_bundled_seed_on_first_run(tmp_path, monkeypatch):
    bundle_dir = tmp_path / "bundle"
    runtime_dir = tmp_path / "runtime"
    _create_bundle(bundle_dir)
    monkeypatch.setattr(start_back_end, "_bundled_path", lambda name: bundle_dir / name)

    start_back_end._prepare_runtime_root(runtime_dir)

    assert (runtime_dir / "config.ini").is_file()
    assert (runtime_dir / "data" / "ems.db").read_bytes() == b"seed database"
    assert (runtime_dir / "data" / "point_csv" / "example.csv").is_file()
    for directory in ("log", "config", "upload", "plan"):
        assert (runtime_dir / directory).is_dir()


def test_prepare_runtime_root_preserves_existing_user_database(tmp_path, monkeypatch):
    bundle_dir = tmp_path / "bundle"
    runtime_dir = tmp_path / "runtime"
    _create_bundle(bundle_dir, database=b"new bundled database")
    (runtime_dir / "data").mkdir(parents=True)
    user_database = runtime_dir / "data" / "ems.db"
    user_database.write_bytes(b"existing user database")
    monkeypatch.setattr(start_back_end, "_bundled_path", lambda name: bundle_dir / name)

    start_back_end._prepare_runtime_root(runtime_dir)

    assert user_database.read_bytes() == b"existing user database"


def test_prepare_runtime_root_recovers_empty_database(tmp_path, monkeypatch):
    bundle_dir = tmp_path / "bundle"
    runtime_dir = tmp_path / "runtime"
    _create_bundle(bundle_dir)
    (runtime_dir / "data").mkdir(parents=True)
    empty_database = runtime_dir / "data" / "ems.db"
    empty_database.touch()
    monkeypatch.setattr(start_back_end, "_bundled_path", lambda name: bundle_dir / name)

    start_back_end._prepare_runtime_root(runtime_dir)

    assert empty_database.read_bytes() == b"seed database"
    assert not empty_database.with_suffix(".db.tmp").exists()


def test_prepare_runtime_root_allows_missing_optional_seed_database(tmp_path, monkeypatch):
    bundle_dir = tmp_path / "bundle"
    runtime_dir = tmp_path / "runtime"
    _create_bundle(bundle_dir)
    (bundle_dir / "data" / "ems.db").unlink()
    monkeypatch.setattr(start_back_end, "_bundled_path", lambda name: bundle_dir / name)

    start_back_end._prepare_runtime_root(runtime_dir)

    # DbController creates the SQLite file and schema when the application is
    # imported; runtime-root preparation must not require a prebuilt database.
    assert not (runtime_dir / "data" / "ems.db").exists()


def test_runtime_config_uses_root_config_before_legacy_etc_config(tmp_path):
    root_config = tmp_path / "config.ini"
    legacy_config = tmp_path / "etc" / "config.ini"
    legacy_config.parent.mkdir()
    root_config.write_text("[server]\nport = 9101\n", encoding="utf-8")
    legacy_config.write_text("[server]\nport = 9102\n", encoding="utf-8")

    assert resolve_config_path(tmp_path) == root_config


def test_runtime_config_falls_back_to_legacy_etc_config(tmp_path):
    legacy_config = tmp_path / "etc" / "config.ini"
    legacy_config.parent.mkdir()
    legacy_config.write_text("[server]\nport = 9102\n", encoding="utf-8")

    assert resolve_config_path(tmp_path) == legacy_config


def test_activate_runtime_config_loads_web_host_and_port(tmp_path, monkeypatch):
    (tmp_path / "config.ini").write_text(
        "[server]\nhost = 0.0.0.0\nport = 9103\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Config, "web_host", "127.0.0.1")
    monkeypatch.setattr(Config, "web_port", 8991)
    monkeypatch.delenv("EMS_ROOT_DIR", raising=False)

    loaded_config = start_back_end._activate_runtime_config(tmp_path)

    assert loaded_config.web_host == "0.0.0.0"
    assert loaded_config.web_port == 9103
    assert Path(start_back_end.os.environ["EMS_ROOT_DIR"]) == tmp_path.resolve()


def test_cli_port_is_optional_so_config_port_can_take_effect(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["start_back_end.py"])

    args = start_back_end._parse_args()

    assert args.port is None


@pytest.mark.parametrize("bundle_name", ["_internal", "_MEI12345"])
def test_frozen_backend_loads_config_beside_executable(tmp_path, monkeypatch, bundle_name):
    package = tmp_path / "package"
    bundle = package / bundle_name
    _create_bundle(bundle)
    (bundle / "config.ini").write_text("[server]\nport = 9101\n", encoding="utf-8")
    root_config = "[server]\nhost = 0.0.0.0\nport = 9104\n[database]\ntype = mysql\n"
    (package / "config.ini").write_text(root_config, encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(package / "ems_simulate"))
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setattr(start_back_end, "__file__", str(bundle / "start_back_end.py"))
    monkeypatch.delenv("EMS_ROOT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Config, "web_host", "127.0.0.1")
    monkeypatch.setattr(Config, "web_port", 8991)
    monkeypatch.setattr(Config, "db_type", "sqlite")

    root = start_back_end._get_root_dir(None)
    start_back_end._prepare_runtime_root(root)
    loaded = start_back_end._activate_runtime_config(root)

    assert root == package
    assert loaded.web_host == "0.0.0.0"
    assert loaded.web_port == 9104
    assert loaded.db_type == "mysql"
    assert (package / "config.ini").read_text(encoding="utf-8") == root_config
    assert (package / "data" / "point_csv" / "example.csv").is_file()


def test_frozen_backend_seeds_custom_root_from_external_config(tmp_path, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    config_text = "[server]\nport = 9105\n"
    (package / "config.ini").write_text(config_text, encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(package / "ems_simulate"))
    monkeypatch.setattr(sys, "_MEIPASS", str(package / "_internal"), raising=False)

    runtime = tmp_path / "runtime"
    start_back_end._prepare_runtime_root(runtime)

    assert (runtime / "config.ini").read_text(encoding="utf-8") == config_text
    (runtime / "config.ini").write_text("user configuration", encoding="utf-8")
    start_back_end._prepare_runtime_root(runtime)
    assert (runtime / "config.ini").read_text(encoding="utf-8") == "user configuration"


def test_runtime_root_preserves_environment_and_cli_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "package" / "ems_simulate"))
    monkeypatch.setenv("EMS_ROOT_DIR", str(tmp_path / "environment"))

    assert start_back_end._get_root_dir(str(tmp_path / "cli")) == tmp_path / "environment"
    monkeypatch.delenv("EMS_ROOT_DIR")
    assert start_back_end._get_root_dir(str(tmp_path / "cli")) == tmp_path / "cli"


def test_source_runtime_root_uses_script_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("EMS_ROOT_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(start_back_end, "__file__", str(tmp_path / "start_back_end.py"))

    assert start_back_end._get_root_dir(None) == tmp_path
