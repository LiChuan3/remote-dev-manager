"""SSH tunnel service for remote-dev-manager."""

from __future__ import annotations

import platform
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

from rdm.models import Service, ServiceType, Status
from rdm.process import spawn_hidden, write_pid

if TYPE_CHECKING:
    from rdm.config import ForwardRule, HostConfig, TunnelConfig


class TunnelService(Service):
    """Manages an SSH tunnel with port forwarding."""

    def __init__(
        self,
        config: TunnelConfig,
        host: HostConfig,
        logs_dir: Path,
        clash_port: int = 7897,
    ) -> None:
        super().__init__(name=config.name, kind=ServiceType.TUNNEL, proxy=config.proxy, logs_dir=logs_dir)
        self.config = config
        self.host = host
        self.clash_port = clash_port

    # ------------------------------------------------------------------
    # Command construction helpers
    # ------------------------------------------------------------------

    def _base_ssh_args(self) -> list[str]:
        """Return the base ssh command with keepalive and safety options."""
        return [
            "ssh",
            "-N",
            "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3",
            "-o", "TCPKeepAlive=yes",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=15",
            "-o", "BatchMode=yes",
        ]

    def _port_args(self) -> list[str]:
        """Return port arguments."""
        return ["-p", str(self.host.port)]

    def _identity_args(self) -> list[str]:
        """Return identity-file arguments (empty list when not configured)."""
        if self.host.identity:
            identity_path = str(Path(self.host.identity).expanduser())
            return ["-i", identity_path]
        return []

    def _forward_args(self) -> list[str]:
        """Translate ForwardRule entries into ssh -L / -R / -D flags."""
        args: list[str] = []
        for fwd in self.config.forwards:
            fwd_type: str = getattr(fwd, "type", "local")
            local_port: int = fwd.local_port
            remote_host: str = getattr(fwd, "remote_host", "127.0.0.1")
            remote_port: int = fwd.remote_port

            if fwd_type == "local":
                args += ["-L", f"{local_port}:{remote_host}:{remote_port}"]
            elif fwd_type == "remote":
                args += ["-R", f"{remote_port}:{remote_host}:{local_port}"]
            elif fwd_type == "dynamic":
                args += ["-D", str(local_port)]
        return args

    def _proxy_args(self) -> list[str]:
        """Return proxy-related ssh options based on self.proxy."""
        proxy = self.proxy or "direct"

        if proxy == "direct":
            return []

        if proxy == "clash":
            return self._clash_proxy_args()

        if proxy.startswith("jump:"):
            jump_alias = proxy[len("jump:"):]
            return ["-J", jump_alias]

        return []

    def _clash_proxy_args(self) -> list[str]:
        """Build ProxyCommand for SOCKS5 via Clash."""
        is_windows = platform.system() == "Windows"
        if is_windows:
            # On Windows, use connect.exe (shipped with Git for Windows
            # under mingw64/bin — expected to be on PATH).
            proxy_cmd = f"connect -S 127.0.0.1:{self.clash_port} %h %p"
        else:
            proxy_cmd = f"nc -x 127.0.0.1:{self.clash_port} %h %p"
        return ["-o", f"ProxyCommand={proxy_cmd}"]

    def _target(self) -> str:
        """Return user@host string."""
        return f"{self.host.user}@{self.host.host}"

    def _build_command(self) -> list[str]:
        """Assemble the full ssh tunnel command."""
        cmd: list[str] = []
        cmd += self._base_ssh_args()
        cmd += self._port_args()
        cmd += self._identity_args()
        cmd += self._forward_args()
        cmd += self._proxy_args()
        cmd.append(self._target())
        return cmd

    # ------------------------------------------------------------------
    # Service lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the SSH tunnel process."""
        if self.status == Status.RUNNING:
            return

        self.status = Status.STARTING
        self.last_error = ""

        cmd = self._build_command()

        try:
            pid = spawn_hidden(cmd=cmd, log_path=self.log_file)
            self.pid = pid
            self.started_at = time.time()
            write_pid(self.pid_file, pid)
            self.status = Status.RUNNING
        except Exception as exc:  # noqa: BLE001
            self.status = Status.FAILED
            self.last_error = str(exc)
            raise
