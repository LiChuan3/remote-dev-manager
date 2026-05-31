"""CLI entry point for Remote Dev Manager (rdm)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from rdm import __version__
from rdm.config import (
    Config,
    find_config,
    load_config,
    load_state,
    get_service_proxy,
)
from rdm.models import Service, ServiceType, Status
from rdm.tunnel import TunnelService
from rdm.mount import MountService
from rdm.proxy import ReverseProxyService
from rdm.sync import sync_push, sync_pull
from rdm.mirror import (
    mirror_pull, mirror_push, mirror_status,
    list_remote_dirs, add_mirror_to_config, estimate_mirror_size,
)

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

class ConfigNotFoundError(Exception):
    """Raised when no configuration file can be located."""


def _load_config_or_die(path: str | None = None) -> Config:
    """Load config, raising ConfigNotFoundError if not found."""
    config_path: Path | None = Path(path) if path else find_config()
    if config_path is None:
        raise ConfigNotFoundError(
            "No rdm config file found.\n"
            "Searched: $RDM_CONFIG, ./rdm.yaml, ~/.config/rdm/config.yaml\n"
            "Run 'rdm init' to generate a starter config in the current directory."
        )
    return load_config(config_path)


# ---------------------------------------------------------------------------
# Service factory
# ---------------------------------------------------------------------------

def build_services(config: Config) -> list[Service]:
    """Instantiate every service defined in *config*, applying proxy overrides."""
    services: list[Service] = []
    state = load_state(config.workspace_path)

    for tc in config.tunnels:
        host = config.hosts[tc.host_ref]
        proxy = (
            get_service_proxy(config.workspace_path, "tunnel", tc.name)
            or tc.proxy
            or config.defaults.proxy
        )
        svc = TunnelService(
            config=tc,
            host=host,
            logs_dir=config.logs_dir,
            clash_port=config.defaults.clash_port,
        )
        svc.proxy = proxy
        services.append(svc)

    for mc in config.mounts:
        host = config.hosts[mc.host_ref]
        proxy = (
            get_service_proxy(config.workspace_path, "mount", mc.name)
            or config.defaults.proxy
        )
        svc = MountService(
            config=mc,
            host=host,
            logs_dir=config.logs_dir,
            workspace=config.workspace_path,
            clash_port=config.defaults.clash_port,
        )
        svc.proxy = proxy
        services.append(svc)

    for rpc in config.reverse_proxies:
        host = config.hosts[rpc.host_ref]
        proxy = (
            get_service_proxy(config.workspace_path, "reverse_proxy", rpc.name)
            or config.defaults.proxy
        )
        svc = ReverseProxyService(
            config=rpc,
            host=host,
            logs_dir=config.logs_dir,
            clash_port=config.defaults.clash_port,
        )
        svc.proxy = proxy
        services.append(svc)

    return services


# ---------------------------------------------------------------------------
# ASCII status table
# ---------------------------------------------------------------------------

def _print_status_table(services: list[Service]) -> None:
    """Print an ASCII-art table of all services."""
    headers = ("Name", "Type", "Status", "Proxy", "PID", "Uptime")
    rows: list[tuple[str, ...]] = []
    for svc in services:
        svc.poll()
        rows.append((
            svc.name,
            svc.kind.name.replace("_", " ").title(),
            svc.status.name,
            svc.proxy,
            str(svc.pid) if svc.pid else "-",
            svc.uptime_str(),
        ))

    # compute column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: tuple[str, ...]) -> str:
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells))

    print(fmt_row(headers))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt_row(row))


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _cmd_up(args: argparse.Namespace) -> int:
    config = _load_config_or_die(args.config)
    services = build_services(config)
    targets = _filter_services(services, args.names)
    if targets is None:
        return 1
    for svc in targets:
        print(f"Starting {svc.name} ...", end=" ", flush=True)
        try:
            svc.start()
            print("OK")
        except Exception as exc:
            print(f"FAILED: {exc}")
    return 0


def _cmd_down(args: argparse.Namespace) -> int:
    config = _load_config_or_die(args.config)
    services = build_services(config)
    targets = _filter_services(services, args.names)
    if targets is None:
        return 1
    for svc in targets:
        svc.poll()
        if svc.status in (Status.RUNNING, Status.STARTING):
            print(f"Stopping {svc.name} ...", end=" ", flush=True)
            svc.stop()
            print("OK")
        else:
            print(f"{svc.name} is not running.")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    config = _load_config_or_die(args.config)
    services = build_services(config)
    if not services:
        print("No services defined in config.")
        return 0
    _print_status_table(services)
    return 0


def _cmd_tui(args: argparse.Namespace) -> int:
    config = _load_config_or_die(args.config)
    services = build_services(config)
    from rdm.tui import ManagerApp
    app = ManagerApp(config=config, services=services)
    app.run()
    return 0


def _cmd_log(args: argparse.Namespace) -> int:
    config = _load_config_or_die(args.config)
    services = build_services(config)
    svc = _find_service(services, args.name)
    if svc is None:
        return 1
    log_path: Path = svc.log_file
    if not log_path.exists():
        print(f"No log file found for {args.name} at {log_path}")
        return 1

    # Print last 50 lines then follow
    lines = log_path.read_text(errors="replace").splitlines()
    for line in lines[-50:]:
        print(line)

    if args.follow:
        print(f"--- following {log_path} (Ctrl+C to stop) ---")
        try:
            pos = log_path.stat().st_size
            while True:
                time.sleep(0.5)
                sz = log_path.stat().st_size
                if sz > pos:
                    with open(log_path, "r", errors="replace") as fh:
                        fh.seek(pos)
                        chunk = fh.read()
                        if chunk:
                            print(chunk, end="", flush=True)
                    pos = sz
                elif sz < pos:
                    # file was truncated / rotated
                    pos = 0
        except KeyboardInterrupt:
            pass
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    config = _load_config_or_die(args.config)
    sc = None
    for s in config.syncs:
        if s.name == args.name:
            sc = s
            break
    if sc is None:
        print(f"Sync config '{args.name}' not found.")
        return 1
    host = config.hosts[sc.host_ref]
    dry_run = getattr(args, "dry_run", False)
    try:
        if args.pull:
            sync_pull(sc, host, dry_run=dry_run)
        else:
            sync_push(sc, host, dry_run=dry_run)
    except Exception as exc:
        print(f"Sync failed: {exc}")
        return 1
    print("Sync complete.")
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    dest = Path.cwd() / "rdm.yaml"
    if dest.exists() and not args.force:
        print(f"{dest} already exists. Use --force to overwrite.")
        return 1
    template = _CONFIG_TEMPLATE
    dest.write_text(template, encoding="utf-8")
    print(f"Created {dest}")
    return 0


def _cmd_version(args: argparse.Namespace) -> int:
    print(f"rdm {__version__}")
    return 0


def _cmd_web(args: argparse.Namespace) -> int:
    """Launch the FastAPI sidecar / web API (used by the desktop app or standalone)."""
    try:
        from rdm.api.server import run
    except ImportError:
        print(
            "The web API requires extra dependencies. Install them with:\n"
            "  pip install 'remote-dev-manager[api]'",
            file=sys.stderr,
        )
        return 1
    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8765)
    print(f"rdm web API listening on http://{host}:{port}  (docs at /docs)")
    run(host=host, port=port, config_path=args.config)
    return 0


def _cmd_mirror(args: argparse.Namespace) -> int:
    """Route mirror sub-subcommands."""
    action = getattr(args, "mirror_action", None)
    if action is None:
        # No sub-action: treat as pull if name provided
        name = getattr(args, "name", None)
        if name:
            args.mirror_action = "pull"
            return _cmd_mirror_pull(args)
        print("Usage: rdm mirror {pull,push,status,browse,add,list} ...")
        return 1
    handlers = {
        "pull": _cmd_mirror_pull,
        "push": _cmd_mirror_push,
        "status": _cmd_mirror_status,
        "browse": _cmd_mirror_browse,
        "add": _cmd_mirror_add,
        "list": _cmd_mirror_list,
    }
    handler = handlers.get(action)
    if handler is None:
        print(f"Unknown mirror action: {action}")
        return 1
    return handler(args)


def _resolve_mirror_local_path(config, mc):
    """Resolve mirror local_path, defaulting to workspace/mirrors/name."""
    if mc.local_path:
        return mc
    from dataclasses import replace
    resolved = str(config.workspace_path / "mirrors" / mc.name)
    return replace(mc, local_path=resolved)


def _cmd_mirror_pull(args: argparse.Namespace) -> int:
    config = _load_config_or_die(args.config)
    mc = _find_mirror(config, args.name)
    if mc is None:
        return 1
    mc = _resolve_mirror_local_path(config, mc)
    host = config.hosts[mc.host_ref]
    dry_run = getattr(args, "dry_run", False)
    result = mirror_pull(mc, host, dry_run=dry_run)
    if result["errors"]:
        for e in result["errors"]:
            print(f"  Error: {e}", file=sys.stderr)
        return 1
    if not dry_run:
        print(f"\nMirror synced to {result.get('local_path', mc.local_path)}")
        print(f"  Files: {result['files_transferred']}, Bytes: {result['bytes']}")
    return 0


def _cmd_mirror_push(args: argparse.Namespace) -> int:
    config = _load_config_or_die(args.config)
    mc = _find_mirror(config, args.name)
    if mc is None:
        return 1
    mc = _resolve_mirror_local_path(config, mc)
    host = config.hosts[mc.host_ref]
    dry_run = getattr(args, "dry_run", False)
    result = mirror_push(mc, host, dry_run=dry_run)
    if result["errors"]:
        for e in result["errors"]:
            print(f"  Error: {e}", file=sys.stderr)
        return 1
    if not dry_run:
        print(f"\nPushed to {host.user}@{host.host}:{mc.remote_path}")
        print(f"  Files: {result['files_transferred']}, Bytes: {result['bytes']}")
    return 0


def _cmd_mirror_status(args: argparse.Namespace) -> int:
    config = _load_config_or_die(args.config)
    mc = _find_mirror(config, args.name)
    if mc is None:
        return 1
    mc = _resolve_mirror_local_path(config, mc)
    host = config.hosts[mc.host_ref]
    result = mirror_status(mc, host)
    print(f"\nSummary: {result['pull_changes']} files to pull, {result['push_changes']} files to push")
    return 0


def _cmd_mirror_browse(args: argparse.Namespace) -> int:
    config = _load_config_or_die(args.config)
    host_name = args.host
    if host_name not in config.hosts:
        print(f"Unknown host: {host_name}")
        print(f"Available: {', '.join(config.hosts)}")
        return 1
    host = config.hosts[host_name]
    base_path = getattr(args, "path", "~")
    depth = getattr(args, "depth", 3)

    print(f"Scanning {host.user}@{host.host}:{base_path} (depth={depth})...")
    print()

    repos = list_remote_dirs(host, base_path, max_depth=depth)
    if not repos:
        print("No code repositories found.")
        return 0

    # Print table
    print(f"  {'#':<4} {'Path':<40} {'Type':<15} {'Size':<10}")
    print(f"  {'─'*4} {'─'*40} {'─'*15} {'─'*10}")
    for i, repo in enumerate(repos, 1):
        path = repo["path"]
        if len(path) > 38:
            path = "..." + path[-35:]
        print(f"  {i:<4} {path:<40} {repo['type']:<15} {repo['size']:<10}")

    print(f"\n  Found {len(repos)} repositories.")
    print(f"  To add one: rdm mirror add {host_name} <remote_path> --name <name>")
    return 0


def _cmd_mirror_add(args: argparse.Namespace) -> int:
    config = _load_config_or_die(args.config)
    host_name = args.host
    if host_name not in config.hosts:
        print(f"Unknown host: {host_name}")
        return 1

    remote_path = args.remote_path
    name = getattr(args, "mirror_name", None) or Path(remote_path).name or "mirror"
    local_path = getattr(args, "local", "") or ""
    auto_exclude = not getattr(args, "no_auto_exclude", False)

    config_path = config._config_path
    if config_path is None:
        print("Cannot determine config file path.")
        return 1

    add_mirror_to_config(config_path, name, host_name, remote_path, local_path, auto_exclude)
    print(f"\nRun 'rdm mirror pull {name}' to start the initial sync.")
    return 0


def _cmd_mirror_list(args: argparse.Namespace) -> int:
    config = _load_config_or_die(args.config)
    if not config.mirrors:
        print("No mirrors configured. Use 'rdm mirror add' or edit rdm.yaml.")
        return 0

    print(f"  {'Name':<20} {'Host':<15} {'Remote Path':<35} {'Local Path':<30} {'Auto-Excl':<10}")
    print(f"  {'─'*20} {'─'*15} {'─'*35} {'─'*30} {'─'*10}")
    for mc in config.mirrors:
        mc_resolved = _resolve_mirror_local_path(config, mc)
        local = mc_resolved.local_path
        if len(local) > 28:
            local = "..." + local[-25:]
        remote = mc.remote_path
        if len(remote) > 33:
            remote = "..." + remote[-30:]
        auto = "yes" if mc.auto_exclude else "no"
        local_exists = "✓" if Path(mc_resolved.local_path).exists() else "✗"
        print(f"  {mc.name:<20} {mc.host_ref:<15} {remote:<35} {local_exists} {local:<28} {auto:<10}")
    return 0


def _find_mirror(config, name: str):
    """Find a MirrorConfig by name."""
    for mc in config.mirrors:
        if mc.name == name:
            return mc
    print(f"Mirror '{name}' not found.")
    if config.mirrors:
        print(f"Available: {', '.join(m.name for m in config.mirrors)}")
    else:
        print("No mirrors configured. Use 'rdm mirror add' or edit rdm.yaml.")
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _filter_services(
    services: list[Service], names: list[str] | None
) -> list[Service] | None:
    """Return the subset of services matching *names*, or all if empty."""
    if not names:
        return services
    by_name = {s.name: s for s in services}
    result: list[Service] = []
    for n in names:
        if n not in by_name:
            print(f"Unknown service: {n}")
            print(f"Available: {', '.join(by_name)}")
            return None
        result.append(by_name[n])
    return result


def _find_service(services: list[Service], name: str) -> Service | None:
    for s in services:
        if s.name == name:
            return s
    print(f"Unknown service: {name}")
    print(f"Available: {', '.join(s.name for s in services)}")
    return None


# ---------------------------------------------------------------------------
# Config template
# ---------------------------------------------------------------------------

_CONFIG_TEMPLATE = """\
version: 1
defaults:
  proxy: direct          # direct | clash | jump:<ssh-alias>
  clash_port: 7897       # local SOCKS5 proxy port
  auto_restart: true
  workspace: ""          # base dir for mounts/logs (default: config dir)
  locale: en             # en | zh

