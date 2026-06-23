#!/usr/bin/env python3
"""将 pyproject.toml 中的版本号同步到其他配置文件。

用法:
    python scripts/sync_version.py          # 同步到所有配置文件
    python scripts/sync_version.py --check  # 仅检查是否一致，不修改

同步目标:
    - src-tauri/tauri.conf.json  → version
    - src-tauri/Cargo.toml       → [package].version (Tauri 应用版本)
    - front/package.json         → version
    - Package.appxmanifest       → Version (MSIX, 4段式, 追加 .0)
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
TAURI_CONF_PATH = PROJECT_ROOT / "src-tauri" / "tauri.conf.json"
CARGO_TOML_PATH = PROJECT_ROOT / "src-tauri" / "Cargo.toml"
FRONT_PKG_PATH = PROJECT_ROOT / "front" / "package.json"
MSIX_MANIFEST_PATH = PROJECT_ROOT / "Package.appxmanifest"


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
        print(f"  [DRY-RUN] {filepath.relative_to(PROJECT_ROOT)}: {old_version} -> {version}")
        return True

    data["version"] = version
    with filepath.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  [SYNCED] {filepath.relative_to(PROJECT_ROOT)}: {old_version} -> {version}")
    return True


def sync_msix_manifest(filepath: Path, version: str, dry_run: bool = False) -> bool:
    """同步版本号到 MSIX Package.appxmanifest (XML) 文件，返回是否需要变更。

    MSIX 版本格式为 major.minor.build.revision (4 段)，
    从 pyproject 的 x.y.z 映射为 x.y.z.0。
    """
    msix_version = f"{version}.0" if version.count(".") == 2 else version

    with filepath.open("r", encoding="utf-8") as f:
        content = f.read()

    match = re.search(r'Version="(\d+\.\d+\.\d+\.\d+)"', content)
    if not match:
        print(f"  [ERROR] {filepath.relative_to(PROJECT_ROOT)}: cannot find Version attribute")
        return False

    old_version = match.group(1)
    if old_version == msix_version:
        print(f"  [OK] {filepath.relative_to(PROJECT_ROOT)}: already {msix_version}")
        return False

    if dry_run:
        print(f"  [DRY-RUN] {filepath.relative_to(PROJECT_ROOT)}: {old_version} -> {msix_version}")
        return True

    new_content = content.replace(f'Version="{old_version}"', f'Version="{msix_version}"')
    with filepath.open("w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  [SYNCED] {filepath.relative_to(PROJECT_ROOT)}: {old_version} -> {msix_version}")
    return True


def sync_cargo_toml(filepath: Path, version: str, dry_run: bool = False) -> bool:
    """同步版本号到 Cargo.toml (TOML) 文件，返回是否需要变更。

    匹配 [package] 下的 version = "x.y.z" 行。
    """
    with filepath.open("r", encoding="utf-8") as f:
        content = f.read()

    match = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', content, re.MULTILINE)
    if not match:
        print(f"  [ERROR] {filepath.relative_to(PROJECT_ROOT)}: cannot find package version")
        return False

    old_version = match.group(1)
    if old_version == version:
        print(f"  [OK] {filepath.relative_to(PROJECT_ROOT)}: already {version}")
        return False

    if dry_run:
        print(f"  [DRY-RUN] {filepath.relative_to(PROJECT_ROOT)}: {old_version} -> {version}")
        return True

    new_content = content.replace(f'version = "{old_version}"', f'version = "{version}"', 1)
    with filepath.open("w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  [SYNCED] {filepath.relative_to(PROJECT_ROOT)}: {old_version} -> {version}")
    return True


def main() -> None:
    dry_run = "--check" in sys.argv

    print(f"Source: pyproject.toml")

    version = get_pyproject_version()
    print(f"Version: {version}")
    print()

    targets = [TAURI_CONF_PATH, CARGO_TOML_PATH, FRONT_PKG_PATH, MSIX_MANIFEST_PATH]
    changed = False

    for target in targets:
        if not target.exists():
            print(f"  [SKIP] {target.relative_to(PROJECT_ROOT)}: file not found")
            continue
        if target.name == "Package.appxmanifest":
            if sync_msix_manifest(target, version, dry_run=dry_run):
                changed = True
        elif target.name == "Cargo.toml":
            if sync_cargo_toml(target, version, dry_run=dry_run):
                changed = True
        else:
            if sync_json_file(target, version, dry_run=dry_run):
                changed = True

    if dry_run and changed:
        print("\nVersion mismatch detected! Run without --check to sync.")
        sys.exit(1)
    elif not changed:
        print("\nAll versions are in sync.")


if __name__ == "__main__":
    main()
