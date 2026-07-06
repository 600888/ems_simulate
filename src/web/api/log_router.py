"""日志查看 API - 读取后端日志文件，支持按模块/设备/等级筛选和分页"""

from datetime import datetime
import os
import re

from fastapi import APIRouter, Query

from src.config.global_config import LOG_DIR
from src.config.log.device_logger import DeviceLoggerManager
from src.web.api.schemas import BaseResponse

log_router = APIRouter(prefix="/api/logs", tags=["日志"])

# 模块 -> 日志文件映射
MODULE_LOG_FILES: dict[str, str] = {
    "system": "ems_simulate.log",
    "web": "web.log",
    "database": "db.log",
    "iec61850": "iec61850.log",
    "iec104": "iec104.log",
    "simulator": "simulate.log",
}

# 记录服务器启动时间，用于错误日志计数只统计本次启动后的日志
_SERVER_STARTUP_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
# 错误计数重置时间点，初始与启动时间一致，打开日志弹框时更新
_LAST_ERROR_RESET_TIME = _SERVER_STARTUP_TIME

# ANSI 转义码
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# 已知的日志等级（大写，匹配括号内的内容）
_KNOWN_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}

# 日志行解析正则
# 分组: 1=timestamp, 2=第一个 meta 括号(可能是等级或模块), 3=消息内容
_LOG_LINE_RE = re.compile(
    r"(?:\x1b\[[0-9;]*[a-zA-Z])*"  # 开头可能的 ANSI
    r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{3})?)\]\s*"  # [timestamp]
    r"(.*)"  # 剩余部分
)


def _strip_ansi(text: str) -> str:
    """去除 ANSI 颜色转义码"""
    return _ANSI_RE.sub("", text)


def _extract_level(metadata_text: str) -> str:
    """从元数据文本中提取日志等级，如 INFO / WARNING / ERROR"""
    for bracket in re.findall(r"\[([^\]]+)\]", metadata_text):
        upper = bracket.strip().upper()
        if upper in _KNOWN_LEVELS:
            return upper
    return ""


def _parse_log_line(line: str) -> tuple[str, str, str] | None:
    """解析单行日志，返回 (time, level, content) 或 None"""
    line = line.rstrip("\n\r")
    if not line:
        return None

    clean = _strip_ansi(line)
    m = _LOG_LINE_RE.match(clean)
    if m:
        time_str = m.group(1)
        rest = m.group(2).strip()

        # 从剩余的 [meta] 中提取等级
        level = _extract_level(rest)

        # 移除所有 [meta] 前缀，只留消息内容
        content = re.sub(r"^(\[.*?\]\s*)*", "", rest).strip()
        return time_str, level, content

    # 退一步匹配
    fallback = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{3})?)\]\s*(.*)", clean)
    if fallback:
        ts = fallback.group(1)
        rest = fallback.group(2).strip()
        level = _extract_level(rest)
        content = re.sub(r"^(\[.*?\]\s*)*", "", rest).strip()
        return ts, level, content

    return None


