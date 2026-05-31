"""Remote SSH automation: connection test, file fetch, and one-click AI proxy setup."""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from rdm.config import HostConfig

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SSH helpers
# ---------------------------------------------------------------------------

def _ssh_base(host: HostConfig) -> list[str]:
    """Build the base ``ssh`` command (options only, no target/command).

    Includes non-interactive batch mode, automatic host-key acceptance, and a
    bounded connect timeout.  Port and identity flags are appended only when
    they differ from the defaults.
    """
    cmd: list[str] = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
    ]
    if host.port != 22:
        cmd += ["-p", str(host.port)]
    if host.identity:
        cmd += ["-i", os.path.expanduser(host.identity)]
    return cmd


def _ssh_target(host: HostConfig) -> str:
    """Return the ``user@host`` SSH target string."""
    return f"{host.user}@{host.host}"


def _ssh_run(host: HostConfig, remote_cmd: str, timeout: int = 30) -> tuple[int, str, str]:
    """Run a single remote command over SSH.

    Args:
        host: Target host configuration.
        remote_cmd: The command line to execute on the remote shell.
        timeout: Wall-clock timeout in seconds.

    Returns:
        A ``(returncode, stdout, stderr)`` tuple.  On timeout returns
        ``(-1, "", "timed out")``; if the ``ssh`` binary is missing returns
        ``(-1, "", "ssh not found on PATH")``.
    """
    cmd = _ssh_base(host) + [_ssh_target(host), remote_cmd]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return (-1, "", "timed out")
    except FileNotFoundError:
        return (-1, "", "ssh not found on PATH")
    return (proc.returncode, proc.stdout, proc.stderr)


