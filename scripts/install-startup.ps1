# install-startup.ps1 - Create/remove Windows Startup shortcut for rdm
# Usage:
#   .\scripts\install-startup.ps1              # Install shortcut
#   .\scripts\install-startup.ps1 -Uninstall   # Remove shortcut

param(
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$StartupFolder = [System.IO.Path]::Combine(
    [System.Environment]::GetFolderPath("Startup"),
    ""
)
$ShortcutName = "rdm-autostart.lnk"
$ShortcutPath = Join-Path $StartupFolder $ShortcutName

if ($Uninstall) {
    if (Test-Path $ShortcutPath) {
        Remove-Item $ShortcutPath -Force
        Write-Host "[OK] Startup shortcut removed: $ShortcutPath" -ForegroundColor Green
    } else {
        Write-Host "[INFO] No startup shortcut found at: $ShortcutPath" -ForegroundColor Yellow
    }
    exit 0
}

# --- Find rdm.exe ---
# Priority: dist/rdm.exe relative to project root, then PATH
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
$DistExe = Join-Path $ProjectRoot "dist" "rdm.exe"

$RdmExePath = $null
if (Test-Path $DistExe) {
    $RdmExePath = (Resolve-Path $DistExe).Path
} else {
    $InPath = Get-Command "rdm" -ErrorAction SilentlyContinue
    if ($InPath) {
        $RdmExePath = $InPath.Source
    }
}

if (-not $RdmExePath) {
    Write-Host "[ERROR] rdm.exe not found." -ForegroundColor Red
    Write-Host "Build it first: .\scripts\build.ps1" -ForegroundColor Yellow
    exit 1
}

# --- Create shortcut ---
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $RdmExePath
$Shortcut.Arguments = "up"
$Shortcut.WorkingDirectory = Split-Path $RdmExePath -Parent
$Shortcut.Description = "remote-dev-manager: start all services on login"
$Shortcut.WindowStyle = 7  # Minimized
$Shortcut.Save()

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " Startup shortcut installed!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Location:  $ShortcutPath" -ForegroundColor Yellow
Write-Host "Target:    $RdmExePath up" -ForegroundColor Yellow
Write-Host ""
Write-Host "rdm will start all services on Windows login."
Write-Host "To remove: .\scripts\install-startup.ps1 -Uninstall" -ForegroundColor Cyan
