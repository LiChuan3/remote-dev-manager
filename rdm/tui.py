"""Interactive Textual TUI for Remote Dev Manager."""

from __future__ import annotations

import time
from pathlib import Path
from typing import ClassVar

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header, Log, Static

from rdm.config import Config, set_service_proxy
from rdm.models import Service, Status
from rdm.tunnel import TunnelService
from rdm.mount import MountService
from rdm.proxy import ReverseProxyService


# ---------------------------------------------------------------------------
# Proxy cycling order
# ---------------------------------------------------------------------------

_PROXY_CYCLE = ("direct", "clash")


def _next_proxy(current: str) -> str:
    """Cycle to the next proxy mode."""
    try:
        idx = _PROXY_CYCLE.index(current)
        return _PROXY_CYCLE[(idx + 1) % len(_PROXY_CYCLE)]
    except ValueError:
        return _PROXY_CYCLE[0]


# ---------------------------------------------------------------------------
# ServiceTable
# ---------------------------------------------------------------------------

_COLUMNS = ("Type", "Name", "Status", "Proxy", "Uptime", "PID", "Note")


class ServiceTable(DataTable):
    """Table listing all managed services."""

    _services: list[Service] = []
    _row_keys: list[str] = []

    def rebuild(self, services: list[Service]) -> None:
        """Full rebuild of table rows from the service list."""
        self._services = services
        self.clear(columns=True)
        for col in _COLUMNS:
            self.add_column(col, key=col)
        self._row_keys = []
        for svc in services:
            row_key = self.add_row(*self._service_cells(svc), key=svc.name)
            self._row_keys.append(svc.name)

    def refresh_rows(self, services: list[Service]) -> None:
        """Update cell values in-place without clearing the table."""
        self._services = services
        for svc in services:
            cells = self._service_cells(svc)
            for i, col in enumerate(_COLUMNS):
                try:
                    self.update_cell(svc.name, col, cells[i])
                except Exception:
                    pass  # row may not exist yet

    def get_selected_service(self) -> Service | None:
        """Return the Service at the current cursor row."""
        if not self._services:
            return None
        try:
            row_key, _ = self.coordinate_to_cell_key(self.cursor_coordinate)
            name = str(row_key)
        except Exception:
            return None
        for svc in self._services:
            if svc.name == name:
                return svc
        return None

    @staticmethod
    def _service_cells(svc: Service) -> tuple[str, ...]:
        kind_label = svc.kind.name.replace("_", " ").title()
        status_label = svc.status.name
        pid_str = str(svc.pid) if svc.pid else "-"
        note = svc.last_error or ""
        if len(note) > 40:
            note = note[:37] + "..."
        return (kind_label, svc.name, status_label, svc.proxy, svc.uptime_str(), pid_str, note)


# ---------------------------------------------------------------------------
# LogView
# ---------------------------------------------------------------------------

class LogView(Log):
    """A log widget that tails a service log file."""

    _log_path: Path | None = None
    _read_pos: int = 0

    def attach(self, path: Path) -> None:
        """Start tailing *path*."""
        self.clear()
        self._log_path = path
        self._read_pos = 0
        if path.exists():
            text = path.read_text(errors="replace")
            lines = text.splitlines()
            # Show last 100 lines initially
            for line in lines[-100:]:
                self.write_line(line)
            self._read_pos = path.stat().st_size

    def detach(self) -> None:
        """Stop tailing."""
        self._log_path = None
        self._read_pos = 0

    def poll(self) -> None:
        """Read any new bytes appended since last poll."""
        if self._log_path is None or not self._log_path.exists():
            return
        sz = self._log_path.stat().st_size
        if sz < self._read_pos:
            # File was truncated
            self._read_pos = 0
        if sz > self._read_pos:
            try:
                with open(self._log_path, "r", errors="replace") as fh:
                    fh.seek(self._read_pos)
                    new_text = fh.read()
                self._read_pos = sz
                for line in new_text.splitlines():
                    self.write_line(line)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------