def _first_line(text: str) -> str:
    """Return the first non-empty stripped line of *text* (or "")."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------

def test_connection(host: HostConfig, timeout: int = 10) -> dict[str, Any]:
    """Test SSH reachability and gather basic remote identity info.

    Runs ``whoami``, ``hostname`` and ``uname -s`` on the remote and measures
    round-trip latency.

    Returns:
        ``{"ok", "latency_ms", "message", "whoami", "hostname", "os"}``.
    """
    # Each sub-command falls back to an empty line so we always get 3 lines.
    remote_cmd = "whoami || true; hostname || true; uname -s || true"

    start = time.monotonic()
    rc, out, err = _ssh_run(host, remote_cmd, timeout=timeout)
    latency_ms = round((time.monotonic() - start) * 1000.0, 1)

    if rc != 0:
        message = _first_line(err) or f"ssh exited with code {rc}"
        return {
            "ok": False,
            "latency_ms": latency_ms if rc != -1 else None,
            "message": message,
            "whoami": None,
            "hostname": None,
            "os": None,
        }

    lines = out.splitlines()
    whoami = lines[0].strip() if len(lines) > 0 and lines[0].strip() else None
    hostname = lines[1].strip() if len(lines) > 1 and lines[1].strip() else None
    os_name = lines[2].strip() if len(lines) > 2 and lines[2].strip() else None

    return {
        "ok": True,
        "latency_ms": latency_ms,
        "message": "ok",
        "whoami": whoami,
        "hostname": hostname,
        "os": os_name,
    }


# ---------------------------------------------------------------------------
# File fetch (scp)
# ---------------------------------------------------------------------------

def _scp_base(host: HostConfig) -> list[str]:
    """Build the base ``scp`` command (options only, no source/dest)."""
    cmd: list[str] = ["scp"]
    if host.port != 22:
        # scp uses uppercase -P for the port.
        cmd += ["-P", str(host.port)]
    if host.identity:
        cmd += ["-i", os.path.expanduser(host.identity)]
    cmd += [
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
    ]
    return cmd


def fetch_file(host: HostConfig, remote_path: str, local_path: str) -> dict[str, Any]:
    """Quick single-file clone from the remote host via ``scp``.

    Args:
        host: Target host configuration.
        remote_path: Path on the remote.  A trailing ``/`` triggers ``-r``.
        local_path: Local destination path (``~`` is expanded).

    Returns:
        ``{"ok", "bytes", "local_path", "error"}``.
    """
    local = Path(os.path.expanduser(local_path))
    cmd = _scp_base(host)

    recursive = remote_path.endswith("/")
    if recursive:
        cmd.append("-r")

    # Parent directory must exist for scp to write into it.
    try:
        local.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {
            "ok": False,
            "bytes": 0,
            "local_path": str(local),
            "error": f"cannot create local directory: {exc}",
        }

    source = f"{_ssh_target(host)}:{remote_path}"
    cmd += [source, str(local)]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return {"ok": False, "bytes": 0, "local_path": str(local), "error": "timed out"}
    except FileNotFoundError:
        return {
            "ok": False,
            "bytes": 0,
            "local_path": str(local),
            "error": "scp not found on PATH",
        }

    if proc.returncode != 0:
        return {
            "ok": False,
            "bytes": 0,
            "local_path": str(local),
            "error": _first_line(proc.stderr) or f"scp exited with code {proc.returncode}",
        }

    size = 0
    try:
        if local.is_file():
            size = local.stat().st_size
        elif local.is_dir():
            size = sum(p.stat().st_size for p in local.rglob("*") if p.is_file())
    except OSError:
        size = 0

    return {"ok": True, "bytes": size, "local_path": str(local), "error": None}


def fetch_files(
    host: HostConfig,
    remote_paths: list[str],
    local_dir: str,
) -> dict[str, Any]:
    """Fetch multiple remote files into *local_dir*, preserving basenames.

    Returns:
        ``{"ok", "results": [...], "errors": [...]}`` where each result is
        ``{"remote", "ok", "bytes", "error"}``.
    """
    base = Path(os.path.expanduser(local_dir))
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for remote_path in remote_paths:
        # Use the basename of the remote path as the local filename.
        basename = os.path.basename(remote_path.rstrip("/"))
        if not basename:
            basename = "download"
        dest = base / basename

        res = fetch_file(host, remote_path, str(dest))
        entry = {
            "remote": remote_path,
            "ok": res["ok"],
            "bytes": res["bytes"],
            "error": res["error"],
        }
        results.append(entry)
        if not res["ok"]:
            errors.append(f"{remote_path}: {res['error']}")

    return {
        "ok": len(errors) == 0 and len(results) > 0,
        "results": results,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Remote proxy env management
# ---------------------------------------------------------------------------

_ENV_FILE = "~/.rdm_proxy.sh"
_BASHRC_SOURCE_LINE = "[ -f ~/.rdm_proxy.sh ] && source ~/.rdm_proxy.sh"


def _proxy_env_body(remote_port: int) -> str:
    """Return the contents of the remote ``~/.rdm_proxy.sh`` script."""
    return (
        "# Added by remote-dev-manager — route AI tool traffic through "
        "local Clash via SSH reverse tunnel\n"
        f"export ALL_PROXY=socks5://127.0.0.1:{remote_port}\n"
        f"export HTTPS_PROXY=socks5://127.0.0.1:{remote_port}\n"
        f"export HTTP_PROXY=socks5://127.0.0.1:{remote_port}\n"
        "export NO_PROXY=localhost,127.0.0.1,::1\n"
    )


def write_remote_proxy_env(
    host: HostConfig,
    remote_port: int = 7897,
    persistent: bool = False,
) -> dict[str, Any]:
    """Write ``~/.rdm_proxy.sh`` on the remote so AI tools use the local proxy.

    The script exports SOCKS5 proxy variables pointing at the reverse-tunnel
    port.  When *persistent* is True it also ensures ``~/.bashrc`` sources the
    script (guarded so the line is appended at most once).

    Returns:
        ``{"ok", "env_file", "persistent", "sourced_in_bashrc", "detail"}``.
    """
    body = _proxy_env_body(remote_port)

    # Build a single remote command that writes the file via a quoted heredoc.
    # The 'RDMEOF' delimiter is single-quoted so the remote shell performs no
    # expansion on the body — we send the literal text.
    write_cmd = f"cat > ~/.rdm_proxy.sh <<'RDMEOF'\n{body}RDMEOF\n"

    rc, _out, err = _ssh_run(host, write_cmd, timeout=30)
    if rc != 0:
        return {
            "ok": False,
            "env_file": _ENV_FILE,
            "persistent": persistent,
            "sourced_in_bashrc": False,
            "detail": _first_line(err) or f"failed to write env file (rc={rc})",
        }

    sourced = False
    detail = "wrote ~/.rdm_proxy.sh"

    if persistent:
        # Append the source line to ~/.bashrc only if it is not already there.
        guard = shlex.quote(_BASHRC_SOURCE_LINE)
        bashrc_cmd = (
            "touch ~/.bashrc; "
            f"grep -qF {guard} ~/.bashrc || "
            f"printf '%s\\n' {guard} >> ~/.bashrc"
        )
        brc, _bout, berr = _ssh_run(host, bashrc_cmd, timeout=30)
        if brc == 0:
            sourced = True
            detail = "wrote ~/.rdm_proxy.sh and sourced it in ~/.bashrc"
        else:
            detail = (
                "wrote ~/.rdm_proxy.sh but failed to update ~/.bashrc: "
                + (_first_line(berr) or f"rc={brc}")
            )

    return {
        "ok": True,
        "env_file": _ENV_FILE,
        "persistent": persistent,
        "sourced_in_bashrc": sourced,
        "detail": detail,
    }


def remove_remote_proxy_env(host: HostConfig) -> dict[str, Any]:
    """Remove ``~/.rdm_proxy.sh`` and strip the source line from ``~/.bashrc``.

    Returns:
        ``{"ok", "detail"}``.
    """
    # Remove the file, then filter the source line out of ~/.bashrc via a
    # temp file + atomic move (only if ~/.bashrc exists).
    guard = shlex.quote(_BASHRC_SOURCE_LINE)
    remote_cmd = (
        "rm -f ~/.rdm_proxy.sh; "
        "if [ -f ~/.bashrc ]; then "
        f"grep -vF {guard} ~/.bashrc > ~/.bashrc.rdm_tmp && "
        "mv ~/.bashrc.rdm_tmp ~/.bashrc; "
        "fi"
    )

    rc, _out, err = _ssh_run(host, remote_cmd, timeout=30)
    if rc != 0:
        return {
            "ok": False,
            "detail": _first_line(err) or f"failed to remove proxy env (rc={rc})",
        }
    return {"ok": True, "detail": "removed ~/.rdm_proxy.sh and cleaned ~/.bashrc"}


# ---------------------------------------------------------------------------
# Proxy verification
# ---------------------------------------------------------------------------

# HTTP status codes that indicate the endpoint was reached (even if the
# request was rejected for auth/method reasons).
_REACHABLE_CODES = {"200", "201", "204", "400", "401", "403", "404", "405", "429"}


def _curl_probe(remote_port: int, url: str) -> str:
    """Build a curl command that prints only the HTTP status code via the proxy."""
    return (
        "curl -s -o /dev/null -w '%{http_code}' --max-time 10 "
        f"-x socks5h://127.0.0.1:{remote_port} {shlex.quote(url)}"
    )


def _is_reachable(code: str) -> bool:
    """Return True if *code* indicates the endpoint responded over the tunnel."""
    code = (code or "").strip()
    if not code or code == "000":
        return False
    return code in _REACHABLE_CODES or code.isdigit()


def verify_remote_proxy(
    host: HostConfig,
    remote_port: int = 7897,
    timeout: int = 25,
) -> dict[str, Any]:
    """Verify the reverse tunnel works by curling AI endpoints via the proxy.

    A reachable-but-unauthorized response (401/403/404/200/405/...) counts as
    OK connectivity; ``000`` or an empty code means failure.

    Returns:
        ``{"ok", "anthropic", "openai", "google", "detail"}`` where ``ok`` is
        True if at least Anthropic OR OpenAI is reachable.
    """
    endpoints = {
        "anthropic": "https://api.anthropic.com/v1/messages",
        "openai": "https://api.openai.com/v1/models",
        "google": "https://generativelanguage.googleapis.com",
    }

    # Single combined remote command, one line of output per endpoint, in a
    # deterministic order so we can map results back by index.
    order = ["anthropic", "openai", "google"]
    combined = "; ".join(
        f"{_curl_probe(remote_port, endpoints[k])}; echo" for k in order
    )

    rc, out, err = _ssh_run(host, combined, timeout=timeout)

    if rc != 0 and not out.strip():
        msg = _first_line(err) or f"ssh exited with code {rc}"
        return {
            "ok": False,
            "anthropic": "000",
            "openai": "000",
            "google": "000",
            "detail": f"proxy verification failed: {msg}",
        }

    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    codes: dict[str, str] = {}
    for idx, key in enumerate(order):
        codes[key] = lines[idx] if idx < len(lines) else "000"

    anthropic_ok = _is_reachable(codes["anthropic"])
    openai_ok = _is_reachable(codes["openai"])
    ok = anthropic_ok or openai_ok

    reachable = [k for k in order if _is_reachable(codes[k])]
    if ok:
        detail = "reachable: " + ", ".join(reachable)
    else:
        detail = (
            "no AI endpoint reachable through the reverse tunnel — "
            "is the reverse proxy running on the local side?"
        )

    return {
        "ok": ok,
        "anthropic": codes["anthropic"],
        "openai": codes["openai"],
        "google": codes["google"],
        "detail": detail,
    }


# ---------------------------------------------------------------------------
# One-click orchestration
# ---------------------------------------------------------------------------

def setup_ai_proxy(
    host: HostConfig,
    remote_port: int = 7897,
    persistent: bool = False,
    verify: bool = True,
) -> dict[str, Any]:
    """Orchestrate remote-side AI-proxy setup (reverse tunnel assumed running).

    Steps:
        1. Check SSH connection.
        2. Write the remote proxy env file (optionally persistent).
        3. Verify proxy connectivity (only when *verify* is True).

    Returns:
        ``{"ok", "steps", "proxy_url", "env_file", "remote_port"}`` where
        ``ok`` is True only if every executed step succeeded.
    """
    steps: list[dict[str, Any]] = []

    # Step 1: connection.
    conn = test_connection(host)
    if conn["ok"]:
        who = conn.get("whoami") or "?"
        hn = conn.get("hostname") or "?"
        conn_detail = f"connected as {who}@{hn} ({conn.get('latency_ms')} ms)"
    else:
        conn_detail = conn["message"]
    steps.append({"name": "Check SSH connection", "ok": conn["ok"], "detail": conn_detail})

    if not conn["ok"]:
        return {
            "ok": False,
            "steps": steps,
            "proxy_url": f"socks5://127.0.0.1:{remote_port}",
            "env_file": _ENV_FILE,
            "remote_port": remote_port,
        }

    # Step 2: write env file.
    env = write_remote_proxy_env(host, remote_port=remote_port, persistent=persistent)
    steps.append({"name": "Write remote proxy env", "ok": env["ok"], "detail": env["detail"]})

    if not env["ok"]:
        return {
            "ok": False,
            "steps": steps,
            "proxy_url": f"socks5://127.0.0.1:{remote_port}",
            "env_file": _ENV_FILE,
            "remote_port": remote_port,
        }

    # Step 3: verify (optional).
    if verify:
        ver = verify_remote_proxy(host, remote_port=remote_port)
        steps.append(
            {"name": "Verify proxy connectivity", "ok": ver["ok"], "detail": ver["detail"]}
        )

    ok = all(step["ok"] for step in steps)
    return {
        "ok": ok,
        "steps": steps,
        "proxy_url": f"socks5://127.0.0.1:{remote_port}",
        "env_file": _ENV_FILE,
        "remote_port": remote_port,
    }


def teardown_ai_proxy(host: HostConfig) -> dict[str, Any]:
    """Tear down the remote AI proxy by removing the env file and bashrc hook.

    Returns:
        The result of :func:`remove_remote_proxy_env`.
    """
    return remove_remote_proxy_env(host)


# ---------------------------------------------------------------------------
# Launch command builder
# ---------------------------------------------------------------------------

def remote_launch_command(
    host: HostConfig,
    tool: str,
    workdir: str | None = None,
    remote_port: int = 7897,
) -> dict[str, Any]:
    """Build a copy-pasteable interactive SSH command to launch *tool* remotely.

    The returned command opens a PTY (``-t``), sources ``~/.rdm_proxy.sh`` so
    the proxy env is active, optionally ``cd``\\ s into *workdir*, and launches
    the tool.  It is **not** executed (an interactive PTY cannot be captured).

    Args:
        host: Target host configuration.
        tool: Either ``"claude"`` or ``"codex"``.
        workdir: Optional remote working directory.
        remote_port: Reverse-tunnel SOCKS5 port (informational; the env file
            already encodes it).

    Returns:
        ``{"command", "tool", "note"}``.
    """
    # Validate / normalise the tool name.
    tool = (tool or "").strip().lower()
    if tool not in ("claude", "codex"):
        return {
            "command": "",
            "tool": tool,
            "note": f"unknown tool '{tool}' — expected 'claude' or 'codex'.",
        }

    # Build the remote shell command portion.
    parts: list[str] = []
    if workdir:
        parts.append(f"cd {shlex.quote(workdir)}")
    parts.append("source ~/.rdm_proxy.sh")
    parts.append(tool)
    remote_inner = "; ".join(parts)

    # Assemble the full ssh command string.  The remote command is quoted as a
    # single argument so it survives shell parsing on the local side.
    ssh_opts = _ssh_base(host)
    ssh_opts.append("-t")  # force PTY allocation for an interactive session
    target = _ssh_target(host)

    command = " ".join(ssh_opts) + f" {target} {shlex.quote(remote_inner)}"

    return {
        "command": command,
        "tool": tool,
        "note": f"Run this in your terminal to launch {tool} on the remote with proxy active.",
    }
