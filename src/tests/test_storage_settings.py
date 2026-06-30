import json
from pathlib import Path

import pytest

from src.config.storage import StorageSettings


def test_storage_settings_defaults_are_root_relative(tmp_path: Path):
    settings = StorageSettings(root_dir=tmp_path)
    paths = settings.get()

    assert paths.data_directory == str(tmp_path / "data")
    assert paths.point_table_cache_directory == str(tmp_path / "config" / "point_csv")
    assert paths.iec61850_model_cache_directory == str(tmp_path / "data" / "61850icd")
    assert paths.iec61850_file_cache_directory == str(tmp_path / "data" / "61850_cache")
    assert paths.iec61850_temp_directory == str(tmp_path / "data" / "61850_temp")


def test_storage_settings_update_creates_and_persists_directories(tmp_path: Path):
    config_file = tmp_path / "config" / "storage.json"
    settings = StorageSettings(root_dir=tmp_path, config_file=config_file)
    values = {
        "data_directory": "custom/data",
        "point_table_cache_directory": "custom/points",
        "iec61850_model_cache_directory": "custom/models",
        "iec61850_file_cache_directory": "custom/files",
        "iec61850_temp_directory": "custom/temp",
    }

    paths, changed = settings.update(values)

    assert set(changed) == set(StorageSettings.PATH_FIELDS)
    assert all(Path(value).is_dir() for value in paths.to_dict().values())
    assert json.loads(config_file.read_text(encoding="utf-8")) == paths.to_dict()
    assert StorageSettings(root_dir=tmp_path, config_file=config_file).get() == paths


def test_storage_settings_rejects_a_file_as_directory(tmp_path: Path):
    invalid_path = tmp_path / "not-a-directory"
    invalid_path.write_text("file", encoding="utf-8")
    settings = StorageSettings(root_dir=tmp_path)

    with pytest.raises(ValueError, match="目录不可写"):
        settings.update({"data_directory": str(invalid_path)})
