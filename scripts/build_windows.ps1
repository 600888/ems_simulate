# -*- coding: utf-8 -*-
# Windows Packaging Script for EMS Simulate
# Builds frontend, packages backend with PyInstaller, and creates a zip file

param(
    [switch]$SkipBuild,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Configuration
$APP_NAME = "ems-simulate"
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_ROOT = Split-Path -Parent $SCRIPT_DIR
# 从 pyproject.toml 读取版本号（单一真相源）
$PYPROJECT_PATH = Join-Path $PROJECT_ROOT "pyproject.toml"
$VERSION = (Get-Content $PYPROJECT_PATH | Select-String 'version\s*=\s*"([^"]+)"').Matches.Groups[1].Value
$BUILD_DIR = Join-Path $PROJECT_ROOT "build"
$OUTPUT_DIR = Join-Path $BUILD_DIR "windows"
$PYINSTALLER_DIR = Join-Path $BUILD_DIR "dist"
$PYINSTALLER_APP_DIR = Join-Path $PYINSTALLER_DIR "ems_simulate"
$ZIP_OUTPUT = Join-Path $BUILD_DIR "${APP_NAME}_windows_${VERSION}.zip"

# Color codes for output
function Write-Step($message) {
    Write-Host "[STEP] $message" -ForegroundColor Cyan
}

function Write-Success($message) {
    Write-Host "[SUCCESS] $message" -ForegroundColor Green
}

function Write-Error($message) {
    Write-Host "[ERROR] $message" -ForegroundColor Red
}

function Write-Info($message) {
    Write-Host "[INFO] $message" -ForegroundColor Yellow
}

# Display help
if ($Help) {
    Write-Host @"
EMS Simulate Windows Packaging Script

Usage: .\build_windows.ps1 [-SkipBuild] [-Help]

Options:
  -SkipBuild  Skip frontend build (use existing www directory)
  -Help       Display this help message

This script:
1. Builds the Vue.js frontend (npm run build:fast)
2. Installs Python dependencies
3. Creates a standalone Windows executable using PyInstaller
4. Packages everything into a zip file

After extraction, run the executable and access the app at:
  http://localhost:8991

"@
    exit 0
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  EMS Simulate Windows Packaging" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""

# Sync version to tauri.conf.json and package.json
Write-Step "Syncing version to config files..."
python "$SCRIPT_DIR\sync_version.py"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Version sync failed"
    exit 1
}
Write-Success "Version synced: $VERSION"

# Change to project root
Set-Location $PROJECT_ROOT
Write-Info "Project root: $PROJECT_ROOT"

# Step 1: Build Frontend
if (-not $SkipBuild) {
    Write-Step "Building frontend..."

    $FRONT_DIR = Join-Path $PROJECT_ROOT "front"
    Set-Location $FRONT_DIR

    # Check if node_modules exists
    if (-not (Test-Path "node_modules")) {
        Write-Info "Installing npm dependencies..."
        npm install
        if ($LASTEXITCODE -ne 0) {
            Write-Error "npm install failed"
            exit 1
        }
    }

    # Build frontend
    Write-Info "Running npm run build:fast..."
    npm run build:fast
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Frontend build failed"
        exit 1
    }

    Set-Location $PROJECT_ROOT

    # Verify www directory exists
    $WWW_DIR = Join-Path $PROJECT_ROOT "www"
    if (-not (Test-Path $WWW_DIR)) {
        Write-Error "Frontend build failed: www directory not found"
        exit 1
    }

    Write-Success "Frontend built successfully"
} else {
    Write-Info "Skipping frontend build"
}

# Step 2: Create build directories
Write-Step "Creating build directories..."
New-Item -ItemType Directory -Force -Path $BUILD_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $OUTPUT_DIR | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $BUILD_DIR "build_pyinstaller") | Out-Null
Write-Success "Build directories created"

# Step 3: Install Python dependencies
Write-Step "Installing Python dependencies..."
$PROJECT_ROOT_DIR = Split-Path $PSScriptRoot -Parent

