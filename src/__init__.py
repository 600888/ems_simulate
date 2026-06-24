"""EMS Simulate - 电力模拟仿真系统"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ems_simulate")
except PackageNotFoundError:
    # 开发模式下未安装包，从 pyproject.toml 读取
    try:
        from pathlib import Path
        import tomllib

        _pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        with _pyproject.open("rb") as f:
            __version__ = tomllib.load(f)["project"]["version"]
    except Exception:
        __version__ = "0.0.0"
