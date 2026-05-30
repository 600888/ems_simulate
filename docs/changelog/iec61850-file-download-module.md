# IEC 61850 文件下载服务模块开发计划

> 版本: 1.0  
> 日期: 2026-05-31  
> 状态: 规划中  
> 关联文档: [iec61850-scl-file-module.md](./iec61850-scl-file-module.md)、[iec61850-refactoring-plan.md](./iec61850-refactoring-plan.md)

---

## 1. 概述

**重要说明**：本文档描述的"文件下载服务"与 [SCL 文件模块](./iec61850-scl-file-module.md) 是**完全不同**的功能：

| 维度 | 文件下载服务 (本文档) | SCL 文件模块 |
|------|----------------------|-------------|
| **协议层** | MMS 文件传输服务 (ACSI) | SCL/XML 配置解析 |
| **数据源** | 远程 IED 的虚拟文件系统 | 本地 ICD/SCD/CID 文件 |
| **操作对象** | IED 上存储的任意文件 (日志/配置/固件等) | 变电站配置描述文档 |
| **通信方式** | MMS 客户端 ↔ 服务器实时传输 | 本地文件系统读写 + XML 解析 |
| **标准章节** | IEC 61850-7-2 §7.5 File Management | IEC 61850-6 SCL |
| **典型场景** | 从 IED 下载故障录波文件、读取日志文件、上传配置到 IED | 导入 ICD 测点、解析 GOOSE 配置 |

IEC 61850 文件服务定义于标准第 7-2 部分 (ACSI) 和第 8-1 部分 (MMS 映射)，提供了一组基于 MMS 协议的文件管理操作，允许客户端对远程 IED (智能电子设备) 的虚拟文件系统进行浏览、下载、上传和删除操作。

### 1.1 标准 ACSI 文件服务

IEC 61850 定义了以下 5 个文件服务 ACSI：

| ACSI 服务 | MMS 映射 | 方向 | 说明 |
|-----------|---------|------|------|
| **GetFileDirectory** | ObtainFileDirectory | C→S | 获取远程 IED 文件目录列表 |
| **GetFile** | FileRead | C←S | 从 IED 下载文件 (分块传输) |
| **SetFile** | FileWrite / FileOpen+FileRead | C→S | 上传文件到 IED |
| **DeleteFile** | FileDelete | C→S | 删除 IED 上的文件 |
| **GetFileAttributeValues** | FileDirectoryEntry | C→S | 获取文件属性 (名称/大小/修改时间) |

**典型使用流程**：

```
1. GetFileDirectory("/")       → 获取根目录文件/子目录列表
2. GetFileDirectory("/logs/")  → 进入子目录，浏览日志文件
3. GetFile("/logs/fault1.comtrade") → 下载故障录波文件
4. DeleteFile("/logs/fault1.comtrade") → (可选) 清理已下载文件
```

### 1.2 当前状态

**已实现：**

- ✅ `FilesPlugin` 骨架 (`src/proto/iec61850/plugins/files/__init__.py`) — 已注册到 PluginRegistry
- ✅ 插件系统架构完备 — Protocol 定义、懒加载注册、生命周期管理

**未实现 / 存在的问题：**

| 问题 | 严重度 | 说明 |
|------|--------|------|
| **FilesPlugin 全部空实现** | 🔴 高 | `get_file_list()` 返回空列表，`get_file()` 返回空字节，无任何实际功能 |
| **缺少 GetFileDirectory 实现** | 🔴 高 | 无法浏览远程 IED 文件目录 |
| **缺少 GetFile (下载) 实现** | 🔴 高 | 无法从 IED 下载文件 |
| **缺少 SetFile (上传) 实现** | 🟡 中 | 无法向 IED 上传文件 (如配置下装) |
| **缺少 DeleteFile 实现** | 🟡 中 | 无法删除 IED 上的文件 |
| **Client 未暴露 files 属性** | 🟡 中 | `IEC61850Client` 无 `files` property，与 datamodels/goose 等插件不一致 |
| **无本地缓存机制** | 🟡 中 | 下载的文件无本地缓存管理，重复下载浪费带宽 |
| **无进度回调** | 🟡 中 | IEC 61850 文件传输为分块式，当前无进度通知机制 |
| **无前端 UI** | 🟡 中 | 无法在界面中浏览/下载 IED 文件 |
| **无后端 API** | 🟡 中 | 无 HTTP 接口供前端调用 |

### 1.3 目标

构建一个完整的 IEC 61850 文件下载服务模块，提供：

1. **完整文件浏览** — GetFileDirectory 递归浏览远程 IED 虚拟文件系统
2. **可靠文件下载** — GetFile 分块传输 + 进度回调 + 断点续传
3. **文件上传/删除** — SetFile / DeleteFile 完整操作
4. **本地缓存管理** — 下载文件自动缓存、版本管理、空间控制
5. **后端 Web API** — RESTful 接口供前端调用
6. **前端文件浏览器** — 树形目录浏览、文件下载、拖拽上传
7. **与 SCL 模块协作** — 下载 ICD/SCD 文件后自动交给 SCL 模块解析

---

