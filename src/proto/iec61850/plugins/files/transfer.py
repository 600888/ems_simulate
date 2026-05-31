"""远程 IED 文件传输操作

封装 pyiec61850 的 getFile / setFile / deleteFile 函数，提供:
- 文件下载 (MmsConnection_downloadFile)
- 文件上传 (SetFile / ObtainFile)
- 文件删除 (DeleteFile)
- 传输进度回调

pyiec61850 Python 绑定签名:
    IedConnection_getFile(self, fileName, handler, handlerParameter) → (bytesReceived, error)
    IedConnection_setFile(self, sourceFilename, destinationFilename) → (data, error)
    IedConnection_deleteFile(self, fileName) → (data, error)
    IedConnection_setFilestoreBasepath(arg1, basepath) → None
    MmsConnection_downloadFile(connection, mmsError, remoteFilePath, localFilePath) → bool
    MmsConnection_obtainFile(self, mmsError, sourceFile, destinationFile) → ...

注意:
- IedConnection_* 系列函数返回值格式为 (data, error_code)，error_code = IED_ERROR_OK(0) 表示成功。
- MmsConnection_downloadFile 返回 bool，错误码通过 mmsError 输出参数获取。
- libiec61850 在检查远程文件是否存在之前就会创建本地文件，失败下载会留下 0 字节残留。
"""

import os
from typing import Optional, Callable

from ...core.connection import Iec61850Connection
from ...defs.constants import HAS_IEC61850
from ...log import log
from .types import TransferProgress, TransferStatus


# 进度回调类型: (progress: TransferProgress) -> None
ProgressCallback = Callable[[TransferProgress], None]


def _ied_error_name(error_code) -> str:
    """将 IED 错误码转换为可读名称"""
    if error_code is None or error_code == 0:
        return "OK"
    _map = {}
    try:
        from pyiec61850 import pyiec61850 as iec
        _map = {v: k for k, v in vars(iec).items() if k.startswith("IED_ERROR") and isinstance(v, int)}
    except Exception:
        pass
    return _map.get(error_code, f"UNKNOWN({error_code})")


def _mms_error_name(error_code) -> str:
    """将 MMS 错误码转换为可读名称"""
    if error_code is None or error_code == 0:
        return "OK"
    try:
        from pyiec61850 import pyiec61850 as iec
        return iec.MmsError_toString(error_code)
    except Exception:
        return f"MMS_ERROR({error_code})"


