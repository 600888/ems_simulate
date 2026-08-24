# Tauri Windows packaging script (Sidecar mode)
param([switch]$SkipBuild, [switch]$SkipBackend, [switch]$Msix, [switch]$Help)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_ROOT = Split-Path -Parent $SCRIPT_DIR
$TAURI_DIR = Join-Path $PROJECT_ROOT "src-tauri"
$BUILD_DIR = Join-Path $PROJECT_ROOT "build"
$BINARIES_DIR = Join-Path $TAURI_DIR "binaries"
$PYTHON_EXE = Join-Path $PROJECT_ROOT ".venv\Scripts\python.exe"

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
        $refItem = Get-Item $ref
        $refTime = $refItem.LastWriteTime
        if ($refItem.PSIsContainer) {
            $latestChild = Get-ChildItem -Path $refItem.FullName -Recurse -File -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending |
                Select-Object -First 1
            if ($latestChild -and $latestChild.LastWriteTime -gt $refTime) {
                $refTime = $latestChild.LastWriteTime
            }
        }
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

if (-not (Test-Path -PathType Leaf $PYTHON_EXE)) {
    WriteErr "Project Python environment not found at $PYTHON_EXE. Run 'uv sync --extra build' first."
}

& $PYTHON_EXE -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    WriteErr 'PyInstaller is not installed in .venv. Run: .\.venv\Scripts\python.exe -m pip install -e ".[build]"'
}

# Sync version to tauri.conf.json and package.json
WriteStep "Syncing version to config files..."
& $PYTHON_EXE "$SCRIPT_DIR\sync_version.py"
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

# Generate icons (skip if all icons already exist and are newer than source/script)
$iconSource = Join-Path $PROJECT_ROOT "resources\m.ico"
$tauriIconScript = Join-Path $SCRIPT_DIR "generate_tauri_icons.py"
$tauriIcons = @(
    (Join-Path $TAURI_DIR "icons\32x32.png"),
    (Join-Path $TAURI_DIR "icons\128x128.png"),
    (Join-Path $TAURI_DIR "icons\128x128@2x.png"),
    (Join-Path $TAURI_DIR "icons\icon.ico"),
    (Join-Path $TAURI_DIR "icons\icon.png")
)
$iconsUpToDate = $true
foreach ($ic in $tauriIcons) {
    if (-not (IsUpToDate $ic @($iconSource, $tauriIconScript))) { $iconsUpToDate = $false; break }
}

