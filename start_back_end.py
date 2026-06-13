"""EMS Simulate 后端入口 - FastAPI 应用

用法:
    python start_back_end.py                          # 默认端口 8991
    python start_back_end.py --port 8991              # 指定端口
    python start_back_end.py --root-dir ./data        # 指定数据根目录

Tauri sidecar 会传入 --port 和 EMS_ROOT_DIR 环境变量。
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys

# ⭐ Windows 打包环境下将 stdout/stderr 重定向到日志文件，避免控制台闪现
if sys.platform.startswith("win") and getattr(sys, "frozen", False):
    # MSIX 安装模式下可执行文件目录为只读，需使用 EMS_ROOT_DIR（Tauri 侧设置的可写数据目录）
    _root = Path(os.environ.get("EMS_ROOT_DIR", sys.executable)).parent
    _log_dir = _root / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    sys.stdout = (_log_dir / "backend.log").open("a", encoding="utf-8")  # noqa: SIM115  # 需要持久打开替换 stdout
    sys.stderr = sys.stdout
    logging.basicConfig(
        filename=_log_dir / "app_error.log",
        level=logging.ERROR,
        format="%(asctime)s - %(levelname)s: %(message)s",
    )


def _parse_args() -> argparse.Namespace:
    """解析命令行参数（Tauri sidecar 传入 --port）"""
    parser = argparse.ArgumentParser(description="EMS Simulate Backend")
    parser.add_argument("--port", type=int, default=8991, help="服务端口号")
    parser.add_argument(
        "--root-dir",
        type=str,
        default=None,
        help="数据根目录（优先级低于 EMS_ROOT_DIR 环境变量）",
    )
    return parser.parse_args()


def _get_root_dir(cli_root: str | None) -> Path:
    """确定数据根目录：环境变量 > CLI 参数 > 脚本所在目录"""
    if env_root := os.environ.get("EMS_ROOT_DIR"):
        return Path(env_root)
    if cli_root:
        return Path(cli_root)
    return Path(__file__).resolve().parent


# ── CLI 入口 ──

if __name__ == "__main__":
    args = _parse_args()
    root_dir = _get_root_dir(args.root_dir)

    # 创建数据子目录
    for sub in ("data", "logs", "config", "upload", "plan"):
        (root_dir / sub).mkdir(parents=True, exist_ok=True)

    # 延迟导入，避免 CLI 解析前加载 FastAPI 全家桶
    from fastapi.staticfiles import StaticFiles
    import uvicorn

    from src.web.app import app

    # 挂载静态文件
    static_dir = (
        Path(sys._MEIPASS) / "www"
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
        else Path(__file__).resolve().parent / "www"
    )
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    print("\nEMS Simulate 后端启动中...")
    print(f"端口: {args.port}  |  数据目录: {root_dir}")
    print(f"API 文档: http://127.0.0.1:{args.port}/docs")
    print(f"Redoc:   http://127.0.0.1:{args.port}/redoc\n")

    uvicorn.run(
        "src.web.app:app",
        host="127.0.0.1" if "EMS_ROOT_DIR" in os.environ else "0.0.0.0",
        port=args.port,
        log_level="info",
        reload=False,
    )