if (Test-Path (Join-Path $PROJECT_ROOT_DIR "pyproject.toml")) {
    pip install .
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install Python dependencies"
        exit 1
    }
    Write-Success "Python dependencies installed"
} else {
    Write-Error "requirements.txt not found"
    exit 1
}

# Step 4: Build backend with PyInstaller
Write-Step "Building backend with PyInstaller..."

# Get absolute path
$ABS_PROJECT_ROOT = (Resolve-Path $PROJECT_ROOT).Path

# Build PyInstaller command
$PYINSTALLER_ARGS = @(
    "--noconfirm",
    "--onedir",
    "--name", "ems_simulate",
    "--clean",
    "--distpath", $PYINSTALLER_DIR,
    "--workpath", (Join-Path $BUILD_DIR "build_pyinstaller"),
    "--specpath", $BUILD_DIR
)

# Add data files (config, frontend, and bundled point tables)
$PYINSTALLER_ARGS += "--add-data"
$PYINSTALLER_ARGS += "${ABS_PROJECT_ROOT}\config.ini;."
$PYINSTALLER_ARGS += "--add-data"
$PYINSTALLER_ARGS += "${ABS_PROJECT_ROOT}\www;www"
$PYINSTALLER_ARGS += "--add-data"
$PYINSTALLER_ARGS += "${ABS_PROJECT_ROOT}\data\point_csv;data\point_csv"

# Add hidden imports
$HIDDEN_IMPORTS = @(
    "uvicorn.logging",
    "uvicorn.loops",
    "openpyxl",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.loops.asyncio",
    "pymodbus",
    "fastapi",
    "sqlalchemy",
    "pydantic",
    "loguru"
)

foreach ($import in $HIDDEN_IMPORTS) {
    $PYINSTALLER_ARGS += "--hidden-import"
    $PYINSTALLER_ARGS += $import
}

# Add the start script
$PYINSTALLER_ARGS += "$ABS_PROJECT_ROOT\start_back_end.py"

Write-Info "Running PyInstaller..."
pyinstaller @PYINSTALLER_ARGS

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed"
    exit 1
}

# Verify PyInstaller output
if (-not (Test-Path $PYINSTALLER_APP_DIR)) {
    Write-Error "PyInstaller did not create expected directory: $PYINSTALLER_APP_DIR"
    exit 1
}

$PACKAGED_POINT_TABLES = Get-ChildItem -Path $PYINSTALLER_APP_DIR -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match '[\\/]data[\\/]point_csv[\\/]' }
if (-not $PACKAGED_POINT_TABLES) {
    Write-Error "PyInstaller output is missing the bundled point tables"
    exit 1
}
Write-Success "Bundled point tables verified: $($PACKAGED_POINT_TABLES.Count) file(s)"

Write-Success "Backend built successfully"

# Step 5: Create package directory structure
Write-Step "Creating package structure..."

# Copy PyInstaller output to output directory
$PACKAGE_DIR = Join-Path $OUTPUT_DIR $APP_NAME
if (Test-Path $PACKAGE_DIR) {
    Remove-Item -Recurse -Force $PACKAGE_DIR
}
Copy-Item -Recurse $PYINSTALLER_APP_DIR $PACKAGE_DIR

# Create data directory for runtime database
$DATA_DIR = Join-Path $PACKAGE_DIR "data"
New-Item -ItemType Directory -Force -Path $DATA_DIR | Out-Null

# Copy config.ini to package
$CONFIG_SOURCE = Join-Path $PROJECT_ROOT "config.ini"
$CONFIG_DEST = Join-Path $PACKAGE_DIR "config.ini"
if (Test-Path $CONFIG_SOURCE) {
    Copy-Item $CONFIG_SOURCE $PACKAGE_DIR
}

Write-Success "Package structure created"

# Step 6: Create startup script
Write-Step "Creating startup script..."

$STARTUP_SCRIPT = @"
@echo off
chcp 65001 >nul
title EMS Simulate
echo ========================================
echo   EMS Simulate
echo ========================================
echo.
echo Starting server...
echo.
echo Access the application at:
echo   http://localhost:8991
echo.
echo API Documentation:
echo   http://localhost:8991/docs
echo.
echo Press Ctrl+C to stop the server
echo.

