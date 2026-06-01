"""SSHFS mount service for remote-dev-manager."""

from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psutil

from rdm.models import Service, ServiceType, Status
from rdm.process import (
    clear_pid,
    is_alive,
    spawn_hidden,
    terminate_tree,
    write_pid,
)

if TYPE_CHECKING:
    from rdm.config import HostConfig, MountConfig

_IS_WINDOWS = platform.system() == "Windows"

# Well-known install location for WinFsp/SSHFS-Win
_SSHFS_WIN_DIR = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "SSHFS-Win" / "bin"
_WINFSP_ROOTS = [
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "WinFsp",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "WinFsp",
]


def _run_version(binary: str) -> str:
    """Return a short sshfs version string when the binary can report one."""
    for flag in ("--version", "-V"):
        try:
            proc = subprocess.run(
                [binary, flag],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        text = (proc.stdout or proc.stderr).strip()
        if text:
            return text.splitlines()[0].strip()
    return ""


def check_sshfs_installation() -> dict[str, Any]:
    """Inspect whether this machine has the pieces needed for SSHFS mounts."""
    path_sshfs = shutil.which("sshfs")
    bundled_sshfs = _SSHFS_WIN_DIR / "sshfs.exe"
    sshfs_path = str(bundled_sshfs) if bundled_sshfs.is_file() else (path_sshfs or "")
    sshfs_win_found = bundled_sshfs.is_file() or (
        bool(path_sshfs) and "sshfs-win" in path_sshfs.lower()
    )
    winfsp_candidates: list[Path] = []
    for root in _WINFSP_ROOTS:
        winfsp_candidates.extend(
            [
                root / "bin" / "winfsp-x64.dll",
                root / "bin" / "winfsp-x86.dll",
                root / "bin" / "launchctl-x64.exe",
                root / "bin" / "fsptool.exe",
            ]
        )
        sxs_dir = root / "SxS"
        if sxs_dir.is_dir():
            for child in sxs_dir.iterdir():
                winfsp_candidates.extend(
                    [
                        child / "bin" / "winfsp-x64.dll",
                        child / "bin" / "winfsp-x86.dll",
                        child / "bin" / "launchctl-x64.exe",
                        child / "bin" / "fsptool-x64.exe",
                    ]
                )
    winfsp_found = any(p.is_file() for p in winfsp_candidates)
    winfsp_path = next(
        (str(p.parent) for p in winfsp_candidates if p.is_file()),
        "",
    )

    found = bool(sshfs_path) and (not _IS_WINDOWS or winfsp_found)
    missing: list[str] = []
    if not sshfs_path:
        missing.append("sshfs")
    if _IS_WINDOWS and not sshfs_win_found and not path_sshfs:
        missing.append("SSHFS-Win")
    if _IS_WINDOWS and not winfsp_found:
        missing.append("WinFsp")

    return {
        "platform": platform.system(),
        "ready": found,
        "sshfs_found": bool(sshfs_path),
        "sshfs_path": sshfs_path,
        "sshfs_version": _run_version(sshfs_path) if sshfs_path else "",
        "sshfs_win_found": sshfs_win_found,
        "sshfs_win_path": str(bundled_sshfs) if bundled_sshfs.is_file() else (path_sshfs or ""),
        "winfsp_found": winfsp_found,
        "winfsp_path": winfsp_path,
        "missing": missing,
    }


def launch_sshfs_dependency_installer() -> dict[str, Any]:
    """Launch an elevated Windows installer flow for WinFsp + SSHFS-Win."""
    if not _IS_WINDOWS:
        return {
            "ok": False,
            "started": False,
            "message": "一键安装目前只支持 Windows。请使用系统包管理器安装 sshfs。",
            "script_path": "",
        }
    if not shutil.which("winget"):
        return {
            "ok": False,
            "started": False,
            "message": "未找到 winget。请先安装或更新 Windows App Installer。",
            "script_path": "",
        }

    script_path = Path(tempfile.gettempdir()) / "rdm-install-sshfs-win.ps1"
    script = r'''
$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "远程开发管理器 - 安装目录挂载依赖"
Write-Host "远程开发管理器将安装目录挂载依赖：" -ForegroundColor Cyan
Write-Host "  1. WinFsp.WinFsp"
Write-Host "  2. SSHFS-Win.SSHFS-Win"
Write-Host ""
Write-Host "安装过程由 winget 执行，可能需要几分钟。" -ForegroundColor Yellow
Write-Host ""

winget install --id WinFsp.WinFsp --exact --source winget --accept-source-agreements --accept-package-agreements
winget install --id SSHFS-Win.SSHFS-Win --exact --source winget --accept-source-agreements --accept-package-agreements

Write-Host ""
Write-Host "安装命令已执行完成。请重新打开远程开发管理器，或回到应用点击“重新检查”。" -ForegroundColor Green
Read-Host "按 Enter 关闭窗口"
'''
    script_path.write_text(script.strip() + "\n", encoding="utf-8")

    escaped_script = str(script_path).replace('"', '`"')
    command = (
        'Start-Process -FilePath "powershell.exe" '
        f'-ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"{escaped_script}`"" '
        "-Verb RunAs"
    )
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "started": False,
            "message": str(exc),
            "script_path": str(script_path),
        }

    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip() or f"安装器启动失败：{proc.returncode}"
        return {
            "ok": False,
            "started": False,
            "message": message,
            "script_path": str(script_path),
        }

    return {
        "ok": True,
        "started": True,
        "message": "已打开管理员安装窗口，请按提示完成 WinFsp 和 SSHFS-Win 安装。",
        "script_path": str(script_path),
    }


