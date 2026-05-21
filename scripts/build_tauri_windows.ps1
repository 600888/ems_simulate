# Tauri Windows packaging script
param([switch]$SkipBuild, [switch]$SkipBackend, [switch]$Help)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_ROOT = Split-Path -Parent $SCRIPT_DIR
$TAURI_DIR = Join-Path $PROJECT_ROOT "src-tauri"
$BUILD_DIR = Join-Path $PROJECT_ROOT "build"

function WriteStep($m) { Write-Host "[STEP] $m" -ForegroundColor Cyan }
function WriteOk($m)   { Write-Host "[SUCCESS] $m" -ForegroundColor Green }
function WriteErr($m)  { Write-Host "[ERROR] $m" -ForegroundColor Red; exit 1 }

if ($Help) {
    Write-Host "Usage: .\build_tauri_windows.ps1 [-SkipBuild] [-SkipBackend]"
    exit 0
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  EMS Simulate Tauri Windows Packaging" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""

Set-Location $PROJECT_ROOT

# Check prerequisites
WriteStep "Checking build environment..."
$rv = rustc --version 2>$null
if (-not $rv) { WriteErr "Rust not found, https://rustup.rs/" }
$nv = node --version 2>$null
if (-not $nv) { WriteErr "Node.js not found" }
WriteOk "Rust: $rv"
WriteOk "Node.js: $nv"

# Generate icons
WriteStep "Generating Tauri icons..."
python scripts/generate_tauri_icons.py
if ($LASTEXITCODE -ne 0) { WriteErr "Icon generation failed" }

# Build frontend
if (-not $SkipBuild) {
    WriteStep "Building frontend..."
    Push-Location (Join-Path $PROJECT_ROOT "front")
    if (-not (Test-Path "node_modules")) { npm install }
    npm run build:fast
    if ($LASTEXITCODE -ne 0) { WriteErr "Frontend build failed" }
    WriteOk "Frontend build complete"
    Pop-Location
}

# Build Python backend
$BE_DIR = Join-Path $TAURI_DIR "ems_simulate_backend"

if (-not $SkipBackend) {
    WriteStep "Building Python backend (PyInstaller --onedir)..."
    New-Item -ItemType Directory -Force -Path $BE_DIR | Out-Null
    New-Item -ItemType Directory -Force -Path $BUILD_DIR | Out-Null

    $ABS = (Resolve-Path $PROJECT_ROOT).Path
    $pyDist = Join-Path $BUILD_DIR "dist"
    $pyWork = Join-Path $BUILD_DIR "build_pyinstaller_tauri"

    $pyArgs = @(
        "--noconfirm", "--onedir",
        "--name", "ems_simulate_backend", "--clean",
        "--distpath", $pyDist,
        "--workpath", $pyWork,
        "--specpath", $BUILD_DIR,
        "--add-data", "$ABS\config.ini;.",
        "--add-data", "$ABS\www;www",
        "--add-data", "$ABS\data;data"
    )
    $hidden = @(
        "uvicorn.logging", "uvicorn.loops", "openpyxl", "uvicorn.loops.auto",
        "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
        "uvicorn.lifespan", "uvicorn.lifespan.on", "uvicorn.loops.asyncio",
        "pymodbus", "fastapi", "sqlalchemy", "pydantic", "loguru"
    )
    foreach ($h in $hidden) { $pyArgs += "--hidden-import"; $pyArgs += $h }
    $pyArgs += "$ABS\start_back_end.py"

    pyinstaller @pyArgs
    if ($LASTEXITCODE -ne 0) { WriteErr "PyInstaller packaging failed" }

    $pyOut = Join-Path $pyDist "ems_simulate_backend"
    if (Test-Path $pyOut) {
        Copy-Item -Recurse -Force "$pyOut\*" $BE_DIR -ErrorAction SilentlyContinue
        WriteOk "Python backend packaged to: $BE_DIR"
    }
}

# Build Tauri
WriteStep "Building Tauri desktop app..."
Set-Location $TAURI_DIR

Write-Host "Ensuring Tauri CLI..."
cargo install tauri-cli --version "^2"
if ($LASTEXITCODE -ne 0) { WriteErr "Tauri CLI install failed" }

Write-Host "Running: cargo tauri build"
cargo tauri build
if ($LASTEXITCODE -ne 0) { WriteErr "Tauri build failed" }

# Copy backend next to release exe
if (Test-Path $BE_DIR) {
    $relDir = Join-Path $TAURI_DIR "target"
    $relDir = Join-Path $relDir "release"
    $destDir = Join-Path $relDir "ems_simulate_backend"
    Write-Host "Copying backend to release directory..."
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $destDir
    Start-Sleep -Milliseconds 500
    New-Item -ItemType Directory -Force -Path $destDir -ErrorAction SilentlyContinue | Out-Null
    Copy-Item -Recurse -Force "$BE_DIR\*" $destDir -ErrorAction SilentlyContinue
    $checkExe = Join-Path $destDir "ems_simulate_backend.exe"
    if (Test-Path $checkExe) {
        WriteOk "Backend copied to: $destDir"
    } else {
        Write-Host "[WARN] Backend copy may be incomplete" -ForegroundColor Yellow
    }
}

# Summary
$exePath = Join-Path $TAURI_DIR "target"
$exePath = Join-Path $exePath "release"
$exePath = Join-Path $exePath "ems-simulate.exe"

$bundlePath = Join-Path $TAURI_DIR "target"
$bundlePath = Join-Path $bundlePath "release"
$bundlePath = Join-Path $bundlePath "bundle"

Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  Tauri Build Complete!" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "exe: $exePath" -ForegroundColor Yellow
Write-Host "bundle: $bundlePath" -ForegroundColor Yellow
Write-Host ""
Write-Host "run:" -ForegroundColor Cyan
Write-Host "  $exePath" -ForegroundColor White
Write-Host ""
