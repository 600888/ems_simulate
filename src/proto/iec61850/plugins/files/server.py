"""Local file store exposed by an IEC 61850 MMS server."""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile

from ...log import log
from .types import FileEntry, FileType


class ServerFileService:
    """Manage the directory exported through the native MMS file service.

    The public methods intentionally mirror :class:`FilesPlugin` so the HTTP
    file explorer can work with client and server channels through one API.
    IEC 61850 paths always use ``/`` and are resolved below ``base_directory``.
    """

    def __init__(self, base_directory: str | os.PathLike[str]):
        self._base_directory = Path(base_directory).expanduser().resolve(strict=False)
        self._base_directory.mkdir(parents=True, exist_ok=True)
        if not self._base_directory.is_dir():
            raise ValueError(f"IEC61850 文件服务路径不是目录: {self._base_directory}")

        # Kept for compatibility with the shared cache-clear HTTP endpoint.
        # Server files are authoritative files, not disposable client cache.
        self._cache = None

    @property
    def base_directory(self) -> Path:
        """Return the absolute directory exported by libIEC61850."""
        return self._base_directory

    def list_directory(self, directory: str = "") -> list[dict[str, object]]:
        """List one directory without exposing host filesystem paths."""
        try:
            local_directory = self._resolve(directory, allow_root=True)
            if not local_directory.is_dir():
                return []

            entries: list[FileEntry] = []
            for child in sorted(local_directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold())):
                # Symlinks can escape the configured file store or change
                # underneath a request, so they are never published.
                if child.is_symlink():
                    continue
                try:
                    stat = child.stat()
                except OSError:
                    continue
                is_directory = child.is_dir()
                if not is_directory and not child.is_file():
                    continue
                entries.append(
                    FileEntry(
                        name=child.name,
                        file_type=FileType.DIRECTORY if is_directory else FileType.FILE,
                        size=0 if is_directory else stat.st_size,
                        last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                        full_path=self._remote_path(child),
                    )
                )
            return [entry.to_dict() for entry in entries]
        except (OSError, ValueError) as exc:
            log.warning(f"浏览 IEC61850 服务端文件目录失败: directory={directory!r}, error={exc}")
            return []

    def get_file_list(self, directory: str = "") -> list[dict[str, object]]:
        """Compatibility alias used by the client-side FilesPlugin API."""
        return self.list_directory(directory)

    def list_directory_recursive(self, directory: str = "", max_depth: int = 5) -> list[dict[str, object]]:
        """Return a flattened recursive directory listing."""
        if max_depth <= 0:
            return []

        result: list[dict[str, object]] = []

        def walk(remote_directory: str, depth: int) -> None:
            if depth >= max_depth:
                return
            for entry in self.list_directory(remote_directory):
                result.append(entry)
                if entry.get("type") == FileType.DIRECTORY.value:
                    walk(str(entry.get("full_path", "")), depth + 1)

        walk(directory, 0)
        return result

    def get_file(self, filename: str, *_args, **_kwargs) -> bytes:
        """Read a file from the exported store."""
        try:
            path = self._resolve(filename)
            if path.is_symlink() or not path.is_file():
                return b""
            return path.read_bytes()
        except (OSError, ValueError) as exc:
            log.warning(f"读取 IEC61850 服务端文件失败: filename={filename!r}, error={exc}")
            return b""

    def upload_file(self, local_path: str, remote_filename: str, *_args, **_kwargs) -> bool:
        """Atomically copy a local file into the exported store."""
        temporary_path: str | None = None
        try:
            source = Path(local_path)
            if source.is_symlink() or not source.is_file():
                return False
            destination = self._resolve(remote_filename)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and (destination.is_symlink() or not destination.is_file()):
                return False

            fd, temporary_path = tempfile.mkstemp(prefix=".iec61850-upload-", dir=str(destination.parent))
            os.close(fd)
            shutil.copyfile(source, temporary_path)
            os.replace(temporary_path, destination)
            temporary_path = None
            return True
        except (OSError, ValueError) as exc:
            log.warning(f"写入 IEC61850 服务端文件失败: filename={remote_filename!r}, error={exc}")
            return False
        finally:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass

    def delete_file(self, remote_filename: str) -> bool:
        """Delete one regular file; directory deletion is intentionally denied."""
        try:
            path = self._resolve(remote_filename)
            if path.is_symlink() or not path.is_file():
                return False
            path.unlink()
            return True
        except (OSError, ValueError) as exc:
            log.warning(f"删除 IEC61850 服务端文件失败: filename={remote_filename!r}, error={exc}")
            return False

    def get_cached_file(self, remote_path: str) -> str | None:
        """Return the authoritative local path for the shared download API."""
        try:
            path = self._resolve(remote_path)
            if path.is_symlink() or not path.is_file():
                return None
            return str(path)
        except ValueError:
            return None

    def list_cached_files(self) -> list[dict[str, object]]:
        """Server files are not client cache entries."""
        return []

    def clear_cache(self) -> int:
        """Do not remove authoritative server files through a cache action."""
        return 0

    def _resolve(self, remote_path: str, *, allow_root: bool = False) -> Path:
        raw_path = str(remote_path or "").replace("\\", "/")
        if "\x00" in raw_path:
            raise ValueError("文件路径包含空字符")

        parts = PurePosixPath(raw_path.lstrip("/")).parts
        if any(part in {"", ".", ".."} or ":" in part for part in parts):
            raise ValueError(f"非法 IEC61850 文件路径: {remote_path!r}")

        candidate = self._base_directory.joinpath(*parts).resolve(strict=False)
        try:
            candidate.relative_to(self._base_directory)
        except ValueError as exc:
            raise ValueError(f"IEC61850 文件路径越界: {remote_path!r}") from exc
        if not allow_root and candidate == self._base_directory:
            raise ValueError("文件路径不能为空")
        return candidate

    def _remote_path(self, local_path: Path) -> str:
        relative = local_path.relative_to(self._base_directory)
        return "/" + relative.as_posix()