def _find_sshfs_binary() -> str:
    """Locate the sshfs binary, raising FileNotFoundError if missing."""
    if _IS_WINDOWS:
        win_path = _SSHFS_WIN_DIR / "sshfs.exe"
        if win_path.is_file():
            return str(win_path)
        # Fall through to PATH lookup
    found = shutil.which("sshfs")
    if found:
        return found
    raise FileNotFoundError(
        "sshfs binary not found. "
        + ("Install SSHFS-Win (https://github.com/winfsp/sshfs-win)." if _IS_WINDOWS else "Install sshfs via your package manager.")
    )


def _find_sshfs_procs_for_mount(mount_point: str) -> list[psutil.Process]:
    """Return live sshfs processes whose command line references *mount_point*."""
    mount_abs = os.path.abspath(mount_point)
    result: list[psutil.Process] = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if "sshfs" not in name:
                continue
            cmdline = proc.info.get("cmdline") or []
            # Check if any argument matches the mount point (normalised)
            for arg in cmdline:
                if os.path.abspath(arg) == mount_abs:
                    result.append(proc)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return result


def _graceful_kill_windows(proc: psutil.Process) -> bool:
    """Try cygwin kill -SIGTERM (from Git usr/bin/kill.exe), return True on success."""
    git_exe = shutil.which("git")
    if not git_exe:
        return False
    # Derive Git install root  e.g.  C:/Program Files/Git/cmd/git.exe -> C:/Program Files/Git
    git_root = Path(git_exe).resolve().parent.parent
    cygwin_kill = git_root / "usr" / "bin" / "kill.exe"
    if not cygwin_kill.is_file():
        return False
    try:
        subprocess.run(
            [str(cygwin_kill), "-SIGTERM", str(proc.pid)],
            timeout=5,
            capture_output=True,
        )
        proc.wait(timeout=5)
        return True
    except (subprocess.TimeoutExpired, psutil.TimeoutExpired, psutil.NoSuchProcess, OSError):
        return False


def _kill_sshfs_proc(proc: psutil.Process) -> None:
    """Kill a single sshfs process gracefully, with platform-specific fallback."""
    try:
        if _IS_WINDOWS:
            if _graceful_kill_windows(proc):
                return
        else:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=5)
                return
            except psutil.TimeoutExpired:
                pass
        # Hard kill fallback
        terminate_tree(proc.pid, timeout=5.0)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


def _cleanup_mount_dir(mount_point: Path) -> None:
    """Remove and recreate the mount point directory."""
    if mount_point.exists():
        try:
            if mount_point.is_mount() or mount_point.is_symlink():
                # On Linux a stale FUSE mount may need fusermount -u first
                if not _IS_WINDOWS:
                    subprocess.run(
                        ["fusermount", "-uz", str(mount_point)],
                        capture_output=True,
                        timeout=10,
                    )
            mount_point.rmdir()
        except OSError:
            pass
    mount_point.mkdir(parents=True, exist_ok=True)


