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
    """确定数据根目录：环境变量 > CLI 参数 > 脚本所在目录"""
    if env_root := os.environ.get("EMS_ROOT_DIR"):
        return Path(env_root)
    if cli_root:
        return Path(cli_root)
    return Path(__file__).resolve().parent


if __name__ == "__main__":
    args = _parse_args()
    root_dir = _get_root_dir(args.root_dir)

    # 创建数据子目录
    for sub in ("data", "logs", "config", "upload", "plan"):
        (root_dir / sub).mkdir(parents=True, exist_ok=True)

    # 延迟导入，避免 CLI 解析前加载 FastAPI
    from fastapi.staticfiles import StaticFiles
    import uvicorn

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
        host="127.0.0.1",
        port=args.port,
        log_level="info",
        reload=False,
    )
