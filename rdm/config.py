"""Configuration loading, parsing, and state persistence for rdm."""

from __future__ import annotations

import json
import os
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class HostConfig:
    name: str
    user: str
    host: str
    port: int = 22
    identity: str = ""


@dataclass
class ForwardRule:
    type: str = "local"
    local_port: int = 0
    remote_host: str = "127.0.0.1"
    remote_port: int = 0


@dataclass
class TunnelConfig:
    name: str
    host_ref: str
    proxy: str = "direct"
    forwards: list[ForwardRule] = field(default_factory=list)


@dataclass
class MountConfig:
    name: str
    host_ref: str
    remote_path: str = "/"
    mount_point: str = ""
    options: list[str] = field(default_factory=list)


@dataclass
class ReverseProxyConfig:
    name: str
    host_ref: str
    local_port: int = 7897
    remote_port: int = 7897


@dataclass
class SyncConfig:
    name: str
    host_ref: str
    local_path: str = "."
    remote_path: str = "~"
    mode: str = "push"
    exclude: list[str] = field(default_factory=list)


@dataclass
class MirrorConfig:
    name: str
    host_ref: str
    remote_path: str
    local_path: str = ""
    direction: str = "pull"
    auto_exclude: bool = True
    max_file_size: str = "10M"
    exclude: list[str] = field(default_factory=list)
    include: list[str] = field(default_factory=list)
    delete: bool = False


@dataclass
class DefaultsConfig:
    proxy: str = "direct"
    clash_port: int = 7897
    auto_restart: bool = True
    workspace: str = ""
    locale: str = "zh-CN"


@dataclass
class Config:
    defaults: DefaultsConfig
    hosts: dict[str, HostConfig]
    tunnels: list[TunnelConfig]
    mounts: list[MountConfig]
    reverse_proxies: list[ReverseProxyConfig]
    syncs: list[SyncConfig]
    mirrors: list[MirrorConfig] = field(default_factory=list)
    _config_path: Path | None = field(default=None, repr=False)

    @property
    def workspace_path(self) -> Path:
        """Return the effective workspace directory.

        Priority:
        1. defaults.workspace (if non-empty)
        2. Parent directory of the config file
        3. Current working directory as last resort
        """
        if self.defaults.workspace:
            return Path(_expand(self.defaults.workspace)).resolve()
        if self._config_path is not None:
            return self._config_path.parent.resolve()
        return Path.cwd()

    @property
    def logs_dir(self) -> Path:
        return self.workspace_path / ".rdm" / "logs"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _expand(p: str) -> str:
    """Expand ~ and environment variables in a path string."""
    return os.path.expandvars(os.path.expanduser(p))


