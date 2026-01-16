from enum import Enum


class ConnectionType(Enum):
    Serial = 0
    TcpClient = 1
    TcpServer = 2