class StatusBar(Static):
    """Single-line status summary."""

    text: reactive[str] = reactive("", layout=True)

    def render(self) -> str:
        return self.text

    def update_counts(
        self, running: int, failed: int, auto_restart: bool
    ) -> None:
        ar = "on" if auto_restart else "off"
        self.text = (
            f"  {running} running  {failed} failed  "
            f"Auto-restart: {ar}  "
            f"(services run independently)"
        )


# ---------------------------------------------------------------------------
# ManagerApp
# ---------------------------------------------------------------------------

class ManagerApp(App):
    """Main TUI application for Remote Dev Manager."""

    TITLE = "Remote Dev Manager"
    SUB_TITLE = ""

    CSS = """
    Screen {
        layout: vertical;
    }
    #table-area {
        height: 1fr;
        min-height: 8;
    }
    #log-area {
        height: 12;
        display: none;
        border-top: solid $accent;
    }
    #log-area.visible {
        display: block;
    }
    #status-bar {
        height: 1;
        dock: bottom;
        background: $boost;
        color: $text;
        padding: 0 1;
    }
    ServiceTable {
        height: 1fr;
    }
    LogView {
        height: 1fr;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("space", "toggle_service", "Start/Stop", show=True),
        Binding("r", "restart_service", "Restart", show=True),
        Binding("c", "cycle_proxy", "Cycle proxy", show=True),
        Binding("l", "show_log", "Log", show=True),
        Binding("escape", "hide_log", "Hide log", show=False),
        Binding("u", "up_all", "Start all", show=True),
        Binding("d", "down_all", "Stop all", show=True),
        Binding("a", "toggle_auto_restart", "Auto-restart", show=True),
        Binding("q", "quit_app", "Quit", show=True),
    ]

    auto_restart: reactive[bool] = reactive(True)

    def __init__(
        self,
        config: Config,
        services: list[Service],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._services = services
        self._log_showing = False
        self._supervisor_timer: Timer | None = None
        # Exponential backoff state per service name
        self._backoff: dict[str, float] = {}
        self._stable_since: dict[str, float] = {}

    # -- Compose --------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Vertical(id="table-area"):
                yield ServiceTable(id="svc-table")
            with Vertical(id="log-area"):
                yield LogView(id="log-view")
        yield StatusBar(id="status-bar")
        yield Footer()

    # -- Lifecycle ------------------------------------------------------

    def on_mount(self) -> None:
        self.auto_restart = self._config.defaults.auto_restart
        table = self.query_one("#svc-table", ServiceTable)
        table.cursor_type = "row"
        table.rebuild(self._services)
        self._refresh_status_bar()
        # Poll and reattach existing processes
        for svc in self._services:
            svc.reattach()
            svc.poll()
        table.refresh_rows(self._services)
        self._refresh_status_bar()
        # Supervisor tick every 2 seconds
        self._supervisor_timer = self.set_interval(2.0, self._supervisor_tick)

    # -- Supervisor -----------------------------------------------------

    def _supervisor_tick(self) -> None:
        """Periodic poll + auto-restart logic."""
        now = time.monotonic()
        for svc in self._services:
            svc.poll()

            # Track stable running time
            if svc.status == Status.RUNNING:
                if svc.name not in self._stable_since:
                    self._stable_since[svc.name] = now
                elif now - self._stable_since[svc.name] > 60.0:
                    # Clear backoff after 60s stable
                    self._backoff.pop(svc.name, None)
                    svc.consecutive_fails = 0
            else:
                self._stable_since.pop(svc.name, None)

            # Auto-restart failed services
            if (
                self.auto_restart
                and svc.status == Status.FAILED
                and not svc.user_stopped
            ):
                backoff = self._backoff.get(svc.name, 60.0)
                retry_at = svc.next_retry_at or 0.0
                if now >= retry_at:
                    try:
                        svc.restart()
                    except Exception:
                        pass
                    svc.consecutive_fails += 1
                    # Exponential backoff: 60s base, 2x, cap 600s
                    new_backoff = min(backoff * 2, 600.0)
                    self._backoff[svc.name] = new_backoff
                    svc.next_retry_at = now + new_backoff

        # Refresh UI
        table = self.query_one("#svc-table", ServiceTable)
        table.refresh_rows(self._services)
        self._refresh_status_bar()

        # Poll log view
        log_view = self.query_one("#log-view", LogView)
        if self._log_showing:
            log_view.poll()

    # -- Status bar -----------------------------------------------------

    def _refresh_status_bar(self) -> None:
        running = sum(1 for s in self._services if s.status == Status.RUNNING)
        failed = sum(1 for s in self._services if s.status == Status.FAILED)
        bar = self.query_one("#status-bar", StatusBar)
        bar.update_counts(running, failed, self.auto_restart)

    # -- Actions --------------------------------------------------------

    def action_toggle_service(self) -> None:
        table = self.query_one("#svc-table", ServiceTable)
        svc = table.get_selected_service()
        if svc is None:
            return
        svc.poll()
        if svc.status in (Status.RUNNING, Status.STARTING):
            svc.stop()
            svc.user_stopped = True
        else:
            svc.user_stopped = False
            self._backoff.pop(svc.name, None)
            try:
                svc.start()
            except Exception as exc:
                svc.last_error = str(exc)
        table.refresh_rows(self._services)
        self._refresh_status_bar()

    def action_restart_service(self) -> None:
        table = self.query_one("#svc-table", ServiceTable)
        svc = table.get_selected_service()
        if svc is None:
            return
        svc.user_stopped = False
        self._backoff.pop(svc.name, None)
        try:
            svc.restart()
        except Exception as exc:
            svc.last_error = str(exc)
        table.refresh_rows(self._services)
        self._refresh_status_bar()

    def action_cycle_proxy(self) -> None:
        table = self.query_one("#svc-table", ServiceTable)
        svc = table.get_selected_service()
        if svc is None:
            return
        new_proxy = _next_proxy(svc.proxy)
        svc.proxy = new_proxy
        # Persist to state file
        kind_key = svc.kind.name.lower()
        set_service_proxy(
            self._config.workspace_path, kind_key, svc.name, new_proxy
        )
        table.refresh_rows(self._services)

    def action_show_log(self) -> None:
        table = self.query_one("#svc-table", ServiceTable)
        svc = table.get_selected_service()
        if svc is None:
            return
        log_area = self.query_one("#log-area")
        log_view = self.query_one("#log-view", LogView)
        log_view.attach(svc.log_file)
        log_area.add_class("visible")
        self._log_showing = True

    def action_hide_log(self) -> None:
        log_area = self.query_one("#log-area")
        log_view = self.query_one("#log-view", LogView)
        log_view.detach()
        log_area.remove_class("visible")
        self._log_showing = False

    def action_up_all(self) -> None:
        for svc in self._services:
            svc.user_stopped = False
            self._backoff.pop(svc.name, None)
            svc.poll()
            if svc.status not in (Status.RUNNING, Status.STARTING):
                try:
                    svc.start()
                except Exception as exc:
                    svc.last_error = str(exc)
        table = self.query_one("#svc-table", ServiceTable)
        table.refresh_rows(self._services)
        self._refresh_status_bar()

    def action_down_all(self) -> None:
        for svc in self._services:
            svc.poll()
            if svc.status in (Status.RUNNING, Status.STARTING):
                svc.stop()
                svc.user_stopped = True
        table = self.query_one("#svc-table", ServiceTable)
        table.refresh_rows(self._services)
        self._refresh_status_bar()

    def action_toggle_auto_restart(self) -> None:
        self.auto_restart = not self.auto_restart
        self._refresh_status_bar()

    def action_quit_app(self) -> None:
        # Services keep running - we just exit the TUI
        self.exit()