## 2. 总体架构

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3 + TypeScript)                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  FileExplorer.vue [新增]                                               │  │
│  │  ┌────────────────┐  ┌────────────────┐  ┌──────────────────────────┐ │  │
│  │  │ 远程文件目录树   │  │ 文件列表/详情    │  │ 下载进度/上传管理         │ │  │
│  │  │ (递归浏览)      │  │ (大小/时间/属性) │  │ (进度条/队列/拖拽)       │ │  │
│  │  └────────────────┘  └────────────────┘  └──────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  fileApi.ts (API 层) [新增]                                            │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │ HTTP / WebSocket
┌──────────────────────────────────┴──────────────────────────────────────────┐
│                        Backend (FastAPI)                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  FileServiceRouter [新增]  (/api/iec61850/files/*)                      │  │
│  │  GET  /directory      — 获取远程目录列表                                 │  │
│  │  GET  /download       — 下载远程文件                                     │  │
│  │  POST /upload         — 上传文件到远程                                   │  │
│  │  DELETE /remote       — 删除远程文件                                     │  │
│  │  GET  /cache          — 获取本地缓存列表                                 │  │
│  │  DELETE /cache         — 清理本地缓存                                    │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────┴──────────────────────────────────────────┐
│                  IEC 61850 Plugin System                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  FilesPlugin (重构)                      ←─ plugins/files/               │  │
│  │  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────────┐│  │
│  │  │ DirectoryBrowser   │  │ FileTransfer       │  │ CacheManager         ││  │
│  │  │ (目录浏览/递归)    │  │ (上传/下载/删除)   │  │ (本地缓存/版本)      ││  │
│  │  └───────────────────┘  └───────────────────┘  └─────────────────────┘│  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  IEC61850Client (门面)                     ←─ iec61850_client.py        │  │
│  │  + files: FilesPlugin  [新增 property]                                  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────┴──────────────────────────────────────────┐
│                  pyiec61850 (C 绑定层)                                        │
│  IedConnection_getFileDirectory  IedConnection_getFileDirectoryEx             │
│  IedConnection_getFile           IedConnection_setFile                        │
│  IedConnection_deleteFile        FileDirectoryEntry_*                         │
│  IedClientGetFileHandler (回调)   IedConnection_FileDirectoryEntryHandler    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 模块职责划分

```
src/proto/iec61850/plugins/files/
├── __init__.py              # FilesPlugin 主类 (插件协议实现 + 门面)
├── directory.py             # DirectoryBrowser — 目录浏览与递归遍历
├── transfer.py             # FileTransfer — 文件下载/上传/删除操作
├── cache.py                 # CacheManager — 本地缓存与版本管理
└── types.py                 # 数据类型定义 (FileEntry, FileMetadata, TransferProgress)
```

### 2.3 设计原则

| 原则 | 说明 |
|------|------|
| **插件隔离** | FilesPlugin 仅依赖 `Iec61850Connection` 和 `Iec61850Plugin` 协议，不依赖其他插件 |
| **门面委托** | FilesPlugin 作为门面，将具体操作委托给 DirectoryBrowser / FileTransfer / CacheManager |
| **分块式设计** | 文件下载采用回调式分块传输，避免大文件一次性加载到内存 |
| **可观测性** | 所有操作提供进度回调和日志，便于前端展示和调试 |
| **容错优先** | pyiec61850 函数调用统一异常包装，连接断开时自动清理资源 |
| **与 SCL 解耦** | FilesPlugin 不关心文件内容，仅负责传输；下载 ICD 文件后由上层交给 SCL 模块解析 |

---

## 3. 详细设计

### 3.1 数据类型 (`types.py`)

```python
"""IEC 61850 文件服务数据类型定义"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


class FileType(enum.Enum):
    """文件/目录类型"""
    FILE = "file"
    DIRECTORY = "directory"


class TransferStatus(enum.Enum):
    """传输状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class FileEntry:
    """远程文件目录条目
    
    对应 libiec61850 的 FileDirectoryEntry:
    - fileName: 文件名 (相对路径)
    - fileSize: 文件大小 (字节), 未知时为 -1
    - lastModified: 最后修改时间 (UTC 毫秒时间戳)
    """
    name: str                              # 文件/目录名
    file_type: FileType = FileType.FILE    # 文件类型
    size: int = -1                         # 文件大小 (字节), -1 表示未知
    last_modified: Optional[datetime] = None  # 最后修改时间
    full_path: str = ""                    # 完整路径 (用于下载/删除)
    
    @property
    def is_directory(self) -> bool:
        return self.file_type == FileType.DIRECTORY
    
    @property
    def size_human(self) -> str:
        """人类可读的文件大小"""
        if self.size < 0:
            return "未知"
        for unit in ("B", "KB", "MB", "GB"):
            if self.size < 1024:
                return f"{self.size:.1f} {unit}"
            self.size /= 1024
        return f"{self.size:.1f} TB"


@dataclass
class TransferProgress:
    """文件传输进度"""
    filename: str                          # 远程文件名
    status: TransferStatus = TransferStatus.PENDING
    bytes_transferred: int = 0             # 已传输字节数
    total_bytes: int = -1                  # 总字节数, -1 表示未知
    error: Optional[str] = None           # 错误信息
    
    @property
    def progress_percent(self) -> float:
        """进度百分比 (0.0 ~ 100.0)"""
        if self.total_bytes <= 0:
            return 0.0
        return min(100.0, self.bytes_transferred / self.total_bytes * 100)
    
    @property
    def is_complete(self) -> bool:
        return self.status in (TransferStatus.COMPLETED, TransferStatus.FAILED, TransferStatus.CANCELLED)


@dataclass
class FileMetadata:
    """本地缓存文件元数据"""
    remote_path: str                       # 远程文件路径 (唯一键)
    local_path: str                        # 本地缓存路径
    file_size: int                         # 文件大小
    remote_modified: Optional[datetime]    # 远程最后修改时间
    download_time: datetime                # 下载时间
    checksum: Optional[str] = None         # 文件校验和 (MD5)
```

### 3.2 目录浏览器 (`directory.py`)

```python
"""远程 IED 文件目录浏览器

封装 pyiec61850 的 getFileDirectory 系列函数，提供:
- 单层目录浏览
- 递归目录遍历 (处理 moreFollows 分页)
- 目录条目解析 (FileDirectoryEntry → FileEntry)
"""

from typing import List, Optional, Callable

from ...core.connection import Iec61850Connection
from ...defs.constants import HAS_IEC61850
from ...log import log
from .types import FileEntry, FileType


class DirectoryBrowser:
    """远程 IED 文件目录浏览器"""
    
    # IED 文件目录中目录的常见后缀特征
    _DIR_INDICATORS = ("/",)
    
    def __init__(self, connection: Iec61850Connection):
        self._conn = connection
    
    def list_directory(self, directory: str = "") -> List[FileEntry]:
        """获取指定目录下的文件和子目录列表
        
        Args:
            directory: 目录路径，空字符串或 "/" 表示根目录
            
        Returns:
            FileEntry 列表，包含文件和子目录
            
        Raises:
            RuntimeError: pyiec61850 未安装或连接不可用
            Iec61850FileError: IED 返回错误
        """
        ...
    
    def list_directory_recursive(
        self, 
        directory: str = "",
        max_depth: int = 5,
        on_entry: Optional[Callable[[FileEntry], None]] = None,
    ) -> List[FileEntry]:
        """递归获取完整文件目录树
        
        Args:
            directory: 起始目录
            max_depth: 最大递归深度 (防止无限递归)
            on_entry: 每发现一个条目时的回调 (用于前端渐进显示)
            
        Returns:
            所有层级的 FileEntry 扁平列表
        """
        ...
    
    def _parse_file_directory_entry(self, entry) -> FileEntry:
        """将 pyiec61850 FileDirectoryEntry 转换为 FileEntry
        
        调用:
        - FileDirectoryEntry_getFileName(entry)
        - FileDirectoryEntry_getFileSize(entry)
        - FileDirectoryEntry_getLastModified(entry)
        """
        ...
    
    def _is_directory_entry(self, entry) -> bool:
        """判断目录条目是否为子目录
        
        IEC 61850 标准中目录条目无显式类型标识，
        常见判据:
        1. 文件名以 "/" 结尾 (libiec61850 惯例)
        2. 大小为 0 且无法作为文件打开
        3. 再次 GetFileDirectory 该路径返回非空列表
        """
        ...
    
    def _collect_all_entries(
        self, 
        directory: str,
    ) -> list:
        """处理 getFileDirectoryEx 的 moreFollows 分页
        
        当目录条目过多时，单个 MMS PDU 无法容纳，需要:
        1. 首次请求 continueAfter=NULL
        2. 若 moreFollows=True，以最后文件名作为 continueAfter 继续请求
        3. 重复直到 moreFollows=False
        """
        ...
```

### 3.3 文件传输器 (`transfer.py`)

```python
"""远程 IED 文件传输操作

封装 pyiec61850 的 getFile / setFile / deleteFile 函数，提供:
- 分块式文件下载 (IedClientGetFileHandler 回调)
- 文件上传 (SetFile)
- 文件删除 (DeleteFile)
- 传输进度回调
"""

import os
from typing import Optional, Callable

from ...core.connection import Iec61850Connection
from ...defs.constants import HAS_IEC61850
from ...log import log
from .types import TransferProgress, TransferStatus


# 进度回调类型: (progress: TransferProgress) -> None
ProgressCallback = Callable[[TransferProgress], None]


class FileTransfer:
    """远程 IED 文件传输器"""
    
    # 默认下载分块大小 (与 libiec61850 默认一致)
    DEFAULT_CHUNK_SIZE = 65535
    
    def __init__(self, connection: Iec61850Connection):
        self._conn = connection
        self._active_transfers: dict[str, TransferProgress] = {}
    
    def download_file(
        self,
        remote_filename: str,
        local_path: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> TransferProgress:
        """从远程 IED 下载文件到本地
        
        使用 IedConnection_getFile + IedClientGetFileHandler 回调，
        分块接收文件数据并写入本地磁盘。
        
        Args:
            remote_filename: 远程文件绝对路径 (如 "/logs/fault1.comtrade")
            local_path: 本地保存路径
            progress_callback: 进度回调
            
        Returns:
            传输进度信息
            
        Raises:
            Iec61850FileError: 下载失败
            FileExistsError: 本地文件已存在且不允许覆盖
        """
        ...
    
    def download_file_to_bytes(
        self,
        remote_filename: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> tuple[bytes, TransferProgress]:
        """从远程 IED 下载文件到内存
        
        适用于小文件 (如 ICD 配置文件)，直接返回字节数据，
        无需写入磁盘。
        
        Args:
            remote_filename: 远程文件绝对路径
            progress_callback: 进度回调
            
        Returns:
            (文件字节数据, 传输进度)
        """
        ...
    
    def upload_file(
        self,
        local_path: str,
        remote_filename: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> TransferProgress:
        """上传本地文件到远程 IED
        
        使用 IedConnection_setFile。注意: SetFile 服务要求文件
        必须在客户端 VMD 虚拟文件库中可用，因此需要先设置
        文件库基路径 (IedConnection_setFilestoreBasepath)。
        
        Args:
            local_path: 本地文件路径
            remote_filename: 远程目标文件名
            progress_callback: 进度回调
            
        Returns:
            传输进度信息
        """
        ...
    
    def delete_file(self, remote_filename: str) -> bool:
        """删除远程 IED 上的文件
        
        使用 IedConnection_deleteFile。
        
        Args:
            remote_filename: 远程文件绝对路径
            
        Returns:
            是否删除成功
        """
        ...
    
    def cancel_transfer(self, remote_filename: str) -> bool:
        """取消正在进行的传输
        
        Returns:
            是否成功取消
        """
        ...
    
    # ===== 内部方法 =====
    
    def _create_get_file_handler(self, local_path: str, progress: TransferProgress, 
                                   progress_callback: Optional[ProgressCallback]):
        """创建 GetFile 回调闭包
        
        IedClientGetFileHandler 签名:
            handler(parameter, buffer, bytesRead) -> bool
        
        返回 True 继续传输，False 取消传输。
        """
        ...
    
    def _create_download_to_bytes_handler(self, chunks: list, progress: TransferProgress,
                                            progress_callback: Optional[ProgressCallback]):
        """创建下载到内存的 GetFile 回调闭包"""
        ...
```

### 3.4 缓存管理器 (`cache.py`)

```python
"""本地文件缓存管理器

管理从远程 IED 下载的文件在本地磁盘的缓存，提供:
- 缓存文件存储与元数据管理
- 缓存命中检测 (路径 + 修改时间)
- 缓存空间管理 (LRU 淘汰 + 容量限制)
- 缓存清理
"""

import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ...log import log
from .types import FileMetadata, FileEntry


class CacheManager:
    """本地文件缓存管理器"""
    
    METADATA_FILE = ".cache_index.json"   # 缓存元数据索引文件
    DEFAULT_MAX_SIZE_MB = 500             # 默认最大缓存大小 (MB)
    
    def __init__(self, cache_dir: str = "", max_size_mb: int = DEFAULT_MAX_SIZE_MB):
        """
        Args:
            cache_dir: 缓存目录，为空时使用默认路径
            max_size_mb: 最大缓存大小 (MB)
        """
        self._cache_dir = Path(cache_dir) if cache_dir else self._default_cache_dir()
        self._max_size_bytes = max_size_mb * 1024 * 1024
        self._index: Dict[str, FileMetadata] = {}
        self._load_index()
    
    @staticmethod
    def _default_cache_dir() -> Path:
        """默认缓存目录: data/61850_cache/"""
        ...
    
    def get_cached_path(self, remote_path: str) -> Optional[str]:
        """查询文件是否已缓存
        
        Args:
            remote_path: 远程文件路径
            
        Returns:
            本地缓存路径，未缓存时返回 None
        """
        ...
    
    def is_cache_valid(self, remote_path: str, remote_modified: Optional[datetime]) -> bool:
        """检查缓存是否有效 (比较远程修改时间)
        
        若远程修改时间较新，则缓存失效。
        """
        ...
    
    def put(self, remote_path: str, local_source: str, 
            remote_modified: Optional[datetime] = None) -> str:
        """将文件加入缓存
        
        Args:
            remote_path: 远程文件路径 (作为缓存键)
            local_source: 本地源文件路径
            remote_modified: 远程文件修改时间
            
        Returns:
            缓存文件路径
        """
        ...
    
    def remove(self, remote_path: str) -> bool:
        """从缓存中移除文件"""
        ...
    
    def list_cached(self) -> List[FileMetadata]:
        """列出所有缓存文件"""
        ...
    
    def clear(self) -> int:
        """清空所有缓存
        
        Returns:
            清理的文件数量
        """
        ...
    
    def enforce_size_limit(self) -> int:
        """执行 LRU 缓存淘汰，确保总大小不超过限制
        
        Returns:
            淘汰的文件数量
        """
        ...
    
    def _load_index(self):
        """从磁盘加载缓存索引"""
        ...
    
    def _save_index(self):
        """将缓存索引保存到磁盘"""
        ...
    
    def _remote_path_to_local(self, remote_path: str) -> Path:
        """将远程路径映射为本地缓存路径
        
        例: /logs/fault1.comtrade → {cache_dir}/logs/fault1.comtrade
        """
        ...
```

### 3.5 FilesPlugin 主类 (`__init__.py` 重构)

```python
"""Files 插件 - IEC 61850 文件下载服务

提供远程 IED 的文件浏览、下载、上传、删除操作，
以及本地缓存管理能力。
"""

from typing import Any, Dict, List, Optional, Callable

from ..base import Iec61850Plugin
from ...defs.constants import HAS_IEC61850
from ...core.connection import Iec61850Connection
from ...log import log

from .directory import DirectoryBrowser
from .transfer import FileTransfer, ProgressCallback
from .cache import CacheManager
from .types import FileEntry, TransferProgress, FileMetadata


class FilesPlugin:
    """Files 插件 — IEC 61850 文件下载服务门面
    
    组合 DirectoryBrowser、FileTransfer、CacheManager 三个子模块，
    通过 Iec61850Plugin 协议接入插件系统。
    """
    
    def __init__(self):
        self._connection: Optional[Iec61850Connection] = None
        self._browser: Optional[DirectoryBrowser] = None
        self._transfer: Optional[FileTransfer] = None
        self._cache: Optional[CacheManager] = None
        self._initialized = False
    
    # ===== Iec61850Plugin 协议实现 =====
    
    @property
    def name(self) -> str:
        return "files"
    
    @property
    def available(self) -> bool:
        return HAS_IEC61850
    
    def initialize(self, connection: Any, **kwargs) -> None:
        if self._initialized:
            return
        self._connection = connection
        self._browser = DirectoryBrowser(connection)
        self._transfer = FileTransfer(connection)
        self._cache = CacheManager()
        self._initialized = True
        log.info("Files 插件已初始化 (完整实现)")
    
    def shutdown(self) -> None:
        self._browser = None
        self._transfer = None
        self._cache = None
        self._connection = None
        self._initialized = False
    
    # ===== 目录浏览 (委托 DirectoryBrowser) =====
    
    def list_directory(self, directory: str = "") -> List[Dict[str, Any]]:
        """获取远程 IED 的文件/目录列表
        
        Returns:
            [{"name": "...", "type": "file|directory", "size": 1234, 
              "last_modified": "2026-05-31T12:00:00", "full_path": "/logs/..."}]
        """
        if not self._browser:
            return []
        entries = self._browser.list_directory(directory)
        return [self._entry_to_dict(e) for e in entries]
    
    def list_directory_recursive(self, directory: str = "", max_depth: int = 5) -> List[Dict[str, Any]]:
        """递归获取完整目录树"""
        if not self._browser:
            return []
        entries = self._browser.list_directory_recursive(directory, max_depth)
        return [self._entry_to_dict(e) for e in entries]
    
    # ===== 文件传输 (委托 FileTransfer) =====
    
    def get_file(self, filename: str, local_path: str = "",
                 progress_callback: Optional[ProgressCallback] = None) -> bytes:
        """从远程 IED 下载文件
        
        Args:
            filename: 远程文件绝对路径
            local_path: 本地保存路径，为空时下载到内存并返回字节数据
            progress_callback: 进度回调
            
        Returns:
            若 local_path 为空，返回文件字节数据；否则返回空 bytes
        """
        if not self._transfer:
            return b""
        if local_path:
            progress = self._transfer.download_file(filename, local_path, progress_callback)
            return b"" if progress.is_complete else b""
        else:
            data, _ = self._transfer.download_file_to_bytes(filename, progress_callback)
            return data
    
    def upload_file(self, local_path: str, remote_filename: str,
                    progress_callback: Optional[ProgressCallback] = None) -> bool:
        """上传文件到远程 IED"""
        if not self._transfer:
            return False
        progress = self._transfer.upload_file(local_path, remote_filename, progress_callback)
        return progress.status.value == "completed"
    
    def delete_file(self, remote_filename: str) -> bool:
        """删除远程 IED 上的文件"""
        if not self._transfer:
            return False
        return self._transfer.delete_file(remote_filename)
    
    # ===== 缓存管理 (委托 CacheManager) =====
    
    def get_cached_file(self, remote_path: str) -> Optional[str]:
        """获取缓存文件路径"""
        if not self._cache:
            return None
        return self._cache.get_cached_path(remote_path)
    
    def list_cached_files(self) -> List[Dict[str, Any]]:
        """列出所有本地缓存文件"""
        if not self._cache:
            return []
        return [self._metadata_to_dict(m) for m in self._cache.list_cached()]
    
    def clear_cache(self) -> int:
        """清空本地缓存，返回清理的文件数量"""
        if not self._cache:
            return 0
        return self._cache.clear()
    
    # ===== 内部辅助 =====
    
    @staticmethod
    def _entry_to_dict(entry: FileEntry) -> Dict[str, Any]:
        return {
            "name": entry.name,
            "type": entry.file_type.value,
            "size": entry.size,
            "last_modified": entry.last_modified.isoformat() if entry.last_modified else None,
            "full_path": entry.full_path,
        }
    
    @staticmethod
    def _metadata_to_dict(meta: FileMetadata) -> Dict[str, Any]:
        return {
            "remote_path": meta.remote_path,
            "local_path": meta.local_path,
            "file_size": meta.file_size,
            "remote_modified": meta.remote_modified.isoformat() if meta.remote_modified else None,
            "download_time": meta.download_time.isoformat(),
            "checksum": meta.checksum,
        }
```

### 3.6 IEC61850Client 集成

在 `iec61850_client.py` 中添加 `files` 属性：

```python
# ===== 插件属性 (按需暴露) =====

@property
def files(self):
    """获取 Files 插件 (文件下载服务)"""
    return self._plugins.get("files")
```

同时添加便捷方法：

```python
# ===== 文件操作 (委托给 Files 插件) =====

def list_remote_files(self, directory: str = "") -> List[Dict[str, Any]]:
    """浏览远程 IED 文件目录"""
    fp = self.files
    if fp:
        return fp.list_directory(directory)
    return []

def download_remote_file(self, filename: str, local_path: str = "") -> bytes:
    """从远程 IED 下载文件"""
    fp = self.files
    if fp:
        return fp.get_file(filename, local_path)
    return b""
```

### 3.7 后端 Web API

新增路由文件 `src/api/iec61850_files.py`：

| 方法 | 路径 | 说明 | 请求参数 | 返回 |
|------|------|------|---------|------|
| GET | `/api/iec61850/files/directory` | 获取远程目录列表 | `directory` (可选) | `FileEntry[]` |
| GET | `/api/iec61850/files/directory/tree` | 递归获取目录树 | `directory`, `max_depth` | `FileEntry[]` |
| GET | `/api/iec61850/files/download` | 下载远程文件 | `filename` (远程路径), `use_cache` (是否使用缓存) | 文件流 / `{"data": "base64..."}` |
| POST | `/api/iec61850/files/upload` | 上传文件到 IED | `file` (multipart), `remote_filename` | `{"success": true}` |
| DELETE | `/api/iec61850/files/remote` | 删除远程文件 | `filename` | `{"success": true}` |
| GET | `/api/iec61850/files/cache` | 获取本地缓存列表 | — | `FileMetadata[]` |
| DELETE | `/api/iec61850/files/cache` | 清理本地缓存 | `remote_path` (可选，为空则全清) | `{"cleared": 3}` |

**下载接口设计考量**：

```
方式 A: 返回文件流 (适合大文件，浏览器直接下载)
        GET /api/iec61850/files/download?filename=/logs/fault1.comtrade
        → Content-Type: application/octet-stream
        → Content-Disposition: attachment; filename="fault1.comtrade"

方式 B: 返回 JSON (适合小文件/前端预览)
        GET /api/iec61850/files/download?filename=/config.icd&format=json
        → {"filename": "config.icd", "data": "base64...", "size": 1234}

推荐: 默认方式 A，通过 Accept 头或 format 参数切换。
```

### 3.8 前端组件设计

```
front/src/views/iec61850/
├── FileExplorer.vue          # 文件浏览器主页面
├── components/
│   ├── RemoteFileTree.vue    # 远程文件目录树 (递归组件)
│   ├── FileList.vue          # 文件列表/详情面板
│   ├── FileUpload.vue        # 上传管理 (拖拽 + 进度)
│   ├── DownloadProgress.vue  # 下载进度条
│   └── CacheManager.vue      # 本地缓存管理
```

**RemoteFileTree.vue** 关键交互：

```
┌────────────────────────────────────────────────┐
│ 📁 /                          [🔄 刷新] [⬆ 上传] │
│ ├─ 📁 logs/                                      │
│ │  ├─ 📄 fault1.comtrade     2.3MB  2026-05-30   │
│ │  ├─ 📄 fault2.comtrade     1.1MB  2026-05-29   │
│ │  └─ 📄 system.log          456KB  2026-05-31   │
│ ├─ 📁 config/                                     │
│ │  └─ 📄 current.icd         89KB   2026-05-28   │
│ └─ 📄 README.txt             2KB    2026-05-01   │
│                                                   │
│ [⬇ 下载] [🗑 删除] [📋 属性]                       │
└────────────────────────────────────────────────┘
```

### 3.9 与 SCL 模块的协作

FilesPlugin 下载 ICD/SCD/CID 文件后，可通过上层服务自动触发 SCL 解析：

```python
# 在 Web API 层实现协作 (不在插件内部)
@router.post("/api/iec61850/files/download-and-import")
async def download_and_import_scl(filename: str):
    """下载远程 ICD 文件并自动导入"""
    # 1. 通过 FilesPlugin 下载文件
    file_bytes = client.files.get_file(filename)
    
    # 2. 保存到临时文件
    temp_path = save_temp_file(file_bytes)
    
    # 3. 调用 SCL 模块解析
    result = scl_service.import_icd(temp_path)
    
    return {"download": "ok", "import": result}
```

---

## 4. 分阶段实施计划

### Phase 1: 数据类型与目录浏览 (P0, 预计 2 天)

**目标**：实现 FilesPlugin 完整骨架 + DirectoryBrowser，可浏览远程 IED 文件系统。

| 任务 | 文件 | 说明 |
|------|------|------|
| 创建 `types.py` | `plugins/files/types.py` | FileEntry, TransferProgress, FileMetadata 数据类 |
| 实现 `DirectoryBrowser` | `plugins/files/directory.py` | list_directory + list_directory_recursive + moreFollows 处理 |
| 重构 `FilesPlugin` | `plugins/files/__init__.py` | 替换空实现，组合 DirectoryBrowser |
| 添加 Client 属性 | `iec61850_client.py` | 添加 `files` property + 便捷方法 |

**验收标准**：

- [ ] `client.files.list_directory("/")` 返回远程 IED 根目录文件列表
- [ ] `client.files.list_directory_recursive("/")` 返回递归目录树
- [ ] 目录条目包含文件名、大小、修改时间、类型 (文件/目录)
- [ ] moreFollows 分页正确处理 (目录条目超过单个 PDU 容量)
- [ ] 目录判断逻辑正确 (以 "/" 结尾 或 尝试进入)
- [ ] 连接断开时返回空列表而非抛出异常

### Phase 2: 文件下载与上传 (P0, 预计 3 天)

**目标**：实现完整的文件下载/上传/删除功能。

| 任务 | 文件 | 说明 |
|------|------|------|
| 实现 `FileTransfer` | `plugins/files/transfer.py` | download_file + download_file_to_bytes + upload_file + delete_file |
| 实现 GetFile 回调 | `plugins/files/transfer.py` | IedClientGetFileHandler 分块接收 + 进度计算 |
| 实现 SetFile 上传 | `plugins/files/transfer.py` | IedConnection_setFile + filestore 基路径设置 |
| 实现 DeleteFile | `plugins/files/transfer.py` | IedConnection_deleteFile |
| 传输进度管理 | `plugins/files/transfer.py` | TransferProgress 状态机 + 取消机制 |

**验收标准**：

- [ ] `client.files.get_file("/logs/fault.comtrade", local_path="./fault.comtrade")` 下载文件到本地
- [ ] `client.files.get_file("/config.icd")` 下载小文件到内存，返回 bytes
- [ ] 大文件 (10MB+) 下载正常，内存占用不超过分块大小
- [ ] 下载进度回调正常触发 (bytes_transferred / total_bytes)
- [ ] `client.files.upload_file(local, "/config/new.icd")` 上传文件到 IED
- [ ] `client.files.delete_file("/temp/old.log")` 删除远程文件
- [ ] 下载/上传过程中连接断开，抛出明确异常并清理资源
- [ ] 远程文件不存在时返回明确错误 (非空 bytes)

### Phase 3: 本地缓存管理 (P1, 预计 1.5 天)

**目标**：实现本地缓存管理，避免重复下载。

| 任务 | 文件 | 说明 |
|------|------|------|
| 实现 `CacheManager` | `plugins/files/cache.py` | 缓存存储/查询/淘汰/清理 |
| 缓存索引持久化 | `plugins/files/cache.py` | JSON 索引文件读写 |
| LRU 淘汰策略 | `plugins/files/cache.py` | 容量限制 + 最近最少使用淘汰 |
| 下载自动缓存 | `plugins/files/__init__.py` | get_file 下载后自动加入缓存 |
| 缓存有效性校验 | `plugins/files/cache.py` | 比较远程修改时间判断缓存是否过期 |

**验收标准**：

- [ ] 下载文件后自动缓存到 `data/61850_cache/` 目录
- [ ] 重复下载相同文件时命中缓存，不发起 MMS 请求
- [ ] 缓存索引持久化，重启后缓存仍然有效
- [ ] 远程文件修改后，缓存自动失效并重新下载
- [ ] 缓存空间超过限制时自动执行 LRU 淘汰
- [ ] `client.files.clear_cache()` 可清空所有缓存

### Phase 4: 后端 Web API (P0, 预计 2 天)

**目标**：提供完整的 HTTP 接口供前端调用。

| 任务 | 文件 | 说明 |
|------|------|------|
| 创建文件服务路由 | `src/api/iec61850_files.py` | 7 个 API 端点 |
| 文件下载接口 | `src/api/iec61850_files.py` | 流式下载 + JSON 下载双模式 |
| 文件上传接口 | `src/api/iec61850_files.py` | multipart 上传 + 转发到 IED |
| WebSocket 进度 | `src/api/iec61850_files.py` | 传输进度实时推送 (可选) |
| 注册路由 | `src/api/__init__.py` | 挂载文件服务路由 |

**验收标准**：

- [ ] `GET /api/iec61850/files/directory` 返回远程目录列表
- [ ] `GET /api/iec61850/files/download?filename=xxx` 触发浏览器文件下载
- [ ] `POST /api/iec61850/files/upload` 上传文件到 IED
- [ ] `DELETE /api/iec61850/files/remote?filename=xxx` 删除远程文件
- [ ] `GET /api/iec61850/files/cache` 返回本地缓存列表
- [ ] 所有接口包含错误处理和 IED 连接状态检查

### Phase 5: 前端文件浏览器 UI (P1, 预计 3 天)

**目标**：实现可视化文件浏览器界面。

| 任务 | 文件 | 说明 |
|------|------|------|
| FileExplorer 主页 | `front/src/views/iec61850/FileExplorer.vue` | 左右分栏布局 |
| RemoteFileTree 组件 | `front/src/views/iec61850/components/RemoteFileTree.vue` | 递归目录树 + 懒加载 |
| FileList 组件 | `front/src/views/iec61850/components/FileList.vue` | 文件列表 + 排序 + 筛选 |
| DownloadProgress 组件 | `front/src/views/iec61850/components/DownloadProgress.vue` | 进度条 + 状态展示 |
| FileUpload 组件 | `front/src/views/iec61850/components/FileUpload.vue` | 拖拽上传 + 进度 |
| fileApi 接口层 | `front/src/api/iec61850/fileApi.ts` | 封装文件服务 API |
| 路由注册 | `front/src/router/` | 添加文件浏览器路由 |

**验收标准**：

- [ ] 文件目录树正常显示，支持逐级展开
- [ ] 点击文件可查看属性 (大小/修改时间)
- [ ] 下载按钮触发文件下载，显示进度条
- [ ] 拖拽上传文件到远程 IED
- [ ] 右键菜单支持删除远程文件
- [ ] 本地缓存管理面板可查看/清理缓存
- [ ] 连接断开时 UI 显示友好提示

### Phase 6: 集成测试与增强 (P2, 预计 2 天)

**目标**：端到端测试、边界情况处理、与 SCL 模块协作。

| 任务 | 文件 | 说明 |
|------|------|------|
| 集成测试 | `tests/test_files_plugin.py` | 目录浏览/下载/上传/缓存 全流程测试 |
| IED 不支持文件服务 | `plugins/files/` | 优雅降级 (返回空列表 + 日志提示) |
| 大文件传输测试 | `tests/` | 100MB+ 文件下载稳定性 |
| SCL 文件下载+导入 | `src/api/iec61850_files.py` | 下载 ICD 并自动导入 SCL 模块 |
| 文件名编码处理 | `plugins/files/directory.py` | 中文文件名/特殊字符兼容 |
| 异步 API 支持 | `plugins/files/transfer.py` | getFileAsync / setFileAsync 异步传输 |

**验收标准**：

- [ ] 从真实 IED 下载文件 (comtrade / log / icd) 成功
- [ ] IED 不支持文件服务时优雅降级，不影响其他功能
- [ ] 大文件 (100MB+) 传输不会内存溢出
- [ ] 下载 ICD 文件后可一键导入测点 (SCL 协作)
- [ ] 中文文件名正确显示和下载

---

## 5. 关键技术要点

### 5.1 pyiec61850 文件服务 API 对照

| C 函数 | Python 绑定 | 用途 | 回调 |
|--------|------------|------|------|
| `IedConnection_getFileDirectory` | `iec61850.IedConnection_getFileDirectory(conn, err, dirName)` | 获取完整目录 | — |
| `IedConnection_getFileDirectoryEx` | `iec61850.IedConnection_getFileDirectoryEx(conn, err, dirName, continueAfter, moreFollows)` | 分页获取目录 | — |
| `IedConnection_getFileDirectoryAsyncEx` | 异步获取目录 | 回调 `FileDirectoryEntryHandler` |
| `IedConnection_getFile` | `iec61850.IedConnection_getFile(conn, err, fileName, handler, param)` | 同步下载文件 | 回调 `IedClientGetFileHandler` |
| `IedConnection_getFileAsync` | 异步下载文件 | 回调 `GetFileAsyncHandler` |
| `IedConnection_setFile` | `iec61850.IedConnection_setFile(conn, err, srcName, dstName)` | 上传文件 | — |
| `IedConnection_setFileAsync` | 异步上传文件 | 回调 `GenericServiceHandler` |
| `IedConnection_deleteFile` | `iec61850.IedConnection_deleteFile(conn, err, fileName)` | 删除文件 | — |
| `IedConnection_deleteFileAsync` | 异步删除文件 | 回调 `GenericServiceHandler` |
| `FileDirectoryEntry_getFileName` | `iec61850.FileDirectoryEntry_getFileName(entry)` | 获取文件名 | — |
| `FileDirectoryEntry_getFileSize` | `iec61850.FileDirectoryEntry_getFileSize(entry)` | 获取文件大小 | — |
| `FileDirectoryEntry_getLastModified` | `iec61850.FileDirectoryEntry_getLastModified(entry)` | 获取修改时间 | — |
| `FileDirectoryEntry_destroy` | `iec61850.FileDirectoryEntry_destroy(entry)` | 销毁条目 | — |
| `LinkedList_destroyDeep` | `iec61850.LinkedList_destroyDeep(list, FileDirectoryEntry_destroy)` | 释放目录列表 | — |

### 5.2 GetFile 回调机制

libiec61850 的 `IedConnection_getFile` 采用**回调式分块传输**：

```python
from pyiec61850 import pyiec61850 as iec61850

# 回调函数签名: handler(parameter, buffer, bytesRead) -> bool
#   - parameter: 用户数据
#   - buffer: 当前数据块 (bytes)
#   - bytesRead: 当前块字节数
#   - 返回 True 继续传输, False 取消传输

output_file = open("local_file.dat", "wb")
total_received = [0]

def get_file_handler(parameter, buffer, bytes_read):
    output_file.write(buffer[:bytes_read])
    total_received[0] += bytes_read
    return True  # 继续传输

# 调用
err = iec61850.IedClientError()
bytes_received = iec61850.IedConnection_getFile(
    connection, err, "/remote/file.dat", get_file_handler, None
)

output_file.close()
```

### 5.3 目录条目的文件/目录判断

IEC 61850 的 `GetFileDirectory` 响应中**没有显式的文件/目录类型字段**。判断方法：

| 方法 | 可靠性 | 说明 |
|------|--------|------|
| 文件名以 "/" 结尾 | 🟡 中 | libiec61850 部分实现会在目录名后追加 "/" |
| 文件大小为 0 | 🟢 较高 | 目录通常大小为 0，但空文件也是 0 |
| 尝试 GetFileDirectory 子路径 | 🟢 高 | 若能获取到子目录列表，则为目录 |
| 尝试 GetFile | 🟡 中 | 若能打开则为文件，但某些目录也可能响应 |
| **组合判断** | 🟢 **推荐** | 先检查 "/" 后缀 → 再尝试 GetFileDirectory → 默认为文件 |

### 5.4 SetFile 的文件库基路径

`IedConnection_setFile` 要求上传的文件必须在客户端的 VMD 虚拟文件库中。需在调用前设置基路径：

```python
# 设置本地文件库基路径 (需编译时启用 CONFIG_SET_FILESTORE_BASEPATH_AT_RUNTIME)
iec61850.IedConnection_setFilestoreBasepath(connection, "/path/to/local/vmd-root")

# 之后 setFile 的 sourceFilename 是相对于此基路径的
iec61850.IedConnection_setFile(connection, err, "config.icd", "/remote/config.icd")
```

### 5.5 内存管理

pyiec61850 的 C 层需要手动释放资源：

```python
# 获取目录列表后必须释放
file_list, error = iec61850.IedConnection_getFileDirectory(connection, err, "")
if file_list:
    # ... 使用列表 ...
    iec61850.LinkedList_destroyDeep(file_list, iec61850.FileDirectoryEntry_destroy)
```

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| **pyiec61850 未绑定文件服务函数** | 🟡 中 | 🔴 高 | 首次开发前验证 pyiec61850 是否暴露 `IedConnection_getFile*` 等函数；若未绑定，需编译更新 pyiec61850 |
| **IED 不支持文件服务** | 🟡 中 | 🟡 中 | 检测 `IedClientError` 返回 `IED_ERROR_OBJECT_ACCESS_UNSUPPORTED`，优雅降级 |
| **大文件传输超时** | 🟡 中 | 🟡 中 | 分块传输天然避免单次超时；增加超时配置和重试机制 |
| **SetFile 基路径不可配** | 🟢 低 | 🟡 中 | 检查 pyiec61850 编译选项，必要时回退到手动文件放置 |
| **目录判断不准** | 🟡 中 | 🟢 低 | 采用组合判断策略 + 前端允许用户手动标记 |
| **文件名编码问题** | 🟢 低 | 🟢 低 | 统一使用 UTF-8 编码，对异常编码做容错处理 |
| **MMS 连接数限制** | 🟢 低 | 🟡 中 | 文件传输与数据读取共享连接，大文件传输时可能阻塞其他操作 |

---

## 7. 参考文档

| 文档 | 说明 |
|------|------|
| IEC 61850-7-2 §7.5 | ACSI File Management 服务定义 |
| IEC 61850-8-1 §11 | MMS 映射 — 文件服务映射到 MMS |
| [libiec61850 File Service API](https://support.mz-automation.de/doc/libiec61850/c/latest/group__IEC61850__CLIENT__FILE__SERVICE.html) | C 层文件服务函数参考 |
| [MMS Server and File Services](https://deepwiki.com/mz-automation/libiec61850/2.2-mms-server-and-file-services) | 文件服务架构详解 |
| [iec61850-scl-file-module.md](./iec61850-scl-file-module.md) | SCL 文件模块计划 (注意区分) |
| [iec61850-refactoring-plan.md](./iec61850-refactoring-plan.md) | IEC 61850 模块化重构计划 |
