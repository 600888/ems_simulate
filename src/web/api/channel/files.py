"""通道管理 - IEC 61850 文件下载服务路由

提供远程 IED 的文件目录浏览、文件下载/上传/删除、本地缓存管理等 HTTP 接口。
"""

import base64
import contextlib
import os
import tempfile
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from src.data.service.channel_service import ChannelService
from src.web.api.schemas import BaseResponse
from src.web.log import log

router = APIRouter(tags=["channel"])


# ===== 请求模型 =====


class FileDirectoryRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    directory: str = Field("", description="目录路径，空字符串表示根目录")


class FileDirectoryTreeRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    directory: str = Field("", description="起始目录路径")
    max_depth: int = Field(5, description="最大递归深度")


class FileDownloadRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    filename: str = Field(..., description="远程文件绝对路径，如 /logs/fault1.comtrade")
    use_cache: bool = Field(True, description="是否优先使用本地缓存")
    return_format: str = Field("file", description="返回格式: file=文件流, json=Base64 JSON")


class FileUploadRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    remote_filename: str = Field(..., description="远程目标文件名")
    file_data: str = Field(..., description="文件内容 (Base64 编码)")


class FileDeleteRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    filename: str = Field(..., description="远程文件绝对路径")


class FileCacheListRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")


class FileCacheClearRequest(BaseModel):
    channel_id: int = Field(..., description="通道ID")
    remote_path: str = Field("", description="指定远程路径 (为空则清空全部)")


# ===== 辅助函数 =====


def _get_iec61850_client(request: Request, channel_id: int):
    """获取 IEC61850 客户端实例

    Returns:
        (client, error_response) 元组，client 为 None 时检查 error_response
    """
    channel = ChannelService.get_channel_by_id(channel_id)
    if not channel:
        return None, BaseResponse(code=404, message="通道不存在", data={})

    protocol_type = channel.get("protocol_type", -1)
    if protocol_type != 4:
        return None, BaseResponse(code=400, message="该通道不是 IEC61850 协议", data={})

    device_controller = request.app.state.device_controller
    device = device_controller.get_device_by_channel_id(channel_id)
    if not device:
        return None, BaseResponse(code=404, message="设备未找到", data={})

    protocol_handler = getattr(device, "protocol_handler", None)
    if not protocol_handler:
        return None, BaseResponse(code=400, message="协议处理器未初始化", data={})

    # 获取客户端或服务端的 files 插件
    client = None
    if hasattr(protocol_handler, "_client") and protocol_handler._client:
        client = protocol_handler._client
    elif hasattr(protocol_handler, "_server") and protocol_handler._server:
        client = protocol_handler._server

    if not client:
        return None, BaseResponse(code=400, message="IEC61850 客户端/服务端未初始化", data={})

    files_plugin = getattr(client, "files", None)
    if not files_plugin:
        return None, BaseResponse(code=400, message="文件服务插件不可用", data={})

    return client, None


# ===== 路由端点 =====


@router.post("/iec61850-file-directory", response_model=BaseResponse)
async def get_file_directory(body: FileDirectoryRequest, request: Request):
    """获取远程 IED 的文件/目录列表"""
    try:
        client, err = _get_iec61850_client(request, body.channel_id)
        if err:
            return err

        files = client.files
        entries = files.list_directory(body.directory)

        return BaseResponse(
            message="获取文件目录成功",
            data={"directory": body.directory, "entries": entries, "total": len(entries)},
        )
    except Exception as e:
        log.error(f"获取文件目录失败: {e}")
        return BaseResponse(code=500, message=f"获取文件目录失败: {e}", data={})


@router.post("/iec61850-file-directory-tree", response_model=BaseResponse)
async def get_file_directory_tree(body: FileDirectoryTreeRequest, request: Request):
    """递归获取远程 IED 的完整文件目录树"""
    try:
        client, err = _get_iec61850_client(request, body.channel_id)
        if err:
            return err

        files = client.files
        entries = files.list_directory_recursive(body.directory, body.max_depth)

        return BaseResponse(
            message="获取文件目录树成功",
            data={"directory": body.directory, "entries": entries, "total": len(entries)},
        )
    except Exception as e:
        log.error(f"获取文件目录树失败: {e}")
        return BaseResponse(code=500, message=f"获取文件目录树失败: {e}", data={})


