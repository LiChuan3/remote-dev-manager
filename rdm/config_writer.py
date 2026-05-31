"""Safe YAML config mutation for rdm — add/update/remove hosts and services."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

# Sections that are stored as lists of named objects.
_LIST_SECTIONS = ("tunnels", "mounts", "reverse_proxies", "syncs", "mirrors")


# ---------------------------------------------------------------------------
# Low-level I/O
# ---------------------------------------------------------------------------

def load_raw(config_path: str | Path) -> dict[str, Any]:
    """Read a YAML config file and return it as a plain dict.

    Returns an empty dict if the file is missing or empty.

    Raises:
        ValueError: The file exists but does not parse as a YAML mapping.
    """
    path = Path(config_path)
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse YAML config {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(
            f"Config {path} must be a YAML mapping at the top level, "
            f"got {type(data).__name__}."
        )
    return data


def save_raw(config_path: str | Path, data: dict[str, Any]) -> None:
    """Atomically write ``data`` to ``config_path`` as YAML.

    Writes to a temporary sibling file then ``os.replace`` for atomicity.
    Preserves key order and unicode characters.
    """
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump(
            data,
            fh,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
    os.replace(tmp, path)


def _ensure_list(data: dict[str, Any], key: str) -> list[Any]:
    """Return ``data[key]`` as a list, creating an empty list if needed."""
    value = data.get(key)
    if not isinstance(value, list):
        value = []
        data[key] = value
    return value


def _ensure_map(data: dict[str, Any], key: str) -> dict[str, Any]:
    """Return ``data[key]`` as a dict, creating an empty dict if needed."""
    value = data.get(key)
    if not isinstance(value, dict):
        value = {}
        data[key] = value
    return value


# ---------------------------------------------------------------------------
# Hosts (map-based)
# ---------------------------------------------------------------------------

def add_host(
    config_path: str | Path,
    name: str,
    user: str,
    host: str,
    port: int = 22,
    identity: str = "",
) -> None:
    """Add a new host entry to the ``hosts`` map.

    Raises:
        ValueError: A host with ``name`` already exists.
    """
    data = load_raw(config_path)
    hosts = _ensure_map(data, "hosts")
    if name in hosts:
        raise ValueError(f"Host '{name}' already exists.")
    entry: dict[str, Any] = {"user": user, "host": host, "port": port}
    if identity:
        entry["identity"] = identity
    hosts[name] = entry
    save_raw(config_path, data)
    log.info("Added host '%s'", name)


def update_host(config_path: str | Path, name: str, **fields: Any) -> None:
    """Merge ``fields`` into an existing host entry.

    Raises:
        KeyError: No host named ``name`` exists.
    """
    data = load_raw(config_path)
    hosts = _ensure_map(data, "hosts")
    if name not in hosts:
        raise KeyError(f"Host '{name}' does not exist.")
    existing = hosts[name]
    if not isinstance(existing, dict):
        existing = {}
    existing.update(fields)
    hosts[name] = existing
    save_raw(config_path, data)
    log.info("Updated host '%s'", name)


def upsert_host(config_path: str | Path, name: str, **fields: Any) -> None:
    """Add a host if missing, otherwise merge ``fields`` into the existing one."""
    data = load_raw(config_path)
    hosts = _ensure_map(data, "hosts")
    existing = hosts.get(name)
    if isinstance(existing, dict):
        existing.update(fields)
        hosts[name] = existing
    else:
        hosts[name] = dict(fields)
    save_raw(config_path, data)
    log.info("Upserted host '%s'", name)


def remove_host(config_path: str | Path, name: str) -> bool:
    """Delete a host by name.

    Returns:
        True if the host existed and was removed, False otherwise.
    """
    data = load_raw(config_path)
    hosts = _ensure_map(data, "hosts")
    if name not in hosts:
        return False
    del hosts[name]
    save_raw(config_path, data)
    log.info("Removed host '%s'", name)
    return True


# ---------------------------------------------------------------------------
# Generic list-section helpers
# ---------------------------------------------------------------------------

def _check_section(section: str) -> None:
    if section not in _LIST_SECTIONS:
        raise ValueError(
            f"Unknown list section '{section}'. "
            f"Valid sections: {', '.join(_LIST_SECTIONS)}."
        )


def upsert_list_item(
    config_path: str | Path,
    section: str,
    entry: dict[str, Any],
) -> None:
    """Insert or replace a named item in a list-based section.

    If an item with the same ``name`` already exists it is replaced in place;
    otherwise the entry is appended.

    Raises:
        ValueError: ``section`` is not a known list section, or ``entry`` has
            no ``name`` field.
    """
    _check_section(section)
    name = entry.get("name")
    if not name:
        raise ValueError("List item entry must have a non-empty 'name' field.")
    data = load_raw(config_path)
    items = _ensure_list(data, section)
    for idx, existing in enumerate(items):
        if isinstance(existing, dict) and existing.get("name") == name:
            items[idx] = entry
            break
    else:
        items.append(entry)
    save_raw(config_path, data)
    log.info("Upserted %s item '%s'", section, name)


def remove_list_item(config_path: str | Path, section: str, name: str) -> bool:
    """Remove a named item from a list-based section.

    Returns:
        True if an item was removed, False otherwise.
    """
    _check_section(section)
    data = load_raw(config_path)
    items = _ensure_list(data, section)
    new_items = [
        it for it in items
        if not (isinstance(it, dict) and it.get("name") == name)
    ]
    if len(new_items) == len(items):
        return False
    data[section] = new_items
    save_raw(config_path, data)
    log.info("Removed %s item '%s'", section, name)
    return True


def get_list_item(
    config_path: str | Path,
    section: str,
    name: str,
) -> dict[str, Any] | None:
    """Return a named item from a list-based section, or None if absent."""
    _check_section(section)
    data = load_raw(config_path)
    items = data.get(section)
    if not isinstance(items, list):
        return None
    for it in items:
        if isinstance(it, dict) and it.get("name") == name:
            return it
    return None


# ---------------------------------------------------------------------------
# Typed convenience wrappers
# ---------------------------------------------------------------------------

def add_tunnel(
    config_path: str | Path,
    name: str,
    host: str,
    forwards: list[dict[str, Any]] | None = None,
    proxy: str | None = None,
) -> None:
    """Add or replace a tunnel entry.

    Args:
        forwards: List of forward rules, each a dict with optional keys
            ``type``, ``local_port``, ``remote_host``, ``remote_port``.
        proxy: Optional proxy mode override; omitted when None.
    """
    entry: dict[str, Any] = {"name": name, "host": host}
    if proxy is not None:
        entry["proxy"] = proxy
    if forwards is not None:
        clean_forwards: list[dict[str, Any]] = []
        for fwd in forwards:
            rule: dict[str, Any] = {}
            for key in ("type", "local_port", "remote_host", "remote_port"):
                if key in fwd and fwd[key] is not None:
                    rule[key] = fwd[key]
            clean_forwards.append(rule)
        entry["forwards"] = clean_forwards
    upsert_list_item(config_path, "tunnels", entry)


def add_mount(
    config_path: str | Path,
    name: str,
    host: str,
    remote_path: str,
    mount_point: str = "",
    options: list[str] | None = None,
) -> None:
    """Add or replace a mount entry."""
    entry: dict[str, Any] = {
        "name": name,
        "host": host,
        "remote_path": remote_path,
    }
    if mount_point:
        entry["mount_point"] = mount_point
    if options:
        entry["options"] = list(options)
    upsert_list_item(config_path, "mounts", entry)


def add_reverse_proxy(
    config_path: str | Path,
    name: str,
    host: str,
    local_port: int = 7897,
    remote_port: int = 7897,
) -> None:
    """Add or replace a reverse proxy entry."""
    entry: dict[str, Any] = {
        "name": name,
        "host": host,
        "local_port": local_port,
        "remote_port": remote_port,
    }
    upsert_list_item(config_path, "reverse_proxies", entry)


def add_mirror(
    config_path: str | Path,
    name: str,
    host: str,
    remote_path: str,
    local_path: str = "",
    direction: str = "pull",
    auto_exclude: bool = True,
    max_file_size: str = "10M",
    exclude: list[str] | None = None,
    include: list[str] | None = None,
    delete: bool = False,
) -> None:
    """Add or replace a mirror entry."""
    entry: dict[str, Any] = {
        "name": name,
        "host": host,
        "remote_path": remote_path,
        "direction": direction,
        "auto_exclude": auto_exclude,
        "max_file_size": max_file_size,
    }
    if local_path:
        entry["local_path"] = local_path
    if exclude:
        entry["exclude"] = list(exclude)
    if include:
        entry["include"] = list(include)
    if delete:
        entry["delete"] = delete
    upsert_list_item(config_path, "mirrors", entry)


def remove_tunnel(config_path: str | Path, name: str) -> bool:
    """Remove a tunnel by name. Returns True if removed."""
    return remove_list_item(config_path, "tunnels", name)


def remove_mount(config_path: str | Path, name: str) -> bool:
    """Remove a mount by name. Returns True if removed."""
    return remove_list_item(config_path, "mounts", name)


def remove_reverse_proxy(config_path: str | Path, name: str) -> bool:
    """Remove a reverse proxy by name. Returns True if removed."""
    return remove_list_item(config_path, "reverse_proxies", name)


def remove_mirror(config_path: str | Path, name: str) -> bool:
    """Remove a mirror by name. Returns True if removed."""
    return remove_list_item(config_path, "mirrors", name)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def set_default(config_path: str | Path, key: str, value: Any) -> None:
    """Set a value under the ``defaults`` section.

    Recognised keys: proxy, clash_port, auto_restart, workspace, locale.
    """
    data = load_raw(config_path)
    data.setdefault("defaults", {})[key] = value
    save_raw(config_path, data)
    log.info("Set default '%s'", key)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(config_path: str | Path) -> list[str]:
    """Validate the config using the real rdm loader.

    Returns:
        An empty list if the config loads cleanly, otherwise a single-element
        list containing the error message. Useful for surfacing schema errors
        to an API after a mutation.
    """
    from rdm.config import load_config  # lazy import to avoid cycles

    try:
        load_config(config_path)
    except Exception as exc:  # noqa: BLE001 - surface any loader error
        return [str(exc)]
    return []
