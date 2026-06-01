"""IEC 61850 异常层次定义

提供结构化的异常类，替代原有的通用 Exception 和 RuntimeError。
"""


class Iec61850Error(Exception):
    """IEC 61850 基础异常"""

    pass


class ConnectionError(Iec61850Error):
    """连接相关异常"""

    pass


class ConnectionTimeoutError(ConnectionError):
    """连接超时"""

    pass


class ConnectionLostError(ConnectionError):
    """连接丢失"""

    pass


class ReadError(Iec61850Error):
    """读取相关异常"""

    pass


class WriteError(Iec61850Error):
    """写入相关异常"""

    pass


class ModelError(Iec61850Error):
    """模型相关异常"""

    pass


class ModelBuildError(ModelError):
    """模型构建异常"""

    pass


class DiscoveryError(Iec61850Error):
    """模型发现异常"""

    pass


class PluginError(Iec61850Error):
    """插件相关异常"""

    pass


class PluginNotAvailableError(PluginError):
    """插件不可用"""

    pass


class DataSetError(Iec61850Error):
    """DataSet 相关异常"""

    pass


class GooseError(Iec61850Error):
    """GOOSE 相关异常"""

    pass


class FCResolveError(Iec61850Error):
    """FC 解析失败"""

    pass


class TypeResolveError(Iec61850Error):
    """类型推断失败"""


class FileError(Iec61850Error):
    """文件服务相关异常"""

    pass


class FileTransferError(FileError):
    """文件传输异常"""

    pass


class FileNotFoundError(FileError):
    """远程文件不存在"""

    pass
    pass