class FileTransfer:
    """远程 IED 文件传输器"""

    def __init__(self, connection: Iec61850Connection):
        self._conn = connection
        self._active_transfers: dict[str, TransferProgress] = {}

    # ===== 公共 API =====

    @staticmethod
    def _normalize_remote(remote_filename: str) -> str:
        """规范化远程文件名供 IED 使用 (统一正斜杠，去除多余分隔符)"""
        return remote_filename.replace("\\", "/")

    def download_file(
        self,
        remote_filename: str,
        local_path: str,
        progress_callback: Optional[ProgressCallback] = None,
        overwrite: bool = False,
    ) -> TransferProgress:
        """从远程 IED 下载文件到本地磁盘

        使用 MmsConnection_downloadFile 下载文件，直接落盘到本地路径。
        参考 pyiec61850.mms.client.MmsClient.download_file 的官方实现。

        Args:
            remote_filename: 远程文件绝对路径 (如 "/logs/fault1.comtrade")
            local_path: 本地保存路径
            progress_callback: 进度回调
            overwrite: 是否覆盖已存在的本地文件

        Returns:
            传输进度信息
        """
        if not HAS_IEC61850:
            return TransferProgress(remote_filename, status=TransferStatus.FAILED, error="pyiec61850 未安装")

        if not self._conn or not self._conn.is_connected:
            return TransferProgress(remote_filename, status=TransferStatus.FAILED, error="连接不可用")

        # 检查本地文件
        if os.path.exists(local_path) and not overwrite:
            return TransferProgress(
                remote_filename, status=TransferStatus.FAILED,
                error=f"本地文件已存在: {local_path}"
            )

        progress = TransferProgress(filename=remote_filename, status=TransferStatus.PENDING)
        self._active_transfers[remote_filename] = progress

        try:
            from pyiec61850 import pyiec61850 as iec61850

            conn = self._conn.connection

            # 确保本地目录存在
            local_dir = os.path.dirname(local_path)
            if local_dir:
                os.makedirs(local_dir, exist_ok=True)

            # 更新状态
            progress.status = TransferStatus.IN_PROGRESS
            self._notify_progress(progress, progress_callback)

            mms_conn = iec61850.IedConnection_getMmsConnection(conn)
            if not mms_conn:
                progress.status = TransferStatus.FAILED
                progress.error = "无法获取 MmsConnection"
                log.error(f"下载文件失败: {remote_filename}, 无法获取 MmsConnection")
                return progress

            # MmsConnection_downloadFile 直接使用 localFilePath 写入本地文件，
            # 不经过 filestore basepath 拼接。
            local_path_fwd = local_path.replace("\\", "/")
            mms_error = iec61850.MmsError_create()
            succeeded = False
            try:
                ok = iec61850.MmsConnection_downloadFile(
                    mms_conn, mms_error, self._normalize_remote(remote_filename), local_path_fwd
                )
                mms_code = iec61850.MmsError_getValue(mms_error)

                if not ok or mms_code != 0:
                    progress.status = TransferStatus.FAILED
                    progress.error = f"MMS 下载失败: {_mms_error_name(mms_code)}({mms_code})"
                    log.error(f"下载文件失败: {remote_filename}, MMS 错误: {_mms_error_name(mms_code)}({mms_code})")
                    try:
                        if os.path.exists(local_path):
                            os.remove(local_path)
                    except OSError:
                        pass
                else:
                    succeeded = True
            finally:
                # 注意: SWIG 导出的析构函数名是 MmsErrror_destroy (三个 r 的拼写错误)
                try:
                    iec61850.MmsErrror_destroy(mms_error)
                except AttributeError:
                    try:
                        iec61850.MmsError_destroy(mms_error)
                    except Exception:
                        pass

            if succeeded:
                downloaded_size = os.path.getsize(local_path) if os.path.exists(local_path) else 0
                # libiec61850 在检查远程文件是否存在之前就会创建本地文件，
                # 失败下载会留下 0 字节残留，需清理。
                if downloaded_size == 0:
                    progress.status = TransferStatus.FAILED
                    progress.error = "下载文件为空 (0 bytes)，远程文件可能不存在"
                    log.warning(f"下载文件失败: {remote_filename}, 下载结果为 0 字节")
                    try:
                        os.remove(local_path)
                    except OSError:
                        pass
                else:
                    progress.status = TransferStatus.COMPLETED
                    progress.bytes_transferred = downloaded_size
                    progress.total_bytes = downloaded_size
                    log.info(f"文件下载完成: {remote_filename} → {local_path} ({downloaded_size} bytes)")

        except Exception as e:
            progress.status = TransferStatus.FAILED
            progress.error = str(e)
            log.error(f"下载文件异常: {remote_filename}, 错误: {e}")
            # 清理可能残留的 0 字节文件
            try:
                if os.path.exists(local_path) and os.path.getsize(local_path) == 0:
                    os.remove(local_path)
            except OSError:
                pass

        finally:
            self._notify_progress(progress, progress_callback)
            self._active_transfers.pop(remote_filename, None)

        return progress

    def download_file_to_bytes(
        self,
        remote_filename: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> tuple[bytes, TransferProgress]:
        """从远程 IED 下载文件到内存

        适用于小文件 (如 ICD 配置文件)，直接返回字节数据。

        Args:
            remote_filename: 远程文件绝对路径
            progress_callback: 进度回调

        Returns:
            (文件字节数据, 传输进度)
        """
        if not HAS_IEC61850:
            return b"", TransferProgress(remote_filename, status=TransferStatus.FAILED, error="pyiec61850 未安装")

        if not self._conn or not self._conn.is_connected:
            return b"", TransferProgress(remote_filename, status=TransferStatus.FAILED, error="连接不可用")

        progress = TransferProgress(filename=remote_filename, status=TransferStatus.PENDING)
        self._active_transfers[remote_filename] = progress

        try:
            import tempfile
            from pyiec61850 import pyiec61850 as iec61850

            conn = self._conn.connection
            progress.status = TransferStatus.IN_PROGRESS
            self._notify_progress(progress, progress_callback)

            mms_conn = iec61850.IedConnection_getMmsConnection(conn)
            if not mms_conn:
                progress.status = TransferStatus.FAILED
                progress.error = "无法获取 MmsConnection"
                log.error(f"下载文件到内存失败: {remote_filename}, 无法获取 MmsConnection")
                return b"", progress

            # MmsConnection_downloadFile 直接使用 localFilePath 写入本地文件，
            # 不经过 filestore basepath 拼接。先落盘到临时文件再读回内存。
            # 注意: Windows 系统临时目录可能包含中文等 Unicode 字符，
            # libiec61850 的 C 层 fopen() 无法处理，需使用纯 ASCII 路径。
            from pathlib import Path
            _tmp_dir = str(Path.cwd() / "data" / "_tmp")
            os.makedirs(_tmp_dir, exist_ok=True)
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".iecdl", dir=_tmp_dir)
            os.close(tmp_fd)
            tmp_path_fwd = tmp_path.replace("\\", "/")

            try:
                mms_error = iec61850.MmsError_create()
                succeeded = False
                try:
                    ok = iec61850.MmsConnection_downloadFile(
                        mms_conn, mms_error, self._normalize_remote(remote_filename), tmp_path_fwd
                    )
                    mms_code = iec61850.MmsError_getValue(mms_error)

                    if not ok or mms_code != 0:
                        progress.status = TransferStatus.FAILED
                        progress.error = f"MMS 下载失败: {_mms_error_name(mms_code)}({mms_code})"
                        log.error(f"下载文件到内存失败: {remote_filename}, MMS 错误: {_mms_error_name(mms_code)}({mms_code})")
                        return b"", progress
                    succeeded = True
                finally:
                    try:
                        iec61850.MmsErrror_destroy(mms_error)
                    except AttributeError:
                        try:
                            iec61850.MmsError_destroy(mms_error)
                        except Exception:
                            pass

                if not succeeded:
                    return b"", progress

                with open(tmp_path, "rb") as f:
                    file_data = f.read()
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

            # libiec61850 在检查远程文件是否存在之前就会创建本地文件，
            # 失败下载会留下 0 字节残留。
            if not file_data:
                progress.status = TransferStatus.FAILED
                progress.error = "下载文件为空 (0 bytes)，远程文件可能不存在"
                log.warning(f"下载文件到内存失败: {remote_filename}, 下载结果为 0 字节")
                return b"", progress

            progress.bytes_transferred = len(file_data)
            progress.status = TransferStatus.COMPLETED
            progress.total_bytes = len(file_data)
            log.info(f"文件下载到内存完成: {remote_filename} ({len(file_data)} bytes)")
            return file_data, progress

        except Exception as e:
            progress.status = TransferStatus.FAILED
            progress.error = str(e)
            log.error(f"下载文件到内存异常: {remote_filename}, 错误: {e}")
            return b"", progress

        finally:
            self._notify_progress(progress, progress_callback)
            self._active_transfers.pop(remote_filename, None)

    def upload_file(
        self,
        local_path: str,
        remote_filename: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> TransferProgress:
        """上传本地文件到远程 IED

        优先使用 IedConnection_setFile，若失败则尝试 MmsConnection_obtainFile。
        SetFile 服务要求文件必须在客户端 VMD 虚拟文件库中可用。

        Args:
            local_path: 本地文件路径
            remote_filename: 远程目标文件名
            progress_callback: 进度回调

        Returns:
            传输进度信息
        """
        if not HAS_IEC61850:
            return TransferProgress(remote_filename, status=TransferStatus.FAILED, error="pyiec61850 未安装")

        if not self._conn or not self._conn.is_connected:
            return TransferProgress(remote_filename, status=TransferStatus.FAILED, error="连接不可用")

        if not os.path.isfile(local_path):
            return TransferProgress(
                remote_filename, status=TransferStatus.FAILED,
                error=f"本地文件不存在: {local_path}"
            )

        progress = TransferProgress(filename=remote_filename, status=TransferStatus.PENDING)
        progress.total_bytes = os.path.getsize(local_path)
        self._active_transfers[remote_filename] = progress

        try:
            from pyiec61850 import pyiec61850 as iec61850

            conn = self._conn.connection
            progress.status = TransferStatus.IN_PROGRESS
            self._notify_progress(progress, progress_callback)

            # 设置文件库基路径 — 让 SetFile 能找到本地文件
            local_dir = os.path.dirname(os.path.abspath(local_path))
            local_name = os.path.basename(local_path)

            # Windows: 将反斜杠转为正斜杠，避免 C 层路径解析异常
            local_dir_fwd = local_dir.replace("\\", "/")

            log.info(f"准备上传: {local_path} → {remote_filename}, "
                      f"basepath={local_dir_fwd}, sourceName={local_name}")

            try:
                iec61850.IedConnection_setFilestoreBasepath(conn, local_dir_fwd)
                log.debug(f"文件库基路径已设置: {local_dir_fwd}")
            except Exception as e:
                log.warning(f"设置文件库基路径失败: {e}")

            # 方式 1: IedConnection_setFile
            result = iec61850.IedConnection_setFile(conn, local_name, remote_filename)

            # 解析返回值: 统一格式 (data, error_code)
            error_code = self._parse_error_code(result)
            err_name = _ied_error_name(error_code)

            if error_code == iec61850.IED_ERROR_OK:
                progress.status = TransferStatus.COMPLETED
                progress.bytes_transferred = progress.total_bytes
                log.info(f"文件上传完成(setFile): {local_path} → {remote_filename}")
            else:
                log.warning(f"setFile 上传失败: {err_name}({error_code}), 尝试 obtainFile...")

                # 方式 2: MmsConnection_obtainFile (备选)
                error_code = self._upload_via_obtain_file(
                    iec61850, conn, local_dir_fwd, local_name, remote_filename
                )
                err_name = _ied_error_name(error_code)

                if error_code == iec61850.IED_ERROR_OK:
                    progress.status = TransferStatus.COMPLETED
                    progress.bytes_transferred = progress.total_bytes
                    log.info(f"文件上传完成(obtainFile): {local_path} → {remote_filename}")
                else:
                    progress.status = TransferStatus.FAILED
                    progress.error = f"上传失败: {err_name}({error_code})"
                    log.error(f"上传文件失败: {local_path} → {remote_filename}, "
                              f"错误码: {err_name}({error_code})")

        except Exception as e:
            progress.status = TransferStatus.FAILED
            progress.error = str(e)
            log.error(f"上传文件异常: {local_path} → {remote_filename}, 错误: {e}")

        finally:
            self._notify_progress(progress, progress_callback)
            self._active_transfers.pop(remote_filename, None)

        return progress

    def _upload_via_obtain_file(
        self, iec61850, conn, local_dir: str, local_name: str, remote_filename: str
    ) -> int:
        """使用 MmsConnection_obtainFile 上传文件 (备选方案)

        某些 IED 设备不支持 SetFile 服务但支持 ObtainFile。
        ObtainFile 让服务端主动从客户端拉取文件。

        Args:
            iec61850: pyiec61850 模块
            conn: IedConnection 对象
            local_dir: 本地文件目录 (正斜杠格式)
            local_name: 本地文件名
            remote_filename: 远程目标文件名

        Returns:
            错误码 (0 = 成功)
        """
        try:
            mms_conn = iec61850.IedConnection_getMmsConnection(conn)
            if not mms_conn:
                log.warning("无法获取 MmsConnection, obtainFile 不可用")
                return -1

            # 设置 MMS 层文件库基路径
            try:
                iec61850.MmsConnection_setFilestoreBasepath(mms_conn, local_dir)
            except Exception as e:
                log.debug(f"MMS 设置文件库基路径失败: {e}")

            # 构造 sourceFile: 本地文件在 VMD 文件库中的路径
            source_file = local_name

            # obtainFile 签名: (self, mmsError, sourceFile, destinationFile)
            # mmsError 是输出参数，传 None
            result = iec61850.MmsConnection_obtainFile(
                mms_conn, None, source_file, remote_filename
            )

            error_code = self._parse_error_code(result)
            if error_code != iec61850.IED_ERROR_OK:
                log.warning(f"obtainFile 上传失败: {_ied_error_name(error_code)}({error_code})")
            return error_code

        except Exception as e:
            log.warning(f"obtainFile 上传异常: {e}")
            return -1

    @staticmethod
    def _parse_error_code(result) -> int:
        """解析 pyiec61850 函数返回值中的错误码

        返回值格式统一为 (data, error_code)，其中:
        - data: 可能为 None 或其他数据
        - error_code: IED 错误码，0 表示成功
        """
        if isinstance(result, (list, tuple)) and len(result) >= 2:
            return result[1]
        if isinstance(result, int):
            return result
        return -1

    def delete_file(self, remote_filename: str) -> bool:
        """删除远程 IED 上的文件

        Args:
            remote_filename: 远程文件绝对路径

        Returns:
            是否删除成功
        """
        if not HAS_IEC61850:
            log.warning("pyiec61850 未安装，无法删除远程文件")
            return False

        if not self._conn or not self._conn.is_connected:
            log.warning("连接不可用，无法删除远程文件")
            return False

        try:
            from pyiec61850 import pyiec61850 as iec61850

            conn = self._conn.connection

            # 返回值格式: (data, error_code)
            result = iec61850.IedConnection_deleteFile(conn, remote_filename)
            error_code = self._parse_error_code(result)
            err_name = _ied_error_name(error_code)

            if error_code != iec61850.IED_ERROR_OK:
                log.error(f"删除远程文件失败: {remote_filename}, 错误: {err_name}({error_code})")
                return False

            log.info(f"远程文件已删除: {remote_filename}")
            return True

        except Exception as e:
            log.error(f"删除远程文件异常: {remote_filename}, 错误: {e}")
            return False

    def cancel_transfer(self, remote_filename: str) -> bool:
        """取消正在进行的传输

        Note: pyiec61850 的 GetFile 回调返回 False 可中断传输，
        但无法从外部直接取消。此处标记取消状态供回调检查。

        Returns:
            是否存在该传输并成功标记取消
        """
        progress = self._active_transfers.get(remote_filename)
        if progress and progress.status == TransferStatus.IN_PROGRESS:
            progress.status = TransferStatus.CANCELLED
            progress.error = "用户取消"
            log.info(f"传输已取消: {remote_filename}")
            return True
        return False

    def get_active_transfers(self) -> dict[str, TransferProgress]:
        """获取当前活跃的传输列表"""
        return dict(self._active_transfers)

    # ===== 内部方法 =====

    @staticmethod
    def _notify_progress(progress: TransferProgress, callback: Optional[ProgressCallback]) -> None:
        """安全调用进度回调"""
        if callback:
            try:
                callback(progress)
            except Exception as e:
                log.debug(f"进度回调异常: {e}")
