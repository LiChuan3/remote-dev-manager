# setup.ps1 - Set up development environment for remote-dev-manager
# Usage: .\scripts\setup.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
Push-Location $ProjectRoot

try {
    # --- Detect Python ---
    $PythonCmd = $null

    # Try py launcher first (standard on Windows)
    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        $ver = & py --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -ge 10) {
                $PythonCmd = "py"
                Write-Host "[OK] Found: $ver (py launcher)" -ForegroundColor Green
            }
        }
    }

    # Try python3
    if (-not $PythonCmd) {
        if (Get-Command "python3" -ErrorAction SilentlyContinue) {
            $ver = & python3 --version 2>&1
            if ($ver -match "Python 3\.(\d+)") {
                $minor = [int]$Matches[1]
                if ($minor -ge 10) {
                    $PythonCmd = "python3"
                    Write-Host "[OK] Found: $ver (python3)" -ForegroundColor Green
                }
            }
        }
    }

    # Try python
    if (-not $PythonCmd) {
        if (Get-Command "python" -ErrorAction SilentlyContinue) {
            $ver = & python --version 2>&1
            if ($ver -match "Python 3\.(\d+)") {
                $minor = [int]$Matches[1]
                if ($minor -ge 10) {
                    $PythonCmd = "python"
                    Write-Host "[OK] Found: $ver (python)" -ForegroundColor Green
                }
            }
        }
    }

    if (-not $PythonCmd) {
        Write-Host "[ERROR] Python 3.10+ is required but not found." -ForegroundColor Red
        Write-Host "Install from https://www.python.org/downloads/" -ForegroundColor Yellow
        exit 1
    }

    # --- Create venv ---
    $VenvDir = Join-Path $ProjectRoot ".venv"
    if (-not (Test-Path $VenvDir)) {
        Write-Host "Creating virtual environment in .venv ..." -ForegroundColor Cyan
        & $PythonCmd -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Failed to create virtual environment." -ForegroundColor Red
            exit 1
        }
        Write-Host "[OK] Virtual environment created." -ForegroundColor Green
    } else {
        Write-Host "[OK] Virtual environment already exists." -ForegroundColor Green
    }

    # --- Activate and install ---
    $PipExe = Join-Path $VenvDir "Scripts" "pip.exe"
    if (-not (Test-Path $PipExe)) {
        Write-Host "[ERROR] pip not found in venv. Recreate the venv." -ForegroundColor Red
        exit 1
    }

    Write-Host "Installing package in editable mode ..." -ForegroundColor Cyan
    & $PipExe install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] pip install failed." -ForegroundColor Red
        exit 1
    }

    # --- Done ---
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host " Setup complete!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Activate the venv:"
    Write-Host "  .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Run rdm:"
    Write-Host "  rdm --help" -ForegroundColor Yellow
    Write-Host "  rdm tui" -ForegroundColor Yellow
} finally {
    Pop-Location
}