if ($iconsUpToDate) {
    WriteSkip "Tauri icons are up-to-date"
} else {
    WriteStep "Generating Tauri icons..."
    & $PYTHON_EXE $tauriIconScript
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

# Build Python backend as an onedir sidecar. PyInstaller --onefile extracts the
# whole Python runtime on every launch (about 3 seconds on a typical machine).
# Keeping the runtime beside the executable lets Windows load it directly.
$SIDECAR_TARGET = GetRustTargetTriple
$BE_SIDECAR_EXE = Join-Path $BINARIES_DIR "ems_simulate_backend-$SIDECAR_TARGET.exe"
$BE_RUNTIME_DIR = Join-Path $BINARIES_DIR "ems_simulate_backend_runtime"

if (-not $SkipBackend) {
    # Check if sidecar binary is up-to-date
    $beSources = @(
        (Join-Path $PROJECT_ROOT "start_back_end.py"),
        (Join-Path $PROJECT_ROOT "src"),
        (Join-Path $PROJECT_ROOT "config.ini"),
        (Join-Path $PROJECT_ROOT "data\point_csv"),
        (Join-Path $PROJECT_ROOT "pyproject.toml"),
        (Join-Path $PROJECT_ROOT "uv.lock"),
        (Join-Path $PROJECT_ROOT "ems_simulate_backend.spec"),
        (Join-Path $SCRIPT_DIR "rthook_numpy_compat.py"),
        (Join-Path $SCRIPT_DIR "build_tauri_windows.ps1")
    )
    if ((Test-Path $BE_RUNTIME_DIR) -and (IsUpToDate $BE_SIDECAR_EXE $beSources)) {
        WriteSkip "Python backend (sidecar) is up-to-date"
    } else {
        WriteStep "Building Python backend (PyInstaller onedir fast-start sidecar)..."

        # Clear old binaries directory
        Remove-Item -Recurse -Force $BINARIES_DIR -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 300
        New-Item -ItemType Directory -Force -Path $BINARIES_DIR | Out-Null
        New-Item -ItemType Directory -Force -Path $BUILD_DIR | Out-Null

        $pyDist = Join-Path $BUILD_DIR "dist"
        $pyWork = Join-Path $BUILD_DIR "build_pyinstaller_tauri"

        $env:EMS_PYINSTALLER_MODE = "onedir"
        $env:EMS_PYINSTALLER_NAME = "ems_simulate_backend"
        $env:EMS_PYINSTALLER_CONTENTS_DIR = "ems_simulate_backend_runtime"
        $env:EMS_PYINSTALLER_DATA_SCOPE = "point_csv"
        $env:EMS_PYINSTALLER_CONSOLE = "1"
        $pyArgs = @(
            "--noconfirm", "--clean",
            "--distpath", $pyDist,
            "--workpath", $pyWork,
            (Join-Path $PROJECT_ROOT "ems_simulate_backend.spec")
        )

        & $PYTHON_EXE -m PyInstaller @pyArgs
        if ($LASTEXITCODE -ne 0) { WriteErr "PyInstaller packaging failed" }

        # Tauri externalBin requires the target-triple executable name. The
        # runtime directory is bundled as a resource beside the renamed exe.
        $pyOutDir = Join-Path $pyDist "ems_simulate_backend"
        $pyOutExe = Join-Path $pyOutDir "ems_simulate_backend.exe"
        $pyRuntimeDir = Join-Path $pyOutDir "ems_simulate_backend_runtime"
        if (Test-Path $pyOutExe) {
            $c104Extension = Get-ChildItem -Path $pyRuntimeDir -Recurse -File -Filter "*_c104*.pyd" |
                Select-Object -First 1
            if (-not $c104Extension) {
                WriteErr "PyInstaller runtime is missing the c104 native extension"
            }
            $pyiec61850Extension = Get-ChildItem -Path $pyRuntimeDir -Recurse -File -Filter "_pyiec61850*.pyd" |
                Select-Object -First 1
            $iec61850Library = Get-ChildItem -Path $pyRuntimeDir -Recurse -File -Filter "iec61850.dll" |
                Select-Object -First 1
            if (-not $pyiec61850Extension -or -not $iec61850Library) {
                WriteErr "PyInstaller runtime is missing pyiec61850 native libraries"
            }
            $packagedPointTables = Get-ChildItem -Path (Join-Path $pyRuntimeDir "data\point_csv") -File -ErrorAction SilentlyContinue
            if (-not $packagedPointTables) {
                WriteErr "PyInstaller runtime is missing the bundled point tables"
            }
            $packagedProfiles = Get-ChildItem -Path (Join-Path $pyRuntimeDir "src\modeling\profile_packages") -Recurse -File -Filter "manifest.json" -ErrorAction SilentlyContinue
            $packagedStandards = Get-ChildItem -Path (Join-Path $pyRuntimeDir "src\modeling\standard_packages") -Recurse -File -Filter "manifest.json" -ErrorAction SilentlyContinue
            if (-not $packagedProfiles -or -not $packagedStandards) {
                WriteErr "PyInstaller runtime is missing modeling package manifests"
            }
            Copy-Item -Force $pyOutExe $BE_SIDECAR_EXE
            Copy-Item -Recurse -Force $pyRuntimeDir $BE_RUNTIME_DIR
            WriteOk "Sidecar binary created: $BE_SIDECAR_EXE"
            WriteOk "Sidecar runtime created: $BE_RUNTIME_DIR"
            WriteOk "c104 native extension verified: $($c104Extension.Name)"
            WriteOk "pyiec61850 native libraries verified"
            WriteOk "Bundled point tables verified: $($packagedPointTables.Count) file(s)"
            WriteOk "Modeling package manifests verified"
        } else {
            WriteErr "PyInstaller output not found: $pyOutExe"
        }
    }
} else {
    WriteSkip "Python backend build (skipped by flag)"
}

# Build Tauri
# Keep only the target-triple sidecar and its onedir runtime.
# Do not let runtime data/log leftovers enter the installer.
WriteStep "Cleaning binaries directory, keeping only sidecar and runtime..."
Get-ChildItem -Path $BINARIES_DIR -Force | Where-Object {
    $_.Name -ne "ems_simulate_backend-$SIDECAR_TARGET.exe" -and
    $_.Name -ne "ems_simulate_backend_runtime"
} | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
WriteOk "binaries directory cleaned"
$tauriExe = Join-Path $TAURI_DIR "target\release\ems-simulate.exe"
$tauriSrc = Join-Path $TAURI_DIR "src"
$tauriFrontend = Join-Path $TAURI_DIR "loading"
$tauriCargo = Join-Path $TAURI_DIR "Cargo.toml"
$tauriConfig = Join-Path $TAURI_DIR "tauri.conf.json"

if ((Test-Path $tauriExe) -and (IsUpToDate $tauriExe @($tauriSrc, $tauriFrontend, $tauriCargo, $tauriConfig, $BE_SIDECAR_EXE, $BE_RUNTIME_DIR))) {
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
    if (-not (Test-Path $BE_RUNTIME_DIR)) {
        WriteErr "Sidecar runtime not found at $BE_RUNTIME_DIR. Run without -SkipBackend first."
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
    $msixIconSource = Join-Path $TAURI_DIR "icons\icon.png"
    $storeLogo = Join-Path $assetsDir "StoreLogo.png"
    if ((Test-Path $storeLogo) -and (IsUpToDate $storeLogo @($msixIconSource, $msixAssetScript))) {
        WriteSkip "MSIX icon assets are up-to-date"
    } else {
        WriteStep "Generating MSIX icon assets..."
        & $PYTHON_EXE $msixAssetScript --source $msixIconSource
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

    # Define this before the non-ASCII comment block. Windows PowerShell 5.1 can
    # misparse the first statement after that block when this UTF-8 file has no BOM.
    $sidecarDestDir = Join-Path $msixDist "binaries"

    # Tauri resolves an MSIX sidecar under resource_dir/binaries.
    try {
        New-Item -ItemType Directory -Force -ErrorAction Stop -Path $sidecarDestDir | Out-Null
    } catch {
        WriteErr "Failed to create MSIX sidecar directory: $($_.Exception.Message)"
    }
    if (-not (Test-Path -PathType Leaf $BE_SIDECAR_EXE)) {
        WriteErr "Sidecar binary not found at $BE_SIDECAR_EXE"
    }
    if (-not (Test-Path -PathType Container $BE_RUNTIME_DIR)) {
        WriteErr "Sidecar runtime not found at $BE_RUNTIME_DIR"
    }

    $msixSidecarExe = Join-Path $sidecarDestDir "ems_simulate_backend-$SIDECAR_TARGET.exe"
    $msixRuntimeDir = Join-Path $sidecarDestDir "ems_simulate_backend_runtime"
    try {
        Copy-Item -Force -ErrorAction Stop $BE_SIDECAR_EXE $msixSidecarExe
        Copy-Item -Recurse -Force -ErrorAction Stop $BE_RUNTIME_DIR $msixRuntimeDir
    } catch {
        WriteErr "Failed to copy sidecar files into MSIX layout: $($_.Exception.Message)"
    }

    # Never create an installable package that can only remain on the loading page.
    $runtimeFile = Get-ChildItem -Path $msixRuntimeDir -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not (Test-Path -LiteralPath $msixSidecarExe -PathType Leaf) -or -not $runtimeFile) {
        WriteErr "MSIX sidecar layout validation failed under $sidecarDestDir"
    }
    WriteOk "Sidecar binary and runtime copied to MSIX dist/binaries/"

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
    if (-not (Test-Path -LiteralPath $msixSidecarExe -PathType Leaf) -or -not (Test-Path -LiteralPath $msixRuntimeDir -PathType Container)) {
        WriteErr "Refusing to package MSIX without the backend sidecar and runtime"
    }
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
