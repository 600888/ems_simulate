param(
    [Parameter(Mandatory = $true)]
    [string]$RuntimeDir,

    [long]$C104MaxBytes = 16MB
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $RuntimeDir -PathType Container)) {
    throw "Native runtime directory not found: $RuntimeDir"
}

$c104Extensions = @(
    Get-ChildItem -LiteralPath $RuntimeDir -Recurse -File -Filter "*_c104*.pyd"
)

if ($c104Extensions.Count -ne 1) {
    throw "Expected exactly one c104 native extension in '$RuntimeDir', found $($c104Extensions.Count)"
}

$c104Extension = $c104Extensions[0]
$originalBytes = $c104Extension.Length

if ($originalBytes -gt $C104MaxBytes) {
    $stripCommand = Get-Command strip.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $stripCommand) {
        $sizeMiB = [math]::Round($originalBytes / 1MB, 2)
        throw "c104 native extension is unexpectedly large (${sizeMiB} MiB), but strip.exe is unavailable. Rebuild c104 in Release mode or install the matching MinGW binutils."
    }

    Write-Host "[INFO] Removing debug symbols from oversized c104 extension: $($c104Extension.FullName)"
    & $stripCommand.Source --strip-debug $c104Extension.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "strip.exe failed for c104 native extension with exit code $LASTEXITCODE"
    }

    $c104Extension = Get-Item -LiteralPath $c104Extension.FullName
}

$optimizedBytes = $c104Extension.Length
if ($optimizedBytes -gt $C104MaxBytes) {
    $sizeMiB = [math]::Round($optimizedBytes / 1MB, 2)
    $limitMiB = [math]::Round($C104MaxBytes / 1MB, 2)
    throw "c104 native extension remains too large after optimization: ${sizeMiB} MiB (limit: ${limitMiB} MiB)"
}

$originalMiB = [math]::Round($originalBytes / 1MB, 2)
$optimizedMiB = [math]::Round($optimizedBytes / 1MB, 2)
$savedMiB = [math]::Round(($originalBytes - $optimizedBytes) / 1MB, 2)
Write-Host "[SUCCESS] c104 native extension size verified: ${originalMiB} MiB -> ${optimizedMiB} MiB (saved ${savedMiB} MiB)"
