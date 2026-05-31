"""Reverse proxy service -- SSH reverse tunnels for routing remote traffic
through a local proxy (e.g. Clash SOCKS5).

Typical use-case:
  Local machine runs Clash on port 7897.  Remote server is behind GFW and
  cannot reach certain APIs.  An SSH reverse tunnel
  ``ssh -N -R 7897:127.0.0.1:7897 user@host`` exposes the local proxy on the
  remote side so that ``ALL_PROXY=socks5://127.0.0.1:7897`` routes traffic
  through the local Clash instance.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import List

from rdm.config import HostConfig, ReverseProxyConfig
from rdm.models import Service, ServiceType, Status
from rdm.process import spawn_hidden, write_pid

log = logging.getLogger(__name__)


class ReverseProxyService(Service):
    """Manages an SSH reverse-tunnel process."""

    def __init__(
        self,
        config: ReverseProxyConfig,
        host: HostConfig,
        logs_dir: Path,
        clash_port: int = 7897,
    ) -> None:
        super().__init__(name=config.name, kind=ServiceType.REVERSE_PROXY, proxy=config.proxy if hasattr(config, "proxy") else "direct", logs_dir=logs_dir)
        self.config = config
        self.host = host
        self.clash_port = clash_port

    # ------------------------------------------------------------------
    # Command building
    # ------------------------------------------------------------------

    def _build_ssh_cmd(self) -> List[str]:
        """Build the ``ssh -N -R ...`` command list."""
        ssh = shutil.which("ssh") or "ssh"
        cmd: List[str] = [ssh]

        # Reverse tunnel: remote_port on remote binds to local_port on local
        cmd += [
            "-N",
            "-R", f"{self.config.remote_port}:127.0.0.1:{self.config.local_port}",
        ]

        # Security: only localhost on the remote side can use the forwarded port
        cmd += ["-o", "GatewayPorts=no"]

        # Keepalive -- same options used by TunnelService
        cmd += [
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
        ]

        # Disable pseudo-terminal allocation and strict host-key checking
        # to make the background process non-interactive.
        cmd += [
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
        ]

        # Port
        if self.host.port and self.host.port != 22:
            cmd += ["-p", str(self.host.port)]

        # Identity file
        if self.host.identity:
            identity = str(Path(self.host.identity).expanduser())
            cmd += ["-i", identity]

        # Proxy mode for the SSH connection itself
        proxy = self.proxy
        if proxy == "clash":
            # Route the SSH connection through the local Clash SOCKS5 proxy
            cmd += [
                "-o", f"ProxyCommand=nc -x 127.0.0.1:{self.clash_port} %h %p",
            ]
        elif proxy.startswith("jump:"):
            jump_host = proxy.split(":", 1)[1]
            cmd += ["-J", jump_host]
        # proxy == "direct" -> no extra options

        # Target host
        cmd.append(f"{self.host.user}@{self.host.host}")

        return cmd

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the reverse-proxy SSH tunnel as a background process."""
        if self.status == Status.RUNNING:
            log.info("reverse-proxy %s is already running (pid %s)", self.name, self.pid)
            return

        self.status = Status.STARTING
        cmd = self._build_ssh_cmd()
        log.info("starting reverse-proxy %s: %s", self.name, " ".join(cmd))

        try:
            pid = spawn_hidden(cmd, log_path=self.log_file)
            self.pid = pid
            self.status = Status.RUNNING
            self.last_error = ""
            self.consecutive_fails = 0
            import time
            self.started_at = time.time()
            write_pid(self.pid_file, pid)
            log.info("reverse-proxy %s started (pid %d)", self.name, pid)
        except Exception as exc:
            self.status = Status.FAILED
            self.last_error = str(exc)
            self.consecutive_fails += 1
            log.error("failed to start reverse-proxy %s: %s", self.name, exc)
