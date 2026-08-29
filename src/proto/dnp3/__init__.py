"""
DNP3 协议封装（基于 pydnp3-pure 纯 Python 库）

对外提供:
- Dnp3Server : DNP3 服务端（Outstation），模拟从站/远方终端
- Dnp3Client : DNP3 客户端（Master），作为主站轮询真实 Outstation
"""

from . import objects as _objects  # noqa: F401 - register additional standard groups
from .dnp3_client import Dnp3Client
from .dnp3_server import Dnp3Server

__all__ = ["Dnp3Server", "Dnp3Client"]