def _user_config_dir() -> Path:
    """Return the platform-appropriate user config directory for rdm."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        return Path(base) / "rdm"
    # Linux / macOS follow XDG
    base = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(base) / "rdm"


# ---------------------------------------------------------------------------
# Config discovery
# ---------------------------------------------------------------------------

def find_config() -> Path | None:
    """Search for a config file in priority order.

    1. $RDM_CONFIG environment variable
    2. ./rdm.yaml in the current working directory
    3. Platform user config directory
    """
    # 1. Environment variable
    env_path = os.environ.get("RDM_CONFIG")
    if env_path:
        p = Path(_expand(env_path))
        if p.is_file():
            return p.resolve()

    # 2. Current directory
    local = Path.cwd() / "rdm.yaml"
    if local.is_file():
        return local.resolve()

    # 3. User config dir
    user_cfg = _user_config_dir() / "config.yaml"
    if user_cfg.is_file():
        return user_cfg.resolve()

    return None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_defaults(raw: dict[str, Any] | None) -> DefaultsConfig:
    if not raw:
        return DefaultsConfig()
    return DefaultsConfig(
        proxy=raw.get("proxy", "direct"),
        clash_port=int(raw.get("clash_port", 7897)),
        auto_restart=bool(raw.get("auto_restart", True)),
        workspace=str(raw.get("workspace", "")),
        locale=str(raw.get("locale", "zh-CN")),
    )


def _parse_hosts(raw: dict[str, Any] | None) -> dict[str, HostConfig]:
    if not raw:
        return {}
    hosts: dict[str, HostConfig] = {}
    for name, data in raw.items():
        hosts[name] = HostConfig(
            name=name,
            user=str(data.get("user", "root")),
            host=str(data.get("host", "")),
            port=int(data.get("port", 22)),
            identity=_expand(str(data.get("identity", ""))),
        )
    return hosts


def _parse_forwards(raw_list: list[dict[str, Any]] | None) -> list[ForwardRule]:
    if not raw_list:
        return []
    rules: list[ForwardRule] = []
    for item in raw_list:
        rules.append(ForwardRule(
            type=str(item.get("type", "local")),
            local_port=int(item.get("local_port", 0)),
            remote_host=str(item.get("remote_host", "127.0.0.1")),
            remote_port=int(item.get("remote_port", 0)),
        ))
    return rules


def _parse_tunnels(
    raw_list: list[dict[str, Any]] | None,
    default_proxy: str,
) -> list[TunnelConfig]:
    if not raw_list:
        return []
    tunnels: list[TunnelConfig] = []
    for item in raw_list:
        tunnels.append(TunnelConfig(
            name=str(item["name"]),
            host_ref=str(item["host"]),
            proxy=str(item.get("proxy", default_proxy)),
            forwards=_parse_forwards(item.get("forwards")),
        ))
    return tunnels


def _parse_mounts(raw_list: list[dict[str, Any]] | None) -> list[MountConfig]:
    if not raw_list:
        return []
    mounts: list[MountConfig] = []
    for item in raw_list:
        mounts.append(MountConfig(
            name=str(item["name"]),
            host_ref=str(item["host"]),
            remote_path=str(item.get("remote_path", "/")),
            mount_point=_expand(str(item.get("mount_point", ""))),
            options=list(item.get("options", [])),
        ))
    return mounts


def _parse_reverse_proxies(
    raw_list: list[dict[str, Any]] | None,
) -> list[ReverseProxyConfig]:
    if not raw_list:
        return []
    proxies: list[ReverseProxyConfig] = []
    for item in raw_list:
        proxies.append(ReverseProxyConfig(
            name=str(item["name"]),
            host_ref=str(item["host"]),
            local_port=int(item.get("local_port", 7897)),
            remote_port=int(item.get("remote_port", 7897)),
        ))
    return proxies


def _parse_syncs(raw_list: list[dict[str, Any]] | None) -> list[SyncConfig]:
    if not raw_list:
        return []
    syncs: list[SyncConfig] = []
    for item in raw_list:
        syncs.append(SyncConfig(
            name=str(item["name"]),
            host_ref=str(item["host"]),
            local_path=str(item.get("local_path", ".")),
            remote_path=str(item.get("remote_path", "~")),
            mode=str(item.get("mode", "push")),
            exclude=list(item.get("exclude", [])),
        ))
    return syncs


def _parse_mirrors(raw_list: list[dict[str, Any]] | None) -> list[MirrorConfig]:
    if not raw_list:
        return []
    mirrors: list[MirrorConfig] = []
    for item in raw_list:
        mirrors.append(MirrorConfig(
            name=str(item["name"]),
            host_ref=str(item["host"]),
            remote_path=str(item.get("remote_path", "")),
            local_path=_expand(str(item.get("local_path", ""))),
            direction=str(item.get("direction", "pull")),
            auto_exclude=bool(item.get("auto_exclude", True)),
            max_file_size=str(item.get("max_file_size", "10M")),
            exclude=list(item.get("exclude", [])),
            include=list(item.get("include", [])),
            delete=bool(item.get("delete", False)),
        ))
    return mirrors


# ---------------------------------------------------------------------------
# Main loader
# ---------------------------------------------------------------------------

def load_config(path: str | Path | None = None) -> Config:
    """Load and parse the rdm configuration file.

    Args:
        path: Explicit config file path.  If *None*, :func:`find_config` is
              used to locate one automatically.

    Returns:
        A fully-resolved :class:`Config` instance.

    Raises:
        FileNotFoundError: No config file found.
        ValueError: Config file is malformed or references unknown hosts.
    """
    if path is not None:
        config_path = Path(_expand(str(path))).resolve()
        if not config_path.is_file():
            raise FileNotFoundError(f"Config file not found: {config_path}")
    else:
        config_path = find_config()
        if config_path is None:
            raise FileNotFoundError(
                "No rdm config file found.\n"
                "Searched:\n"
                "  1. $RDM_CONFIG environment variable\n"
                "  2. ./rdm.yaml (current directory)\n"
                f"  3. {_user_config_dir() / 'config.yaml'}\n"
                "\n"
                "Create one with:  rdm init"
            )

    with open(config_path, "r", encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    defaults = _parse_defaults(raw.get("defaults"))
    hosts = _parse_hosts(raw.get("hosts"))
    tunnels = _parse_tunnels(raw.get("tunnels"), defaults.proxy)
    mounts = _parse_mounts(raw.get("mounts"))
    reverse_proxies = _parse_reverse_proxies(raw.get("reverse_proxies"))
    syncs = _parse_syncs(raw.get("syncs"))
    mirrors = _parse_mirrors(raw.get("mirrors"))

    # Validate host references
    all_refs: list[tuple[str, str]] = []
    for t in tunnels:
        all_refs.append((f"tunnel:{t.name}", t.host_ref))
    for m in mounts:
        all_refs.append((f"mount:{m.name}", m.host_ref))
    for rp in reverse_proxies:
        all_refs.append((f"reverse_proxy:{rp.name}", rp.host_ref))
    for s in syncs:
        all_refs.append((f"sync:{s.name}", s.host_ref))
    for mr in mirrors:
        all_refs.append((f"mirror:{mr.name}", mr.host_ref))

    for label, ref in all_refs:
        if ref not in hosts:
            raise ValueError(
                f"{label} references unknown host '{ref}'. "
                f"Known hosts: {', '.join(hosts.keys()) or '(none)'}"
            )

    return Config(
        defaults=defaults,
        hosts=hosts,
        tunnels=tunnels,
        mounts=mounts,
        reverse_proxies=reverse_proxies,
        syncs=syncs,
        mirrors=mirrors,
        _config_path=config_path,
    )


# ---------------------------------------------------------------------------
# Runtime state persistence
# ---------------------------------------------------------------------------

def _state_path(workspace: Path) -> Path:
    return workspace / ".rdm" / "state.json"


def load_state(workspace: Path) -> dict[str, Any]:
    """Load runtime state from ``<workspace>/.rdm/state.json``.

    Returns an empty dict if the file does not exist or is corrupt.
    """
    sp = _state_path(workspace)
    if not sp.is_file():
        return {}
    try:
        with open(sp, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(workspace: Path, data: dict[str, Any]) -> None:
    """Persist runtime state to ``<workspace>/.rdm/state.json``."""
    sp = _state_path(workspace)
    sp.parent.mkdir(parents=True, exist_ok=True)
    tmp = sp.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    tmp.replace(sp)


def set_service_proxy(
    workspace: Path,
    kind: str,
    name: str,
    proxy: str,
) -> None:
    """Set a per-service proxy override in runtime state.

    Args:
        workspace: Workspace root directory.
        kind: Service kind (e.g. ``"tunnel"``, ``"mount"``).
        name: Service name.
        proxy: Proxy mode string (e.g. ``"direct"``, ``"clash"``).
    """
    state = load_state(workspace)
    overrides = state.setdefault("proxy_overrides", {})
    key = f"{kind}:{name}"
    overrides[key] = proxy
    save_state(workspace, state)


def get_service_proxy(
    workspace: Path,
    kind: str,
    name: str,
) -> str | None:
    """Get a per-service proxy override, or *None* if not set."""
    state = load_state(workspace)
    overrides = state.get("proxy_overrides", {})
    return overrides.get(f"{kind}:{name}")