hosts:
  my-server:
    user: ubuntu
    host: 192.168.1.100
    port: 22
    identity: ~/.ssh/id_rsa

tunnels:
  - name: jupyter
    host: my-server
    forwards:
      - type: local
        local_port: 8888
        remote_port: 8888

mounts:
  - name: server-home
    host: my-server
    remote_path: /home/ubuntu

reverse_proxies: []

syncs: []

mirrors: []
"""


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rdm",
        description="Remote Dev Manager - manage SSH tunnels, mounts, proxies & syncs",
    )
    parser.add_argument(
        "-c", "--config",
        default=None,
        help="Path to config file (default: auto-detect)",
    )
    sub = parser.add_subparsers(dest="command")

    # up
    p_up = sub.add_parser("up", help="Start services")
    p_up.add_argument("names", nargs="*", help="Service names (default: all)")

    # down
    p_down = sub.add_parser("down", help="Stop services")
    p_down.add_argument("names", nargs="*", help="Service names (default: all)")

    # status
    sub.add_parser("status", help="Show service status table")

    # tui
    sub.add_parser("tui", help="Launch interactive TUI")

    # log
    p_log = sub.add_parser("log", help="Tail a service log")
    p_log.add_argument("name", help="Service name")
    p_log.add_argument(
        "-f", "--follow",
        action="store_true",
        default=True,
        help="Follow log output (default: true)",
    )
    p_log.add_argument(
        "--no-follow",
        action="store_false",
        dest="follow",
        help="Print last 50 lines only, do not follow",
    )

    # sync
    p_sync = sub.add_parser("sync", help="Run file sync")
    p_sync.add_argument("name", help="Sync config name")
    p_sync.add_argument(
        "--pull",
        action="store_true",
        help="Pull from remote (default: push)",
    )
    p_sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be transferred",
    )

    # init
    p_init = sub.add_parser("init", help="Generate starter config in current dir")
    p_init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing rdm.yaml",
    )

    # version
    sub.add_parser("version", help="Print version")

    # web (FastAPI sidecar / API server)
    p_web = sub.add_parser("web", help="Launch the web API server (desktop sidecar)")
    p_web.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    p_web.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")

    # mirror (with sub-subcommands)
    p_mirror = sub.add_parser("mirror", help="Smart code repo mirroring")
    p_mirror.add_argument("name", nargs="?", default=None, help="Mirror name (for quick pull)")
    p_mirror.add_argument("--dry-run", action="store_true")
    mirror_sub = p_mirror.add_subparsers(dest="mirror_action")

    p_mp = mirror_sub.add_parser("pull", help="Pull remote -> local")
    p_mp.add_argument("name", help="Mirror name")
    p_mp.add_argument("--dry-run", action="store_true")

    p_mpush = mirror_sub.add_parser("push", help="Push local -> remote")
    p_mpush.add_argument("name", help="Mirror name")
    p_mpush.add_argument("--dry-run", action="store_true")

    p_ms = mirror_sub.add_parser("status", help="Show what would change")
    p_ms.add_argument("name", help="Mirror name")

    p_mb = mirror_sub.add_parser("browse", help="Discover code repos on remote host")
    p_mb.add_argument("host", help="Host name from config")
    p_mb.add_argument("--path", default="~", help="Base path to search (default: ~)")
    p_mb.add_argument("--depth", type=int, default=3, help="Search depth (default: 3)")

    p_ma = mirror_sub.add_parser("add", help="Add a mirror to config")
    p_ma.add_argument("host", help="Host name from config")
    p_ma.add_argument("remote_path", help="Remote directory path")
    p_ma.add_argument("--name", dest="mirror_name", help="Mirror name (default: dir basename)")
    p_ma.add_argument("--local", default="", help="Local path (default: auto)")
    p_ma.add_argument("--no-auto-exclude", action="store_true", help="Disable smart exclusion")

    mirror_sub.add_parser("list", help="List configured mirrors")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    # No subcommand -> launch TUI
    if args.command is None:
        try:
            return _cmd_tui(args)
        except ConfigNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    handlers = {
        "up": _cmd_up,
        "down": _cmd_down,
        "status": _cmd_status,
        "tui": _cmd_tui,
        "log": _cmd_log,
        "sync": _cmd_sync,
        "init": _cmd_init,
        "version": _cmd_version,
        "web": _cmd_web,
        "mirror": _cmd_mirror,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    try:
        return handler(args)
    except ConfigNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
