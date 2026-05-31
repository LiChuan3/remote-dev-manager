# build.ps1 - Build standalone executable with PyInstaller
# Usage: .\scripts\build.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
Push-Location $ProjectRoot

try {
    # --- Locate PyInstaller ---
    $VenvPyInstaller = Join-Path $ProjectRoot ".venv" "Scripts" "pyinstaller.exe"

    if (Test-Path $VenvPyInstaller) {
        $PyInstallerCmd = $VenvPyInstaller
    } elseif (Get-Command "pyinstaller" -ErrorAction SilentlyContinue) {
        $PyInstallerCmd = "pyinstaller"
    } else {
        Write-Host "[ERROR] PyInstaller not found." -ForegroundColor Red
        Write-Host "Install it: pip install pyinstaller" -ForegroundColor Yellow
        exit 1
    }

    Write-Host "Building rdm executable ..." -ForegroundColor Cyan

    $EntryPoint = Join-Path $ProjectRoot "rdm" "__main__.py"
    if (-not (Test-Path $EntryPoint)) {
        Write-Host "[ERROR] Entry point not found: $EntryPoint" -ForegroundColor Red
        exit 1
    }

    & $PyInstallerCmd `
        --onefile `
        --name rdm `
        --collect-all textual `
        --hidden-import psutil `
        --hidden-import yaml `
        --distpath (Join-Path $ProjectRoot "dist") `
        --workpath (Join-Path $ProjectRoot "build") `
        --specpath $ProjectRoot `
        $EntryPoint

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] PyInstaller build failed." -ForegroundColor Red
        exit 1
    }

    # --- Report result ---
    $ExePath = Join-Path $ProjectRoot "dist" "rdm.exe"
    if (Test-Path $ExePath) {
        $SizeKB = [math]::Round((Get-Item $ExePath).Length / 1024)
        $SizeMB = [math]::Round((Get-Item $ExePath).Length / 1MB, 1)
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Green
        Write-Host " Build complete!" -ForegroundColor Green
        Write-Host "========================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "Output: $ExePath" -ForegroundColor Yellow
        Write-Host "Size:   $SizeMB MB ($SizeKB KB)" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Test it:"
        Write-Host "  .\dist\rdm.exe --version" -ForegroundColor Yellow
    } else {
        Write-Host "[ERROR] Expected output not found: $ExePath" -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}