@router.post("/iec61850-file-download", response_model=BaseResponse)
async def download_file(body: FileDownloadRequest, request: Request):
    """从远程 IED 下载文件

    支持 return_format:
    - file: 返回文件流的 Base64 编码 (默认)
    - json: 返回文件元数据 + Base64 数据
    """
    try:
        client, err = _get_iec61850_client(request, body.channel_id)
        if err:
            return err

        files = client.files

        # 检查缓存
        if body.use_cache:
            cached = files.get_cached_file(body.filename)
            if cached and os.path.isfile(cached):
                log.info(f"命中文件缓存: {body.filename} → {cached}")
                with open(cached, "rb") as f:
                    data = f.read()
                return BaseResponse(
                    message="文件下载成功 (缓存)",
                    data={
                        "filename": body.filename,
                        "data": base64.b64encode(data).decode("ascii"),
                        "size": len(data),
                        "cached": True,
                    },
                )

        # 下载文件到内存
        file_bytes = files.get_file(body.filename)

        if not file_bytes:
            return BaseResponse(code=404, message=f"远程文件不存在或下载失败: {body.filename}", data={})

        return BaseResponse(
            message="文件下载成功",
            data={
                "filename": body.filename,
                "data": base64.b64encode(file_bytes).decode("ascii"),
                "size": len(file_bytes),
                "cached": False,
            },
        )
    except Exception as e:
        log.error(f"文件下载失败: {e}")
        return BaseResponse(code=500, message=f"文件下载失败: {e}", data={})


@router.post("/iec61850-file-upload", response_model=BaseResponse)
async def upload_file(body: FileUploadRequest, request: Request):
    """上传文件到远程 IED

    请求体中的 file_data 为文件内容的 Base64 编码。
    """
    try:
        client, err = _get_iec61850_client(request, body.channel_id)
        if err:
            return err

        # 解码 Base64 数据
        try:
            file_data = base64.b64decode(body.file_data)
        except Exception:
            return BaseResponse(code=400, message="file_data 不是有效的 Base64 编码", data={})

        if not file_data:
            return BaseResponse(code=400, message="文件数据为空", data={})

        # 写入临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix="_upload") as tmp:
            tmp.write(file_data)
            tmp_path = tmp.name

        try:
            files = client.files
            success = files.upload_file(tmp_path, body.remote_filename)

            if success:
                return BaseResponse(
                    message="文件上传成功",
                    data={"remote_filename": body.remote_filename, "size": len(file_data)},
                )
            else:
                return BaseResponse(code=500, message="文件上传失败", data={})
        finally:
            # 清理临时文件
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)

    except Exception as e:
        log.error(f"文件上传失败: {e}")
        return BaseResponse(code=500, message=f"文件上传失败: {e}", data={})


@router.post("/iec61850-file-delete", response_model=BaseResponse)
async def delete_remote_file(body: FileDeleteRequest, request: Request):
    """删除远程 IED 上的文件"""
    try:
        client, err = _get_iec61850_client(request, body.channel_id)
        if err:
            return err

        files = client.files
        success = files.delete_file(body.filename)

        if success:
            return BaseResponse(message="远程文件已删除", data={"filename": body.filename})
        else:
            return BaseResponse(code=500, message="删除远程文件失败", data={"filename": body.filename})
    except Exception as e:
        log.error(f"删除远程文件失败: {e}")
        return BaseResponse(code=500, message=f"删除远程文件失败: {e}", data={})


@router.post("/iec61850-file-cache-list", response_model=BaseResponse)
async def list_cached_files(body: FileCacheListRequest, request: Request):
    """获取本地缓存的文件列表"""
    try:
        client, err = _get_iec61850_client(request, body.channel_id)
        if err:
            return err

        files = client.files
        cached = files.list_cached_files()

        return BaseResponse(
            message="获取缓存列表成功",
            data={"files": cached, "total": len(cached)},
        )
    except Exception as e:
        log.error(f"获取缓存列表失败: {e}")
        return BaseResponse(code=500, message=f"获取缓存列表失败: {e}", data={})


@router.post("/iec61850-file-cache-clear", response_model=BaseResponse)
async def clear_file_cache(body: FileCacheClearRequest, request: Request):
    """清理本地文件缓存"""
    try:
        client, err = _get_iec61850_client(request, body.channel_id)
        if err:
            return err

        files = client.files

        if body.remote_path:
            # 删除指定文件缓存
            removed = files._cache.remove(body.remote_path) if files._cache else False
            count = 1 if removed else 0
        else:
            # 清空全部缓存
            count = files.clear_cache()

        return BaseResponse(message="缓存清理完成", data={"cleared": count})
    except Exception as e:
        log.error(f"缓存清理失败: {e}")
        return BaseResponse(code=500, message=f"缓存清理失败: {e}", data={})
