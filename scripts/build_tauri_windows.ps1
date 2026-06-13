# Tauri Windows packaging script (Sidecar mode)
param([switch]$SkipBuild, [switch]$SkipBackend, [switch]$Msix, [switch]$Help)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_ROOT = Split-Path -Parent $SCRIPT_DIR
$TAURI_DIR = Join-Path $PROJECT_ROOT "src-tauri"
$BUILD_DIR = Join-Path $PROJECT_ROOT "build"
$BINARIES_DIR = Join-Path $TAURI_DIR "binaries"

function WriteStep($m) { Write-Host "[STEP] $m" -ForegroundColor Cyan }
function WriteOk($m)   { Write-Host "[SUCCESS] $m" -ForegroundColor Green }
function WriteSkip($m) { Write-Host "[SKIP] $m" -ForegroundColor DarkGray }
function WriteErr($m)  { Write-Host "[ERROR] $m" -ForegroundColor Red; exit 1 }

# Check if a file is newer than a set of reference files/dirs.
# Returns $true if $target exists and is newer than ALL references.
function IsUpToDate($target, [string[]]$references) {
    if (-not (Test-Path $target)) { return $false }
    $targetTime = (Get-Item $target).LastWriteTime
    foreach ($ref in $references) {
        if (-not (Test-Path $ref)) { continue }
        $refTime = (Get-Item $ref).LastWriteTime
        if ($refTime -gt $targetTime) { return $false }
    }
    return $true
}

# Get the Rust target triple for the current platform
function GetRustTargetTriple {
    $triple = rustc -vV | Select-String "host: (.*)$" | ForEach-Object { $_.Matches.Groups[1].Value }
    return $triple
}