def _read_log_file(
    filepath: str,
    offset: int = 0,
    limit: int = 100,
    keyword: str = "",
    level: str = "",
) -> tuple[list[dict], int]:
    """读取日志文件，返回 (日志条目列表, 总行数)"""
    if not os.path.isfile(filepath):
        return [], 0

    with open(filepath, encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()

    total = len(all_lines)
    matched_lines: list[str] = []  # "time\tlevel\tcontent"

    for line in all_lines:
        parsed = _parse_log_line(line)
        if parsed is None:
            continue
        ts, lv, content = parsed
        if keyword and keyword not in line:
            continue
        if level and lv.upper() != level.upper():
            continue
        matched_lines.append(f"{ts}\t{lv}\t{content}")

    if not matched_lines:
        return [], total

    # 按时间倒序
    matched_lines.reverse()

    page_lines = matched_lines[offset : offset + limit]
    logs = []
    for entry in page_lines:
        parts = entry.split("\t", 2)
        logs.append(
            {
                "time": parts[0],
                "level": parts[1] if len(parts) > 1 else "",
                "content": parts[2] if len(parts) > 2 else "",
            }
        )

    return logs, total


def _get_device_names() -> list[str]:
    """从 DeviceLoggerManager 获取已注册的设备名称列表"""
    return list(DeviceLoggerManager._registered_devices.keys())


@log_router.get("/modules", response_model=BaseResponse)
async def list_log_modules():
    """获取所有可用的日志模块列表"""
    return BaseResponse(data={"modules": list(MODULE_LOG_FILES.keys())})


@log_router.get("/error-count", response_model=BaseResponse)
async def count_error_logs():
    """统计自上次重置后所有模块日志中 ERROR 级别的日志条数"""
    total_errors = 0
    for filename in MODULE_LOG_FILES.values():
        filepath = os.path.join(LOG_DIR, filename)
        if not os.path.isfile(filepath):
            continue
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                for line in f:
                    parsed = _parse_log_line(line)
                    if parsed and parsed[1] == "ERROR":
                        if parsed[0] >= _LAST_ERROR_RESET_TIME:
                            total_errors += 1
        except OSError:
            continue
    return BaseResponse(data={"error_count": total_errors})


@log_router.post("/reset-error-count", response_model=BaseResponse)
async def reset_error_count():
    """重置错误计数，将统计起点设为当前时间"""
    global _LAST_ERROR_RESET_TIME
    _LAST_ERROR_RESET_TIME = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return BaseResponse(data={"reset_since": _LAST_ERROR_RESET_TIME})


@log_router.get("/devices", response_model=BaseResponse)
async def list_log_devices():
    """获取所有有独立日志文件的设备列表"""
    return BaseResponse(data={"devices": _get_device_names()})


@log_router.get("/query", response_model=BaseResponse)
async def query_logs(
    module: str = Query("", description="日志模块"),
    device: str = Query("", description="设备名称"),
    level: str = Query("", description="日志等级 (INFO/WARNING/ERROR/DEBUG 等)"),
    offset: int = Query(0, ge=0, description="偏移行数"),
    limit: int = Query(100, ge=1, le=1000, description="返回条数"),
    keyword: str = Query("", description="关键词搜索"),
):
    """查询日志内容，支持分页和筛选"""
    if device:
        log_file = os.path.join(LOG_DIR, device, f"{device}.log")
        logs, total = _read_log_file(log_file, offset, limit, keyword, level)
        return BaseResponse(data={"total": total, "offset": offset, "limit": limit, "logs": logs})

    if module and module in MODULE_LOG_FILES:
        log_file = os.path.join(LOG_DIR, MODULE_LOG_FILES[module])
        logs, total = _read_log_file(log_file, offset, limit, keyword, level)
        return BaseResponse(data={"total": total, "offset": offset, "limit": limit, "logs": logs})

    # 全部模块
    all_results: list[tuple[str, str, str]] = []  # (time, level, content)
    for filename in MODULE_LOG_FILES.values():
        filepath = os.path.join(LOG_DIR, filename)
        if not os.path.isfile(filepath):
            continue
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                for line in f:
                    parsed = _parse_log_line(line)
                    if parsed is None:
                        continue
                    ts, lv, content = parsed
                    if keyword and keyword not in line:
                        continue
                    if level and lv.upper() != level.upper():
                        continue
                    all_results.append((ts, lv, content))
        except OSError:
            continue

    all_results.sort(key=lambda x: x[0], reverse=True)
    total = len(all_results)
    page_results = all_results[offset : offset + limit]
    logs = [{"time": t, "level": lv, "content": c} for t, lv, c in page_results]

    return BaseResponse(data={"total": total, "offset": offset, "limit": limit, "logs": logs})
