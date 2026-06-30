"""Persistent storage-directory settings.

The configuration file itself always lives under ``ROOT_DIR/config`` so that
changing the data directory cannot make the settings file disappear.  Paths
may be entered as absolute paths or as paths relative to ``ROOT_DIR``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import ClassVar

from src.config.global_config import ROOT_DIR


@dataclass(frozen=True)
class StoragePaths:
    data_directory: str
    point_table_cache_directory: str
    iec61850_model_cache_directory: str
    iec61850_file_cache_directory: str
    iec61850_temp_directory: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class StorageSettings:
    """Load, validate and atomically persist storage paths."""

    PATH_FIELDS: ClassVar[tuple[str, ...]] = (
        "data_directory",
        "point_table_cache_directory",
        "iec61850_model_cache_directory",
        "iec61850_file_cache_directory",
        "iec61850_temp_directory",
    )

    def __init__(self, root_dir: str | Path = ROOT_DIR, config_file: str | Path | None = None):
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.config_file = (
            Path(config_file).expanduser().resolve()
            if config_file is not None
            else self.root_dir / "config" / "storage.json"
        )
        self._lock = threading.RLock()
        self._paths = self._load()

    def defaults(self) -> StoragePaths:
        data_dir = self.root_dir / "data"
        return StoragePaths(
            data_directory=str(data_dir),
            point_table_cache_directory=str(self.root_dir / "config" / "point_csv"),
            iec61850_model_cache_directory=str(data_dir / "61850icd"),
            iec61850_file_cache_directory=str(data_dir / "61850_cache"),
            iec61850_temp_directory=str(data_dir / "61850_temp"),
        )

    def get(self) -> StoragePaths:
        with self._lock:
            return self._paths

    def reload(self) -> StoragePaths:
        with self._lock:
            self._paths = self._load()
            return self._paths

    def update(self, values: dict[str, str]) -> tuple[StoragePaths, list[str]]:
        unknown = set(values) - set(self.PATH_FIELDS)
        if unknown:
            raise ValueError(f"未知的存储目录配置: {', '.join(sorted(unknown))}")

        with self._lock:
            current = self._paths.to_dict()
            normalized: dict[str, str] = {}
            for field_name in self.PATH_FIELDS:
                raw_value = values.get(field_name, current[field_name])
                normalized[field_name] = str(self._normalize_path(raw_value, field_name))

            for field_name, path_value in normalized.items():
                self._ensure_writable_directory(Path(path_value), field_name)

            changed_fields = [name for name in self.PATH_FIELDS if normalized[name] != current[name]]
            new_paths = StoragePaths(**normalized)
            self._save(new_paths)
            self._paths = new_paths
            return new_paths, changed_fields

    def directory_status(self, paths: StoragePaths | None = None) -> dict[str, dict[str, bool]]:
        selected = paths or self.get()
        result: dict[str, dict[str, bool]] = {}
        for field_name, value in selected.to_dict().items():
            path = Path(value)
            result[field_name] = {
                "exists": path.is_dir(),
                "writable": path.is_dir() and os.access(path, os.W_OK),
            }
        return result

    def _load(self) -> StoragePaths:
        defaults = self.defaults().to_dict()
        try:
            if self.config_file.is_file():
                raw = json.loads(self.config_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for field_name in self.PATH_FIELDS:
                        value = raw.get(field_name)
                        if isinstance(value, str) and value.strip():
                            defaults[field_name] = str(self._normalize_path(value, field_name))
        except (OSError, ValueError, json.JSONDecodeError):
            # A broken optional settings file must not prevent application startup.
            pass
        return StoragePaths(**defaults)

    def _save(self, paths: StoragePaths) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(paths.to_dict(), ensure_ascii=False, indent=2) + "\n"
        fd, temp_name = tempfile.mkstemp(
            prefix=".storage-",
            suffix=".tmp",
            dir=str(self.config_file.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file_obj:
                file_obj.write(payload)
                file_obj.flush()
                os.fsync(file_obj.fileno())
            os.replace(temp_name, self.config_file)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _normalize_path(self, value: str, field_name: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} 不能为空")
        expanded = Path(os.path.expandvars(value.strip())).expanduser()
        if not expanded.is_absolute():
            expanded = self.root_dir / expanded
        return expanded.resolve(strict=False)

    @staticmethod
    def _ensure_writable_directory(path: Path, field_name: str) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
            if not path.is_dir():
                raise ValueError(f"{field_name} 不是目录: {path}")
            fd, probe = tempfile.mkstemp(prefix=".ems-write-test-", dir=str(path))
            os.close(fd)
            os.unlink(probe)
        except (OSError, ValueError) as exc:
            raise ValueError(f"目录不可写: {path} ({exc})") from exc


_storage_settings = StorageSettings()


def get_storage_settings() -> StorageSettings:
    return _storage_settings


def get_storage_path(field_name: str) -> str:
    if field_name not in StorageSettings.PATH_FIELDS:
        raise KeyError(field_name)
    value = getattr(_storage_settings.get(), field_name)
    Path(value).mkdir(parents=True, exist_ok=True)
    return value
