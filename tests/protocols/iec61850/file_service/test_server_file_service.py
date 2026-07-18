"""Tests for the IEC 61850 server-side file store."""

from pathlib import Path
from types import SimpleNamespace

from pyiec61850 import pyiec61850 as iec61850

from src.proto.iec61850.iec61850_server import IEC61850Server
from src.proto.iec61850.plugins.files.server import ServerFileService
from src.proto.iec61850.plugins.files.transfer import FileTransfer
from src.proto.iec61850.plugins.files.types import TransferStatus


def test_server_file_service_crud_and_recursive_listing(tmp_path: Path):
    store = ServerFileService(tmp_path / "store")
    source = tmp_path / "source.cfg"
    source.write_bytes(b"relay-settings")

    assert store.upload_file(str(source), "/config/protection.cfg") is True
    assert store.get_file("/config/protection.cfg") == b"relay-settings"
    assert store.get_cached_file("/config/protection.cfg") == str(
        (tmp_path / "store" / "config" / "protection.cfg").resolve()
    )

    root_entries = store.list_directory("")
    assert [(entry["name"], entry["type"]) for entry in root_entries] == [("config", "directory")]

    nested_entries = store.list_directory_recursive("", max_depth=3)
    assert [(entry["full_path"], entry["type"]) for entry in nested_entries] == [
        ("/config", "directory"),
        ("/config/protection.cfg", "file"),
    ]
    file_entry = nested_entries[1]
    assert file_entry["size"] == len(b"relay-settings")
    assert file_entry["last_modified"] is not None

    assert store.delete_file("/config/protection.cfg") is True
    assert store.get_file("/config/protection.cfg") == b""
    assert store.delete_file("/config") is False


def test_explicit_device_directory_is_used_as_the_export_root(tmp_path: Path):
    selected_directory = tmp_path / "selected-ied-files"

    server = IEC61850Server(
        model_name="IED42",
        ied_name="IED42",
        file_service_directory=str(selected_directory),
    )

    assert server.files.base_directory == selected_directory.resolve()


def test_empty_device_directory_disables_file_service():
    server = IEC61850Server(model_name="IED-OFF", ied_name="IED-OFF", file_service_directory="")

    assert server.files is None


def test_server_file_service_rejects_paths_outside_store(tmp_path: Path):
    store = ServerFileService(tmp_path / "store")
    source = tmp_path / "source.txt"
    source.write_text("secret", encoding="utf-8")

    assert store.upload_file(str(source), "../escaped.txt") is False
    assert store.upload_file(str(source), "/safe/../../escaped.txt") is False
    assert store.get_file("../source.txt") == b""
    assert store.delete_file("../source.txt") is False
    assert not (tmp_path / "escaped.txt").exists()


def test_server_file_service_does_not_treat_authoritative_files_as_cache(tmp_path: Path):
    store = ServerFileService(tmp_path / "store")

    assert store.list_cached_files() == []
    assert store.clear_cache() == 0
    assert store._cache is None


def test_client_upload_passes_filestore_basepath_with_trailing_separator(tmp_path: Path, monkeypatch):
    source = tmp_path / "event.cfg"
    source.write_bytes(b"event")
    native_connection = object()
    connection = SimpleNamespace(is_connected=True, connection=native_connection)
    basepaths = []
    monkeypatch.setattr(
        iec61850,
        "IedConnection_setFilestoreBasepath",
        lambda conn, basepath: basepaths.append((conn, basepath)),
    )
    monkeypatch.setattr(
        iec61850,
        "IedConnection_setFile",
        lambda conn, source_name, destination_name: (None, iec61850.IED_ERROR_OK),
    )

    progress = FileTransfer(connection).upload_file(str(source), "/event.cfg")

    assert progress.status == TransferStatus.COMPLETED
    assert basepaths == [(native_connection, tmp_path.as_posix() + "/")]
