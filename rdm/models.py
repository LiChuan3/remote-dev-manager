"""Service model base class and enums for rdm."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path


class ServiceType(Enum):
    TUNNEL = "tunnel"
    MOUNT = "mount"
    REVERSE_PROXY = "reverse_proxy"
    SYNC = "sync"


class Status(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"


class Service(ABC):
    """Abstract base class for all managed services.

    Subclasses must implement :meth:`start` to spawn the underlying process.
    """

    # Backoff parameters
    _BACKOFF_BASE: float = 2.0
    _BACKOFF_MAX: float = 300.0  # 5 minutes cap

    def __init__(
        self,
        name: str,
        kind: ServiceType,
        proxy: str,
        logs_dir: Path,
    ) -> None:
        self.name: str = name
        self.kind: ServiceType = kind
        self.proxy: str = proxy
        self.status: Status = Status.STOPPED
        self.pid: int | None = None
        self.started_at: float | None = None
        self.last_error: str | None = None
        self.restart_count: int = 0
        self.user_stopped: bool = False
        self.consecutive_fails: int = 0
        self.next_retry_at: float | None = None

        self._logs_dir: Path = logs_dir

    # ------------------------------------------------------------------
    # Path properties
    # ------------------------------------------------------------------

    @property
    def log_file(self) -> Path:
        return self._logs_dir / f"{self.name}.log"

    @property
    def pid_file(self) -> Path:
        return self._logs_dir / f"{self.name}.pid"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def start(self) -> None:
        """Spawn the underlying process.

        Implementations must:
        - Build the command line
        - Call :func:`rdm.process.spawn_hidden` to get a PID
        - Call :func:`rdm.process.write_pid`
        - Set ``self.pid``, ``self.started_at``, ``self.status``
        """

    def stop(self) -> None:
        """Stop the service, kill the process, and clean up the PID file."""
        from rdm.process import clear_pid, terminate_tree

        if self.pid is not None:
            try:
                terminate_tree(self.pid)
            except Exception:
                pass  # process may already be gone
            self.pid = None

        clear_pid(self.pid_file)
        self.status = Status.STOPPED
        self.started_at = None

    def restart(self) -> None:
        """Stop and then start the service."""
        self.stop()
        self.restart_count += 1
        self.start()

    def poll(self) -> None:
        """Check whether the process is still alive and update status.

        If the process has died unexpectedly (``user_stopped`` is False),
        the status is set to FAILED and backoff fields are updated.
        """
        from rdm.process import is_alive

        if self.pid is None:
            return

        if is_alive(self.pid):
            if self.status != Status.RUNNING:
                self.status = Status.RUNNING
                # Reset backoff on successful run
                self.consecutive_fails = 0
                self.next_retry_at = None
        else:
            # Process died
            self.pid = None
            if self.user_stopped:
                self.status = Status.STOPPED
            else:
                self.status = Status.FAILED
                self.consecutive_fails += 1
                delay = min(
                    self._BACKOFF_BASE ** self.consecutive_fails,
                    self._BACKOFF_MAX,
                )
                self.next_retry_at = time.time() + delay
                self.last_error = "Process exited unexpectedly"

    def reattach(self) -> None:
        """Attempt to reattach to an existing process via the PID file.

        If the PID file exists and the process is alive, restore the service
        to RUNNING state.  Otherwise, clean up stale state.
        """
        from rdm.process import clear_pid, is_alive, read_pid

        pid = read_pid(self.pid_file)
        if pid is None:
            return

        if is_alive(pid):
            self.pid = pid
            self.status = Status.RUNNING
            # We don't know the real start time; use current time as fallback
            if self.started_at is None:
                from rdm.process import process_start_time

                pst = process_start_time(pid)
                self.started_at = pst if pst is not None else time.time()
            self.user_stopped = False
        else:
            # Stale PID file
            clear_pid(self.pid_file)
            self.pid = None
            self.status = Status.STOPPED

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def uptime_str(self) -> str:
        """Return a human-readable uptime string.

        Format examples: ``"12s"``, ``"3m 45s"``, ``"2h 10m"``, ``"1d 4h"``.
        Returns ``"-"`` if the service is not running.
        """
        if self.started_at is None or self.status != Status.RUNNING:
            return "-"

        elapsed = int(time.time() - self.started_at)
        if elapsed < 0:
            return "0s"

        days, remainder = divmod(elapsed, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {minutes}m"
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"
