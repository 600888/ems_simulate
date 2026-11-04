# -*- coding: utf-8 -*-
# 电力协议报文解析器 —— Windows 打包脚本（PyInstaller onedir）
#
# 用法：
#   .\build_windows.ps1               # 完整打包
#   .\build_windows.ps1 -SkipBuild     # 只重新组装 zip（复用已有 dist）
#   .\build_windows.ps1 -Help

param(
    [switch]$SkipBuild,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$APP_NAME = "PacketAnalyzer"
$TOOL_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_ROOT = Split-Path -Parent $TOOL_DIR
$PYTHON_EXE = Join-Path $PROJECT_ROOT ".venv\Scripts\python.exe"
$SPEC_FILE = Join-Path $TOOL_DIR "packet_analyzer.spec"
$WORK_DIR = Join-Path $TOOL_DIR "build\work"
$DIST_DIR = Join-Path $TOOL_DIR "dist"
$APP_DIR = Join-Path $DIST_DIR $APP_NAME
$OUT_DIR = Join-Path $TOOL_DIR "build\windows"
$ZIP_OUTPUT = Join-Path $OUT_DIR "${APP_NAME}_windows.zip"

function Write-Step($message) { Write-Host "[STEP] $message" -ForegroundColor Cyan }
function Write-Success($message) { Write-Host "[SUCCESS] $message" -ForegroundColor Green }
function Write-Error($message) { Write-Host "[ERROR] $message" -ForegroundColor Red }
function Write-Info($message) { Write-Host "[INFO] $message" -ForegroundColor Yellow }

if ($Help) {
    Write-Host @"
电力协议报文解析器 打包脚本

用法：.\build_windows.ps1 [-SkipBuild] [-Help]

  -SkipBuild   跳过 PyInstaller，仅用已有 dist 重新生成 zip
  -Help        显示本帮助

依赖：在项目根目录 .venv 中安装 PySide6 与 pyinstaller
   uv pip install PySide6 pyinstaller

产物：dist\PacketAnalyzer\PacketAnalyzer.exe
      build\windows\PacketAnalyzer_windows.zip
"@
    exit 0
}

if (-not (Test-Path $PYTHON_EXE)) {
    Write-Error "未找到虚拟环境解释器：$PYTHON_EXE"
    Write-Info "请先在项目根目录执行 uv sync，或手动创建 .venv 并安装 PySide6 + pyinstaller"
    exit 1
}

if ($SkipBuild) {
    Write-Info "跳过打包，复用已有产物"
} else {
    Write-Step "检查打包依赖"
    & $PYTHON_EXE -c "import PySide6, PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "缺少 PySide6 或 PyInstaller，请先执行：uv pip install PySide6 pyinstaller"
        exit 1
    }

    # PyInstaller 的 --clean 与旧产物冲突，先移除工作目录
    foreach ($dir in @($WORK_DIR, $DIST_DIR)) {
        if (Test-Path $dir) {
            Write-Info "清理 $dir"
            Remove-Item -Recurse -Force $dir
        }
    }

    Write-Step "PyInstaller 打包（onedir）"
    Push-Location $TOOL_DIR
    try {
        & $PYTHON_EXE -m PyInstaller --noconfirm --clean `
            --workpath $WORK_DIR --distpath $DIST_DIR $SPEC_FILE
        if ($LASTEXITCODE -ne 0) {
            Write-Error "PyInstaller 打包失败"
            exit 1
        }
    } finally {
        Pop-Location
    }
    Write-Success "打包完成：$APP_DIR"
}

$exe_path = Join-Path $APP_DIR "$APP_NAME.exe"
if (-not (Test-Path $exe_path)) {
    Write-Error "未找到可执行文件：$exe_path"
    exit 1
}

Write-Step "生成分发包"
if (-not (Test-Path $OUT_DIR)) {
    New-Item -ItemType Directory -Path $OUT_DIR | Out-Null
}
if (Test-Path $ZIP_OUTPUT) {
    Remove-Item -Force $ZIP_OUTPUT
}
Compress-Archive -Path $APP_DIR -DestinationPath $ZIP_OUTPUT -CompressionLevel Optimal

$size_mb = [math]::Round((Get-Item $ZIP_OUTPUT).Length / 1MB, 1)
$dir_mb = [math]::Round(((Get-ChildItem $APP_DIR -Recurse | Measure-Object -Property Length -Sum).Sum) / 1MB, 1)
Write-Success "分发压缩包：$ZIP_OUTPUT（$size_mb MB）"
Write-Info "解压后目录体积：$dir_mb MB"
Write-Info "提示：分发时请保留整个 $APP_NAME 目录，不要只拷 exe"
