"""Cross-platform process spawning and management for rdm."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import psutil


# ---------------------------------------------------------------------------
# Platform constants
# ---------------------------------------------------------------------------

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    _CREATION_FLAGS = CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


# ---------------------------------------------------------------------------
# Process spawning
# ---------------------------------------------------------------------------

def spawn_hidden(
    cmd: list[str],
    log_path: Path,
    cwd: str | Path | None = None,
    env_overlay: dict[str, str] | None = None,
    detached: bool = True,
) -> int:
    """Spawn a process in the background with its output redirected to a log file.

    Args:
        cmd: Command and arguments to execute.
        log_path: Path to the log file (opened in append mode).
        cwd: Working directory for the subprocess.
        env_overlay: Extra environment variables merged on top of ``os.environ``.
        detached: If True (default), fully detach the process from the parent.

    Returns:
        The PID of the spawned process.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "a", encoding="utf-8", errors="replace")

    env: dict[str, str] | None = None
    if env_overlay:
        env = {**os.environ, **env_overlay}

    kwargs: dict[str, Any] = {
        "stdout": log_fh,
        "stderr": subprocess.STDOUT,
        "stdin": subprocess.DEVNULL,
        "env": env,
    }

    if cwd is not None:
        kwargs["cwd"] = str(cwd)

    if _IS_WINDOWS:
        if detached:
            kwargs["creationflags"] = _CREATION_FLAGS
        si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        si.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = si
    else:
        if detached:
            kwargs["preexec_fn"] = os.setsid
        # Close file descriptors (Python 3.2+ default is True, but be explicit)
        kwargs["close_fds"] = True

    proc = subprocess.Popen(cmd, **kwargs)

    # We don't close log_fh here because the child process owns it now via
    # stdout/stderr redirection.  On Windows, the handle is inherited; on
    # POSIX, it stays open in the child via the fd.  The parent can safely
    # close its copy once Popen has forked/spawned.
    try:
        log_fh.close()
    except OSError:
        pass

    return proc.pid


# ---------------------------------------------------------------------------
# PID file helpers
# ---------------------------------------------------------------------------

def write_pid(path: Path, pid: int) -> None:
    """Write a PID to a file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(str(pid), encoding="utf-8")
    tmp.replace(path)


def read_pid(path: Path) -> int | None:
    """Read a PID from a file.  Returns None if the file is missing or corrupt."""
    try:
        text = path.read_text(encoding="utf-8").strip()
        return int(text)
    except (OSError, ValueError):
        return None


def clear_pid(path: Path) -> None:
    """Remove a PID file if it exists."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Process inspection
# ---------------------------------------------------------------------------

def is_alive(pid: int) -> bool:
    """Check whether a process with the given PID is still running.

    Uses psutil so it works reliably across platforms (handles zombie
    processes, PID reuse, etc.).
    """
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def terminate_tree(pid: int, timeout: float = 5.0) -> None:
    """Terminate a process and all its children.

    Sends SIGTERM (or TerminateProcess on Windows) to the process tree,
    waits up to *timeout* seconds, then force-kills any survivors.

    Args:
        pid: Root process PID.
        timeout: Seconds to wait for graceful shutdown before SIGKILL.
    """
    try:
        parent = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return

    # Collect the full tree (children first, parent last)
    children = []
    try:
        children = parent.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    procs = children + [parent]

    # Graceful termination
    for proc in procs:
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Wait for processes to exit
    _, alive = psutil.wait_procs(procs, timeout=timeout)

    # Force-kill stragglers
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def process_start_time(pid: int) -> float | None:
    """Return the create_time of a process, or None if unavailable.

    The returned value is a Unix timestamp (seconds since epoch).
    """
    try:
        proc = psutil.Process(pid)
        return proc.create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
