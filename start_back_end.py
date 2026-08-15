"""EMS Simulate 后端入口 - FastAPI 应用

用法:
    python start_back_end.py --port 8991
    python start_back_end.py --port 8991 --root-dir ./data

Tauri 侧通过 Rust spawn 传入 --port 和 EMS_ROOT_DIR 环境变量。
stdout/stderr 由 Rust 侧 Stdio::null() 统一抑制，Python 层无需处理。
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def _parse_args() -> argparse.Namespace:
    """解析命令行参数（Tauri sidecar / direct spawn 传入 --port）"""
    parser = argparse.ArgumentParser(description="EMS Simulate Backend")
    parser.add_argument("--port", type=int, default=8991, help="服务端口号")
    parser.add_argument("--root-dir", type=str, default=None, help="数据根目录（优先级低于 EMS_ROOT_DIR 环境变量）")
    return parser.parse_args()


def _get_root_dir(cli_root: str | None) -> Path:
    """Resolve the runtime data root before importing the FastAPI app."""
    if env_root := os.environ.get("EMS_ROOT_DIR"):
        return Path(env_root)
    if cli_root:
        return Path(cli_root)
    return Path(__file__).resolve().parent


def _bundled_path(name: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / name
    return Path(__file__).resolve().parent / name


def _prepare_runtime_root(root_dir: Path) -> None:
    root_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("data", "log", "config", "upload", "plan"):
        (root_dir / sub).mkdir(parents=True, exist_ok=True)
    (root_dir / "data" / "point_csv").mkdir(parents=True, exist_ok=True)

    config_target = root_dir / "config.ini"
    config_source = _bundled_path("config.ini")
    if not config_target.exists() and config_source.exists():
        config_target.write_bytes(config_source.read_bytes())

    # 首次运行时复制初始数据库
    db_target = root_dir / "data" / "ems.db"
    if not db_target.exists() or db_target.stat().st_size == 0:
        db_source = _bundled_path("data/ems.db")
        if db_source.is_file() and db_source.stat().st_size > 0:
            # Replace atomically so an interrupted first launch cannot leave a
            # partial SQLite file that then survives every later restart.
            db_temp = db_target.with_suffix(".db.tmp")
            db_temp.write_bytes(db_source.read_bytes())
            db_temp.replace(db_target)

    # 首次运行时复制样本点表文件
    point_csv_target = root_dir / "data" / "point_csv"
    point_csv_source = _bundled_path("data/point_csv")
    if point_csv_source.is_dir() and not any(point_csv_target.iterdir()):
        for f in point_csv_source.iterdir():
            if f.is_file():
                (point_csv_target / f.name).write_bytes(f.read_bytes())


if __name__ == "__main__":
    args = _parse_args()
    root_dir = _get_root_dir(args.root_dir)
    _prepare_runtime_root(root_dir)

    # Late imports keep CLI parsing and runtime root setup deterministic.
    from fastapi.staticfiles import StaticFiles
    import uvicorn

    from src.config.config import Config
    from src.web.app import app

    # 挂载静态文件（前端打包产物）
    static_dir = (
        Path(sys._MEIPASS) / "www"
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
        else Path(__file__).resolve().parent / "www"
    )
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    uvicorn.run(
        "src.web.app:app",
        host=Config.web_host,
        port=args.port,
        log_level="info",
        reload=False,
    )