if ($Help) {
    Write-Host "Usage: .\build_tauri_windows.ps1 [-SkipBuild] [-SkipBackend] [-Msix]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -SkipBuild    Skip frontend build"
    Write-Host "  -SkipBackend  Skip Python backend build"
    Write-Host "  -Msix         Package as MSIX instead of MSI"
    exit 0
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  EMS Simulate Tauri Windows Packaging" -ForegroundColor Magenta
Write-Host "  (Sidecar mode)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""

Set-Location $PROJECT_ROOT

# Sync version to tauri.conf.json and package.json
WriteStep "Syncing version to config files..."
python "$SCRIPT_DIR\sync_version.py"
if ($LASTEXITCODE -ne 0) { WriteErr "Version sync failed" }
WriteOk "Version synced from pyproject.toml"

# Kill any running backend process that may lock www/ files
$beProc = Get-Process -Name "ems_simulate_backend" -ErrorAction SilentlyContinue
if ($beProc) {
    WriteStep "Stopping running backend process (locks www/ files)..."
    Stop-Process -Name "ems_simulate_backend" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    WriteOk "Backend process stopped"
}

# Check prerequisites
WriteStep "Checking build environment..."
$rv = rustc --version 2>$null
if (-not $rv) { WriteErr "Rust not found, https://rustup.rs/" }
$nv = node --version 2>$null
if (-not $nv) { WriteErr "Node.js not found" }
WriteOk "Rust: $rv"
WriteOk "Node.js: $nv"

# Generate icons (skip if all icons already exist and are newer than source)
$iconSource = Join-Path $PROJECT_ROOT "resources\icon.png"
$tauriIcons = @(
    (Join-Path $TAURI_DIR "icons\32x32.png"),
    (Join-Path $TAURI_DIR "icons\128x128.png"),
    (Join-Path $TAURI_DIR "icons\128x128@2x.png"),
    (Join-Path $TAURI_DIR "icons\icon.ico"),
    (Join-Path $TAURI_DIR "icons\icon.png")
)
$iconsUpToDate = $true
foreach ($ic in $tauriIcons) {
    if (-not (IsUpToDate $ic @($iconSource))) { $iconsUpToDate = $false; break }
}

if ($iconsUpToDate) {
    WriteSkip "Tauri icons are up-to-date"
} else {
    WriteStep "Generating Tauri icons..."
    python scripts/generate_tauri_icons.py
    if ($LASTEXITCODE -ne 0) { WriteErr "Icon generation failed" }
    WriteOk "Tauri icons generated"
}

# Build frontend
if (-not $SkipBuild) {
    $frontDir = Join-Path $PROJECT_ROOT "front"
    $frontDist = Join-Path $frontDir "dist"
    $frontSrcDir = Join-Path $frontDir "src"
    if ((Test-Path $frontDist) -and (IsUpToDate $frontDist @($frontSrcDir))) {
        WriteSkip "Frontend build is up-to-date"
    } else {
        WriteStep "Building frontend..."
        Push-Location $frontDir
        if (-not (Test-Path "node_modules")) { npm install }
        npm run build:fast
        if ($LASTEXITCODE -ne 0) { WriteErr "Frontend build failed" }
        WriteOk "Frontend build complete"
        Pop-Location
    }
} else {
    WriteSkip "Frontend build (skipped by flag)"
}

# Build Python backend (Sidecar: single file via --onefile)
$SIDECAR_TARGET = GetRustTargetTriple
$BE_SIDECAR_EXE = Join-Path $BINARIES_DIR "ems_simulate_backend-$SIDECAR_TARGET.exe"

if (-not $SkipBackend) {
    # Check if sidecar binary is up-to-date
    $beSources = @(
        (Join-Path $PROJECT_ROOT "start_back_end.py"),
        (Join-Path $PROJECT_ROOT "src"),
        (Join-Path $PROJECT_ROOT "config.ini"),
        (Join-Path $PROJECT_ROOT "pyproject.toml")
    )
    if ((Test-Path $BE_SIDECAR_EXE) -and (IsUpToDate $BE_SIDECAR_EXE $beSources)) {
        WriteSkip "Python backend (sidecar) is up-to-date"
    } else {
        WriteStep "Building Python backend (PyInstaller --onefile for Sidecar)..."

        # Clear old binaries directory
        Remove-Item -Recurse -Force $BINARIES_DIR -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 300
        New-Item -ItemType Directory -Force -Path $BINARIES_DIR | Out-Null
        New-Item -ItemType Directory -Force -Path $BUILD_DIR | Out-Null

        $ABS = (Resolve-Path $PROJECT_ROOT).Path
        $pyDist = Join-Path $BUILD_DIR "dist"
        $pyWork = Join-Path $BUILD_DIR "build_pyinstaller_tauri"

        $rthookNumpy = Join-Path $SCRIPT_DIR "rthook_numpy_compat.py"
        $pyArgs = @(
            "--noconfirm", "--onefile",
            "--name", "ems_simulate_backend", "--clean",
            "--distpath", $pyDist,
            "--workpath", $pyWork,
            "--specpath", $BUILD_DIR,
            "--runtime-hook", $rthookNumpy,
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

        # Copy the single-file exe to binaries/ with target-triple naming
        $pyOutExe = Join-Path $pyDist "ems_simulate_backend.exe"
        if (Test-Path $pyOutExe) {
            Copy-Item -Force $pyOutExe $BE_SIDECAR_EXE
            WriteOk "Sidecar binary created: $BE_SIDECAR_EXE"
        } else {
            WriteErr "PyInstaller output not found: $pyOutExe"
        }
    }
} else {
    WriteSkip "Python backend build (skipped by flag)"
}

# Build Tauri
# 确保 binaries/ 目录中只有 triple 命名的 sidecar 文件，清理可能残留的旧文件
WriteStep "清理 binaries/ 目录中非 triple 命名的文件..."
Get-ChildItem -Path $BINARIES_DIR -Filter "*.exe" | Where-Object {
    $_.Name -ne "ems_simulate_backend-$SIDECAR_TARGET.exe"
} | Remove-Item -Force -ErrorAction SilentlyContinue
WriteOk "binaries/ 目录已清理"

$tauriExe = Join-Path $TAURI_DIR "target\release\ems-simulate.exe"
$tauriSrc = Join-Path $TAURI_DIR "src"
$tauriCargo = Join-Path $TAURI_DIR "Cargo.toml"

if ((Test-Path $tauriExe) -and (IsUpToDate $tauriExe @($tauriSrc, $tauriCargo, $BE_SIDECAR_EXE))) {
    WriteSkip "Tauri build is up-to-date"
} else {
    WriteStep "Building Tauri desktop app..."
    Set-Location $TAURI_DIR

    Write-Host "Ensuring Tauri CLI..."
    cargo install tauri-cli --version "^2"
    if ($LASTEXITCODE -ne 0) { WriteErr "Tauri CLI install failed" }

    # Sidecar binary must be in place at binaries/ before build
    if (-not (Test-Path $BE_SIDECAR_EXE)) {
        WriteErr "Sidecar binary not found at $BE_SIDECAR_EXE. Run without -SkipBackend first."
    }

    if ($Msix) {
        # Tauri v2 不支持 MSIX 打包，先用 MSI 构建（仅获取 exe），后续手动打 MSIX
        Write-Host "Running: cargo tauri build --bundles msi"
        cargo tauri build --bundles msi
    } else {
        Write-Host "Running: cargo tauri build"
        cargo tauri build
    }
    if ($LASTEXITCODE -ne 0) { WriteErr "Tauri build failed" }
    WriteOk "Tauri build complete"
}

$relDir = Join-Path $TAURI_DIR "target\release"

# MSIX packaging (Tauri v2 does not natively support MSIX, so we use winapp CLI)
if ($Msix) {
    WriteStep "Packaging as MSIX..."

    # Check winapp CLI
    $winapp = Get-Command winapp -ErrorAction SilentlyContinue
    if (-not $winapp) {
        WriteErr "winapp CLI not found. Install with: winget install microsoft.winappcli --source winget"
    }
    WriteOk "winapp CLI found: $($winapp.Source)"

    # Generate MSIX assets (skip if already generated and source icon hasn't changed)
    $assetsDir = Join-Path $PROJECT_ROOT "Assets"
    $msixAssetScript = Join-Path $SCRIPT_DIR "generate_msix_assets.py"
    $storeLogo = Join-Path $assetsDir "StoreLogo.png"
    if ((Test-Path $storeLogo) -and (IsUpToDate $storeLogo @($iconSource))) {
        WriteSkip "MSIX icon assets are up-to-date"
    } else {
        WriteStep "Generating MSIX icon assets..."
        python $msixAssetScript
        if ($LASTEXITCODE -ne 0) { WriteErr "MSIX asset generation failed" }
        WriteOk "MSIX icon assets generated"
    }

    # Prepare dist directory for MSIX packaging
    $msixDist = Join-Path $PROJECT_ROOT "dist_msix"
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $msixDist
    Start-Sleep -Milliseconds 300
    New-Item -ItemType Directory -Force -Path $msixDist | Out-Null

    # Copy main exe
    $exePath = Join-Path $relDir "ems-simulate.exe"
    if (Test-Path $exePath) {
        Copy-Item -Force $exePath $msixDist
        WriteOk "ems-simulate.exe copied"
    } else {
        WriteErr "ems-simulate.exe not found at $exePath"
    }

    # Copy sidecar binary
    # Tauri sidecar API 在 MSIX 下的路径解析: resource_dir/binaries/<name>-<target-triple>.exe
    # MSIX 安装后 resource_dir == exe 所在目录, 所以 sidecar 应放在 exe 同级的 binaries/ 子目录
    $sidecarDestDir = Join-Path $msixDist "binaries"
    New-Item -ItemType Directory -Force -Path $sidecarDestDir | Out-Null
    if (Test-Path $BE_SIDECAR_EXE) {
        Copy-Item -Force $BE_SIDECAR_EXE (Join-Path $sidecarDestDir "ems_simulate_backend-$SIDECAR_TARGET.exe")
        WriteOk "Sidecar binary copied to MSIX dist/binaries/"
    } else {
        WriteErr "Sidecar binary not found at $BE_SIDECAR_EXE"
    }

    # Copy Assets
    if (Test-Path $assetsDir) {
        $assetsDest = Join-Path $msixDist "Assets"
        Copy-Item -Recurse -Force $assetsDir $assetsDest
        WriteOk "Assets copied to MSIX dist"
    }

    # Copy Package.appxmanifest
    $manifest = Join-Path $PROJECT_ROOT "Package.appxmanifest"
    if (Test-Path $manifest) {
        Copy-Item -Force $manifest $msixDist
        WriteOk "Package.appxmanifest copied"
    }

    # Generate dev certificate if not exists
    $certPath = Join-Path $PROJECT_ROOT "devcert.pfx"
    if (-not (Test-Path $certPath)) {
        WriteStep "Generating development certificate..."
        Set-Location $PROJECT_ROOT
        winapp cert generate --if-exists skip
        if ($LASTEXITCODE -ne 0) { WriteErr "Certificate generation failed" }
        WriteOk "Development certificate generated"
    } else {
        WriteSkip "Development certificate already exists"
    }

    # Pack MSIX
    WriteStep "Creating MSIX package..."
    Set-Location $PROJECT_ROOT
    winapp pack $msixDist --cert $certPath
    if ($LASTEXITCODE -ne 0) { WriteErr "MSIX packaging failed" }

    # Find generated MSIX
    $msixFile = Get-ChildItem -Path $PROJECT_ROOT -Filter "*.msix" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($msixFile) {
        WriteOk "MSIX package created: $($msixFile.FullName)"
    } else {
        Write-Host '[WARN] MSIX file not found in project root' -ForegroundColor Yellow
    }

    # Install instructions
    Write-Host ""
    Write-Host "To install the MSIX, first install the certificate (admin required):" -ForegroundColor Cyan
    Write-Host "  winapp cert install .\devcert.pfx" -ForegroundColor White
    Write-Host ""
    Write-Host "Then install the MSIX:" -ForegroundColor Cyan
    if ($msixFile) {
        Write-Host "  Add-AppxPackage `"$($msixFile.FullName)`"" -ForegroundColor White
    }
    Write-Host ""
    Write-Host "Note: MSIX uses self-signed dev certificate." -ForegroundColor Yellow
    Write-Host "  Install the cert to 'Trusted People' store." -ForegroundColor Yellow
}

# Summary
$exePath = Join-Path $TAURI_DIR "target\release\ems-simulate.exe"
$bundlePath = Join-Path $TAURI_DIR "target\release\bundle"

Write-Host ""
Write-Host "========================================" -ForegroundColor Magenta
Write-Host "  Tauri Build Complete!" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "exe: $exePath" -ForegroundColor Yellow
if ($Msix) {
    $bundleMsixDir = Join-Path $TAURI_DIR "target\release\bundle\msix"
    $msixFile = Get-ChildItem -Path $bundleMsixDir -Filter "*.msix" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $msixFile) {
        $msixFile = Get-ChildItem -Path $PROJECT_ROOT -Filter "*.msix" -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    if ($msixFile) {
        Write-Host "msix: $($msixFile.FullName)" -ForegroundColor Yellow
    }
} else {
    Write-Host "bundle: $bundlePath" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "run:" -ForegroundColor Cyan
Write-Host "  $exePath" -ForegroundColor White
Write-Host ""
