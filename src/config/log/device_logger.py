"""
设备日志模块 - 企业级 loguru 实现

使用 loguru 的 bind() 模式为每个设备创建上下文化的日志器。
支持：
- 每个设备独立的日志文件
- 统一的控制台输出
- 延迟初始化（按需创建日志文件）
- 线程安全的日志管理
"""

import os
import sys
import threading
from typing import Optional, Dict, Any
from loguru import logger

from src.config.global_config import ROOT_DIR


class DeviceLoggerManager:
    """设备日志管理器 - 单例模式
    
    集中管理所有设备的日志配置，确保：
    1. 每个设备有独立的日志文件
    2. 日志文件按设备名自动路由
    3. 延迟初始化，按需创建
    
    使用示例:
        # 获取设备日志器
        log = DeviceLoggerManager.get_logger("device_01")
        log.info("设备启动")
        
        # 或者在 Device 类中
        self._logger = DeviceLoggerManager.get_logger(self.name)
    """
    
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    _registered_devices: Dict[str, int] = {}  # device_name -> handler_id
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def _ensure_initialized(cls):
        """确保日志系统已初始化"""
        if not cls._initialized:
            with cls._lock:
                if not cls._initialized:
                    # 不调用 logger.remove()，避免影响其他模块的日志配置
                    # 只添加设备专用的控制台处理器
                    # 使用模板格式字符串，避免尖括号解析问题
                    cls._console_handler_id = logger.add(
                        sys.stderr,
                        level="DEBUG",
                        format="<green>[{time:YYYY-MM-DD HH:mm:ss.SSS}]</green> "
                               "<cyan>[{extra[device]}]</cyan> "
                               "<level>[{file.name}:{function}:{line}]</level> "
                               "<level>[{level}]</level> "
                               "{message}",
                        colorize=True,
                        enqueue=True,
                        filter=cls._device_console_filter,  # 只显示有 device 上下文的日志
                    )
                    
                    cls._initialized = True
    
    @classmethod
    def _device_console_filter(cls, record):
        """设备专用控制台过滤器 - 只显示有 device 上下文的日志"""
        return "device" in record["extra"]
    
    # 文件日志格式（无颜色）
    FILE_FORMAT = (
        "[{time:YYYY-MM-DD HH:mm:ss.SSS}] "
        "[{extra[device]}] "
        "[{file.name}:{function}:{line}] "
        "[{level}] "
        "{message}"
    )
    
    @classmethod
    def _create_device_filter(cls, device_name: str):
        """创建设备专用过滤器"""
        def filter_func(record):
            return record["extra"].get("device") == device_name
        return filter_func
    
    @classmethod
    def register_device(
        cls,
        device_name: str,
        log_level: str = "INFO",
        rotation: str = "1 MB",
        retention: str = "7 days",
        compression: Optional[str] = None,
    ) -> None:
        """注册设备日志处理器
        
        为指定设备创建独立的日志文件处理器。
        
        Args:
            device_name: 设备名称（用于日志文件命名和过滤）
            log_level: 文件日志级别
            rotation: 日志轮转配置（如 "1 MB", "1 day"）
            retention: 日志保留时间（如 "7 days"）
            compression: 压缩格式（如 "zip", "gz"）
        """
        cls._ensure_initialized()
        
        with cls._lock:
            # 避免重复注册
            if device_name in cls._registered_devices:
                return
            
            # 创建日志目录
            log_dir = os.path.join(ROOT_DIR, "log", device_name)
            os.makedirs(log_dir, exist_ok=True)
            
            log_file = os.path.join(log_dir, f"{device_name}.log")
            
            # 添加文件处理器
            handler_id = logger.add(
                log_file,
                level=log_level,
                format=cls.FILE_FORMAT,
                rotation=rotation,
                retention=retention,
                compression=compression,
                enqueue=True,
                filter=cls._create_device_filter(device_name),
            )
            
            cls._registered_devices[device_name] = handler_id
    
    @classmethod
    def unregister_device(cls, device_name: str) -> None:
        """注销设备日志处理器"""
        with cls._lock:
            if device_name in cls._registered_devices:
                handler_id = cls._registered_devices.pop(device_name)
                logger.remove(handler_id)
    
    @classmethod
    def get_logger(cls, device_name: str, auto_register: bool = True):
        """获取设备日志器
        
        返回一个绑定了设备上下文的 loguru 日志器。
        
        Args:
            device_name: 设备名称
            auto_register: 是否自动注册文件处理器
            
        Returns:
            绑定了设备上下文的日志器
        """
        cls._ensure_initialized()
        
        if auto_register and device_name not in cls._registered_devices:
            cls.register_device(device_name)
        
        # 同时绑定 device 和 task 键，确保与第三方库（如 dlt645）兼容
        # 第三方库可能期望 extra 中存在 task 键
        return logger.bind(device=device_name, task=device_name)


# 便捷函数
def get_device_logger(device_name: str, auto_register: bool = True):
    """获取设备日志器的便捷函数
    
    Args:
        device_name: 设备名称
        auto_register: 是否自动注册文件处理器
        
    Returns:
        绑定了设备上下文的日志器
        
    使用示例:
        from src.config.log.device_logger import get_device_logger
        
        log = get_device_logger("modbus_server_01")
        log.info("服务器启动")
        log.error("连接失败: {}", error_msg)
    """
    return DeviceLoggerManager.get_logger(device_name, auto_register)
