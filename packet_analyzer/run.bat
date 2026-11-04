@echo off
setlocal
cd /d "%~dp0"

rem 优先使用能导入 PySide6 的解释器，避免误选空 venv 导致启动失败
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" -c "import PySide6" >nul 2>&1
    if not errorlevel 1 (
        "%~dp0.venv\Scripts\python.exe" "%~dp0main.py" %*
        goto :end
    )
    echo [WARN] .\venv 中未安装 PySide6，尝试其它解释器...
)

if exist "%~dp0..\.venv\Scripts\python.exe" (
    "%~dp0..\.venv\Scripts\python.exe" -c "import PySide6" >nul 2>&1
    if not errorlevel 1 (
        "%~dp0..\.venv\Scripts\python.exe" "%~dp0main.py" %*
        goto :end
    )
    echo [WARN] ..\.venv 中未安装 PySide6，回退到系统 python...
)

python -c "import PySide6" >nul 2>&1
if not errorlevel 1 (
    python "%~dp0main.py" %*
    goto :end
)

echo [ERROR] 找不到已安装 PySide6 的 Python 解释器。
echo         请执行: pip install -r requirements.txt
pause

:end
endlocal
