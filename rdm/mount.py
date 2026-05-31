"""SSHFS mount service for remote-dev-manager."""

from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

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