cd /d "%~dp0"
ems_simulate.exe
"@

$STARTUP_BATCH = Join-Path $PACKAGE_DIR "start.bat"
Set-Content -Path $STARTUP_BATCH -Value $STARTUP_SCRIPT -Encoding ASCII

# Create a PowerShell startup script with better handling
$STARTUP_PS1 = @"
`$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

`$SCRIPT_DIR = Split-Path -Parent `$MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  EMS Simulate" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Starting server..." -ForegroundColor Green
Write-Host ""
Write-Host "Access the application at:" -ForegroundColor Yellow
Write-Host "  http://localhost:8991" -ForegroundColor White
Write-Host ""
Write-Host "API Documentation:" -ForegroundColor Yellow
Write-Host "  http://localhost:8991/docs" -ForegroundColor White
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Gray
Write-Host ""

Set-Location `$SCRIPT_DIR
& ".\ems_simulate.exe"
"@

$STARTUP_PS1_FILE = Join-Path $PACKAGE_DIR "start.ps1"
Set-Content -Path $STARTUP_PS1_FILE -Value $STARTUP_PS1 -Encoding UTF8

Write-Success "Startup scripts created"

# Step 7: Create README for the package
Write-Step "Creating README..."

$README = @"
EMS Simulate - Windows Portable Package
=======================================

Version: $VERSION

Quick Start:
1. Double-click `start.bat` or `start.ps1` to start the server
2. Open your web browser and go to: http://localhost:8991
3. Use the API documentation at: http://localhost:8991/docs

System Requirements:
- Windows 10 or later
- No additional software required (standalone executable)

Features:
- Energy Management System (EMS) Simulator
- Supports Modbus TCP, IEC 104, IEC 61850, DL/T 645 protocols
- Web-based user interface
- RESTful API for integration

Directory Structure:
- ems_simulate/          # Main application folder
  - ems_simulate.exe     # Main executable
  - config.ini           # Configuration file
  - data/                # Database and data files
  - www/                 # Web frontend files
  - start.bat            # Quick start script (CMD)
  - start.ps1            # Quick start script (PowerShell)

Configuration:
Edit `config.ini` to change:
- Database settings
- Web server port (default: 8991)
- Protocol ports

Logs:
Logs are stored in the `logs` subdirectory.

Troubleshooting:
- If the port is already in use, change `web_port` in config.ini
- Check the `logs` directory for error messages
- Make sure the `data` directory is writable

For more information, visit the project documentation.
"@

$README_FILE = Join-Path $PACKAGE_DIR "README.txt"
Set-Content -Path $README_FILE -Value $README -Encoding UTF8

Write-Success "README created"

# Step 8: Create zip file
Write-Step "Creating zip file..."

# Remove existing zip if it exists
if (Test-Path $ZIP_OUTPUT) {
    Remove-Item $ZIP_OUTPUT -Force
}

# Create zip archive
Compress-Archive -Path "$PACKAGE_DIR\*" -DestinationPath $ZIP_OUTPUT -CompressionLevel Optimal

if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ZIP_OUTPUT)) {
    Write-Error "Failed to create zip file"
    exit 1
}

Write-Success "Zip file created: $ZIP_OUTPUT"

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  Build Complete!" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "Package location: $PACKAGE_DIR" -ForegroundColor White
Write-Host "Zip file: $ZIP_OUTPUT" -ForegroundColor White
Write-Host ""
Write-Host "To run the application:" -ForegroundColor Cyan
Write-Host "  1. Extract the zip file (if not already extracted)" -ForegroundColor White
Write-Host "  2. Run start.bat or start.ps1" -ForegroundColor White
Write-Host "  3. Open http://localhost:8991 in your browser" -ForegroundColor White
Write-Host ""
Write-Host "File size:" -ForegroundColor Cyan
$ZIP_SIZE = (Get-Item $ZIP_OUTPUT).Length / 1MB
Write-Host "  Zip: $([math]::Round($ZIP_SIZE, 2)) MB" -ForegroundColor White
Write-Host ""
