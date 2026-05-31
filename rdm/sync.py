"""File sync utilities using rsync (preferred) or scp (fallback).

These are standalone functions -- *not* Service subclasses -- because syncs
are one-shot operations rather than long-running daemons.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any

from rdm.config import HostConfig, SyncConfig

log = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def is_rsync_available() -> bool:
    """Return True if ``rsync`` is found on PATH."""
    return shutil.which("rsync") is not None


def _ssh_cmd_fragment(host: HostConfig) -> str:
    """Build the ``-e 'ssh ...'`` argument value for rsync / the scp flags."""
    parts = ["ssh"]
    if host.port and host.port != 22:
        parts += ["-p", str(host.port)]
    if host.identity:
        identity = str(Path(host.identity).expanduser())
        parts += ["-i", identity]
    parts += ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
    return " ".join(parts)


def _ssh_scp_flags(host: HostConfig) -> List[str]:
    """Return scp-specific flags for port / identity."""
    flags: List[str] = []
    if host.port and host.port != 22:
        flags += ["-P", str(host.port)]
    if host.identity:
        identity = str(Path(host.identity).expanduser())
        flags += ["-i", identity]
    flags += ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]
    return flags


def _remote_spec(host: HostConfig, path: str) -> str:
    """Return ``user@host:path``."""
    return f"{host.user}@{host.host}:{path}"


def _ensure_trailing_slash(p: str) -> str:
    """Ensure a path ends with ``/`` (rsync semantics)."""
    return p if p.endswith("/") else p + "/"


def _parse_rsync_output(output: str) -> Dict[str, Any]:
    """Extract transfer stats from rsync stdout."""
    files_transferred = 0
    total_bytes = 0
    errors: List[str] = []

    for line in output.splitlines():
        # rsync 3.x summary lines
        m = re.search(r"Number of regular files transferred:\s*(\d[\d,]*)", line)
        if m:
            files_transferred = int(m.group(1).replace(",", ""))
        m = re.search(r"Total transferred file size:\s*([\d,]+)", line)
        if m:
            total_bytes = int(m.group(1).replace(",", ""))
        # older rsync / simpler output
        m = re.search(r"sent\s+([\d,]+)\s+bytes", line)
        if m and total_bytes == 0:
            total_bytes = int(m.group(1).replace(",", ""))
        if "error" in line.lower() or "rsync:" in line.lower():
            errors.append(line.strip())

    return {
        "files_transferred": files_transferred,
        "bytes": total_bytes,
        "errors": errors,
    }


def _run(cmd: List[str], dry_run: bool = False) -> Dict[str, Any]:
    """Execute *cmd*, stream output to stdout, and return a summary dict."""
    log.info("running: %s", " ".join(cmd))
    if dry_run:
        print(f"[dry-run] {' '.join(cmd)}")

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        full_output_lines: List[str] = []
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            full_output_lines.append(line)
        proc.wait()
        full_output = "".join(full_output_lines)

        if proc.returncode != 0:
            return {
                "files_transferred": 0,
                "bytes": 0,
                "errors": [f"exit code {proc.returncode}: {full_output.strip()[-500:]}"],
            }

        return _parse_rsync_output(full_output)

    except FileNotFoundError as exc:
        msg = f"command not found: {cmd[0]} ({exc})"
        log.error(msg)
        return {"files_transferred": 0, "bytes": 0, "errors": [msg]}
    except Exception as exc:
        msg = f"unexpected error: {exc}"
        log.error(msg)
        return {"files_transferred": 0, "bytes": 0, "errors": [msg]}


# ------------------------------------------------------------------
# rsync builders
# ------------------------------------------------------------------

def _rsync_push_cmd(
    config: SyncConfig,
    host: HostConfig,
    dry_run: bool = False,
) -> List[str]:
    rsync = shutil.which("rsync") or "rsync"
    cmd = [rsync, "-avz", "--stats"]
    if dry_run:
        cmd.append("-n")
    for pat in config.exclude:
        cmd += ["--exclude", pat]
    cmd += ["-e", _ssh_cmd_fragment(host)]
    local = _ensure_trailing_slash(str(Path(config.local_path).expanduser().resolve()))
    cmd.append(local)
    cmd.append(_remote_spec(host, _ensure_trailing_slash(config.remote_path)))
    return cmd


def _rsync_pull_cmd(
    config: SyncConfig,
    host: HostConfig,
    dry_run: bool = False,
) -> List[str]:
    rsync = shutil.which("rsync") or "rsync"
    cmd = [rsync, "-avz", "--stats"]
    if dry_run:
        cmd.append("-n")
    for pat in config.exclude:
        cmd += ["--exclude", pat]
    cmd += ["-e", _ssh_cmd_fragment(host)]
    cmd.append(_remote_spec(host, _ensure_trailing_slash(config.remote_path)))
    local = _ensure_trailing_slash(str(Path(config.local_path).expanduser().resolve()))
    cmd.append(local)
    return cmd


# ------------------------------------------------------------------
# scp builders (fallback -- no exclude support)
# ------------------------------------------------------------------

def _scp_push_cmd(config: SyncConfig, host: HostConfig) -> List[str]:
    scp = shutil.which("scp") or "scp"
    cmd = [scp, "-r"] + _ssh_scp_flags(host)
    local = str(Path(config.local_path).expanduser().resolve())
    # scp -r copies the directory contents
    if os.path.isdir(local):
        # Append /* so contents (not the dir itself) are copied
        cmd.append(os.path.join(local, "*") if sys.platform == "win32" else local + "/*")
    else:
        cmd.append(local)
    cmd.append(_remote_spec(host, config.remote_path))
    return cmd


def _scp_pull_cmd(config: SyncConfig, host: HostConfig) -> List[str]:
    scp = shutil.which("scp") or "scp"
    cmd = [scp, "-r"] + _ssh_scp_flags(host)
    cmd.append(_remote_spec(host, config.remote_path + "/*"))
    local = str(Path(config.local_path).expanduser().resolve())
    cmd.append(local)
    return cmd


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def sync_push(
    config: SyncConfig,
    host: HostConfig,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Upload *local_path* to *remote_path* on *host*.

    Uses rsync when available; falls back to scp (which lacks ``--exclude``
    and ``--dry-run`` support).

    Returns a summary dict::

        {"files_transferred": int, "bytes": int, "errors": list[str]}
    """
    if config.exclude and not is_rsync_available():
        print(
            "WARNING: rsync not found -- exclude patterns will be ignored "
            "when falling back to scp.",
            file=sys.stderr,
        )

    if is_rsync_available():
        cmd = _rsync_push_cmd(config, host, dry_run=dry_run)
    else:
        if dry_run:
            cmd = _scp_push_cmd(config, host)
            print(f"[dry-run] would run: {' '.join(cmd)}")
            return {"files_transferred": 0, "bytes": 0, "errors": []}
        cmd = _scp_push_cmd(config, host)

    return _run(cmd, dry_run=dry_run)


def sync_pull(
    config: SyncConfig,
    host: HostConfig,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Download *remote_path* from *host* to *local_path*.

    Uses rsync when available; falls back to scp.

    Returns a summary dict::

        {"files_transferred": int, "bytes": int, "errors": list[str]}
    """
    # Ensure local directory exists
    local_dir = Path(config.local_path).expanduser().resolve()
    local_dir.mkdir(parents=True, exist_ok=True)

    if config.exclude and not is_rsync_available():
        print(
            "WARNING: rsync not found -- exclude patterns will be ignored "
            "when falling back to scp.",
            file=sys.stderr,
        )

    if is_rsync_available():
        cmd = _rsync_pull_cmd(config, host, dry_run=dry_run)
    else:
        if dry_run:
            cmd = _scp_pull_cmd(config, host)
            print(f"[dry-run] would run: {' '.join(cmd)}")
            return {"files_transferred": 0, "bytes": 0, "errors": []}
        cmd = _scp_pull_cmd(config, host)

    return _run(cmd, dry_run=dry_run)
