<#
.SYNOPSIS
    Full desktop build for Remote Dev Manager (rdm) on Windows.

.DESCRIPTION
    1. Builds the Python sidecar into a one-file executable with PyInstaller.
    2. Renames it to the Rust target-triple form Tauri's externalBin expects.
    3. Builds the Tauri desktop app (frontend + installer/bundle).

.PARAMETER Python
    Python interpreter to use (default: "python"). PyInstaller and the rdm
    package (with the [api] extra) must be installed in this environment.
#>
[CmdletBinding()]
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

# --- Resolve repo root (parent of this scripts/ directory) -----------------
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot
Write-Host "==> Repo root: $RepoRoot" -ForegroundColor Cyan

$BinariesDir = Join-Path $RepoRoot "desktop/src-tauri/binaries"
$Spec        = Join-Path $RepoRoot "desktop/sidecar/rdm-sidecar.spec"

# --- 1. Build the sidecar with PyInstaller ---------------------------------
Write-Host "==> Building sidecar with PyInstaller..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $BinariesDir | Out-Null
& $Python -m PyInstaller $Spec `
    --distpath $BinariesDir `
    --workpath (Join-Path $RepoRoot "build/pyinstaller") `
    --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE)" }

$SidecarExe = Join-Path $BinariesDir "rdm-sidecar.exe"
if (-not (Test-Path $SidecarExe)) {
    throw "Expected sidecar not found: $SidecarExe"
}

# --- 2. Compute Rust target triple and rename to Tauri convention ----------
Write-Host "==> Resolving Rust target triple..." -ForegroundColor Cyan
$triple = (rustc -Vv | Select-String '^host:').ToString().Split(' ')[1]
if ([string]::IsNullOrWhiteSpace($triple)) { throw "Could not determine Rust target triple" }
Write-Host "    target triple: $triple"

$TargetExe = Join-Path $BinariesDir "rdm-sidecar-$triple.exe"
Copy-Item -Force $SidecarExe $TargetExe
Write-Host "==> Sidecar ready: $TargetExe" -ForegroundColor Green

# --- 3. Build the Tauri desktop app ----------------------------------------
Write-Host "==> Building Tauri desktop app..." -ForegroundColor Cyan
Set-Location (Join-Path $RepoRoot "desktop")
npm install
if ($LASTEXITCODE -ne 0) { throw "npm install failed (exit $LASTEXITCODE)" }
# The bundle config overlay adds the sidecar as an externalBin (kept out of the
# default tauri.conf.json so `tauri dev` / `cargo check` work with no artifacts).
npm run tauri build -- --config src-tauri/tauri.bundle.conf.json
if ($LASTEXITCODE -ne 0) { throw "tauri build failed (exit $LASTEXITCODE)" }

# --- Done ------------------------------------------------------------------
$BundleDir = Join-Path $RepoRoot "desktop/src-tauri/target/release/bundle"
Write-Host ""
Write-Host "==> Build complete." -ForegroundColor Green
Write-Host "    Installer / bundle: $BundleDir"
