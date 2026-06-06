#!/usr/bin/env python3
"""将 pyproject.toml 中的版本号同步到其他配置文件。

用法:
    python scripts/sync_version.py          # 同步到所有配置文件
    python scripts/sync_version.py --check  # 仅检查是否一致，不修改

同步目标:
    - src-tauri/tauri.conf.json  → version
    - front/package.json         → version
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
TAURI_CONF_PATH = PROJECT_ROOT / "src-tauri" / "tauri.conf.json"
FRONT_PKG_PATH = PROJECT_ROOT / "front" / "package.json"


def get_pyproject_version() -> str:
    """从 pyproject.toml 读取版本号。"""
    import tomllib

    with PYPROJECT_PATH.open("rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def sync_json_file(filepath: Path, version: str, dry_run: bool = False) -> bool:
    """同步版本号到 JSON 配置文件，返回是否需要变更。"""
    with filepath.open("r", encoding="utf-8") as f:
        data = json.load(f)

    old_version = data.get("version", "")
    if old_version == version:
        print(f"  [OK] {filepath.relative_to(PROJECT_ROOT)}: already {version}")
        return False

    if dry_run:
        print(f"  [DRY-RUN] {filepath.relative_to(PROJECT_ROOT)}: {old_version} → {version}")
        return True

    data["version"] = version
    with filepath.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  [SYNCED] {filepath.relative_to(PROJECT_ROOT)}: {old_version} → {version}")
    return True


def main() -> None:
    dry_run = "--check" in sys.argv

    print(f"Source: pyproject.toml")

    version = get_pyproject_version()
    print(f"Version: {version}")
    print()

    targets = [TAURI_CONF_PATH, FRONT_PKG_PATH]
    changed = False

    for target in targets:
        if not target.exists():
            print(f"  [SKIP] {target.relative_to(PROJECT_ROOT)}: file not found")
            continue
        if sync_json_file(target, version, dry_run=dry_run):
            changed = True

    if dry_run and changed:
        print("\nVersion mismatch detected! Run without --check to sync.")
        sys.exit(1)
    elif not changed:
        print("\nAll versions are in sync.")


if __name__ == "__main__":
    main()