class MountService(Service):
    """Manages an SSHFS mount."""

    def __init__(
        self,
        config: MountConfig,
        host: HostConfig,
        logs_dir: Path,
        workspace: Path,
        clash_port: int = 7897,
    ) -> None:
        super().__init__(name=config.name, kind=ServiceType.MOUNT, proxy="direct", logs_dir=logs_dir)
        self.config = config
        self.host = host
        self.workspace = workspace
        self.clash_port = clash_port

        # Resolve mount point: explicit > workspace/<name>
        if config.mount_point:
            self.mount_point = Path(config.mount_point).expanduser().resolve()
        else:
            self.mount_point = (workspace / "mounts" / config.name).resolve()

    # ------------------------------------------------------------------
    # Process adoption / discovery
    # ------------------------------------------------------------------

    def _find_my_procs(self) -> list[psutil.Process]:
        return _find_sshfs_procs_for_mount(str(self.mount_point))

    def _try_adopt(self) -> bool:
        """If an sshfs process already serves this mount point, adopt it.

        Returns True if adoption succeeded.
        """
        procs = self._find_my_procs()
        if not procs:
            return False
        proc = procs[0]
        try:
            if proc.is_running():
                self.pid = proc.pid
                self.status = Status.RUNNING
                write_pid(self.pid_file, self.pid)
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return False

    # ------------------------------------------------------------------
    # Command construction
    # ------------------------------------------------------------------

    def _build_command(self) -> list[str]:
        sshfs_bin = _find_sshfs_binary()

        remote_spec = f"{self.host.user}@{self.host.host}:{self.config.remote_path}"
        mount_dir = str(self.mount_point)

        cmd: list[str] = [
            sshfs_bin,
            remote_spec,
            mount_dir,
            "-o", f"port={self.host.port}",
            "-o", "reconnect",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=15",
            "-o", "BatchMode=yes",
        ]

        # Identity file
        if self.host.identity:
            identity_path = str(Path(self.host.identity).expanduser())
            cmd += ["-o", f"IdentityFile={identity_path}"]

        # Proxy
        proxy = self.proxy or "direct"
        if proxy == "clash":
            if _IS_WINDOWS:
                proxy_cmd = f"connect -S 127.0.0.1:{self.clash_port} %h %p"
            else:
                proxy_cmd = f"nc -x 127.0.0.1:{self.clash_port} %h %p"
            cmd += ["-o", f"ProxyCommand={proxy_cmd}"]
        elif proxy.startswith("jump:"):
            jump_alias = proxy[len("jump:"):]
            cmd += ["-o", f"ProxyJump={jump_alias}"]

        # Extra user-specified options
        for opt in (self.config.options or []):
            cmd += ["-o", opt]

        return cmd

    def _build_env(self) -> dict[str, str] | None:
        """On Windows, prepend SSHFS-Win bin dir to PATH."""
        if not _IS_WINDOWS:
            return None
        if not _SSHFS_WIN_DIR.is_dir():
            return None
        env = os.environ.copy()
        env["PATH"] = str(_SSHFS_WIN_DIR) + os.pathsep + env.get("PATH", "")
        return env

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the SSHFS mount."""
        if self.status == Status.RUNNING:
            return

        self.status = Status.STARTING
        self.last_error = ""

        # 1. Try to adopt an existing sshfs process
        if self._try_adopt():
            return

        # 2. Kill any stale sshfs processes for this mount point
        for proc in self._find_my_procs():
            _kill_sshfs_proc(proc)

        # 3. Prepare mount point directory
        _cleanup_mount_dir(self.mount_point)

        # 4. Build command
        cmd = self._build_command()
        env_overlay = self._build_env()

        # 5. Spawn
        #    On Windows sshfs daemonizes itself, so detached=False.
        #    On Linux we let spawn_hidden detach.
        detached = not _IS_WINDOWS

        try:
            pid = spawn_hidden(
                cmd=cmd,
                log_path=self.log_file,
                env_overlay=env_overlay,
                detached=detached,
            )
            self.pid = pid
            self.started_at = time.time()
            write_pid(self.pid_file, pid)
            self.status = Status.RUNNING
        except Exception as exc:  # noqa: BLE001
            self.status = Status.FAILED
            self.last_error = str(exc)
            raise

    def stop(self) -> None:
        """Stop the SSHFS mount and clean up."""
        self.user_stopped = True

        # Kill all sshfs processes for this mount point
        for proc in self._find_my_procs():
            _kill_sshfs_proc(proc)

        # Also kill by stored PID if still alive
        if self.pid and is_alive(self.pid):
            terminate_tree(self.pid, timeout=5.0)

        self.pid = None
        self.status = Status.STOPPED
        clear_pid(self.pid_file)

        # Unmount / clean up directory
        _cleanup_mount_dir(self.mount_point)

    def poll(self) -> None:
        """Check if the sshfs process is still running; adopt if found."""
        # First check stored PID
        if self.pid and is_alive(self.pid):
            self.status = Status.RUNNING
            return

        # Try to find and adopt an sshfs process for this mount point
        if self._try_adopt():
            return

        # No process found — mark stopped (unless user explicitly stopped)
        if self.status == Status.RUNNING:
            self.status = Status.FAILED
            self.last_error = "sshfs process exited unexpectedly"
        self.pid = None

    def reattach(self) -> None:
        """Re-attach to an existing sshfs process after daemon restart."""
        self._try_adopt()
