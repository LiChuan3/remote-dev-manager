"""Host management routes."""

from __future__ import annotations

import fnmatch
import glob
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from rdm import config_writer, mirror, remote
from rdm.api.manager import ServiceManager
from rdm.api.schemas import BrowseIn, HostIn, HostUpdate, SshConfigHost

router = APIRouter()

_SSH_IMPORT_OPTIONS = {
    "hostname",
    "user",
    "port",
    "identityfile",
    "proxyjump",
    "proxycommand",
}


@dataclass
class _SshHostBlock:
    patterns: list[str]
    options: dict[str, str] = field(default_factory=dict)
    source: str = ""
    line: int = 0


def _manager(request: Request) -> ServiceManager:
    return request.app.state.manager


def _host_dict(h) -> dict:
    return {
        "name": h.name,
        "user": h.user,
        "host": h.host,
        "port": h.port,
        "identity": h.identity,
    }


def _host_references(mgr: ServiceManager, name: str) -> list[str]:
    """Return config entries that still point at a host."""
    cfg = mgr.config
    refs: list[str] = []
    refs.extend(f"tunnel:{x.name}" for x in cfg.tunnels if x.host_ref == name)
    refs.extend(f"mount:{x.name}" for x in cfg.mounts if x.host_ref == name)
    refs.extend(
        f"reverse_proxy:{x.name}" for x in cfg.reverse_proxies if x.host_ref == name
    )
    refs.extend(f"sync:{x.name}" for x in cfg.syncs if x.host_ref == name)
    refs.extend(f"mirror:{x.name}" for x in cfg.mirrors if x.host_ref == name)
    return refs


def _default_ssh_user() -> str:
    return os.environ.get("USER") or os.environ.get("USERNAME") or ""


def _default_ssh_config_path() -> Path:
    """Return the most likely per-user OpenSSH config path on this machine."""
    candidates: list[Path] = []
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        candidates.append(Path(userprofile) / ".ssh" / "config")
    home = os.environ.get("HOME")
    if home:
        candidates.append(Path(home) / ".ssh" / "config")
    home_drive = os.environ.get("HOMEDRIVE")
    home_path = os.environ.get("HOMEPATH")
    if home_drive and home_path:
        candidates.append(Path(home_drive + home_path) / ".ssh" / "config")
    candidates.append(Path.home() / ".ssh" / "config")

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            return resolved
    return candidates[0].expanduser().resolve(strict=False)


def _strip_inline_comment(line: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for idx, ch in enumerate(line):
        if ch == "\\" and not escaped:
            escaped = True
            continue
        if ch == "'" and not in_double and not escaped:
            in_single = not in_single
        elif ch == '"' and not in_single and not escaped:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:idx]
        escaped = False
    return line


def _clean_ssh_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _split_ssh_words(value: str) -> list[str]:
    return [_clean_ssh_value(part) for part in value.split() if part.strip()]


def _read_ssh_directive(line: str) -> Optional[tuple[str, str]]:
    line = _strip_inline_comment(line).strip().lstrip("\ufeff")
    if not line:
        return None
    first = line.split(None, 1)[0]
    if "=" in first:
        key, value = line.split("=", 1)
    else:
        parts = line.split(None, 1)
        if len(parts) == 1:
            return (parts[0].lower(), "")
        key, value = parts
    return (key.strip().lower(), _clean_ssh_value(value))


def _include_paths(patterns: str, base_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for pattern in _split_ssh_words(patterns):
        expanded = os.path.expandvars(os.path.expanduser(pattern))
        candidate = Path(expanded)
        if not candidate.is_absolute():
            candidate = base_dir / candidate
        matches = sorted(glob.glob(str(candidate)))
        paths.extend(Path(match) for match in matches)
    return paths


def _read_ssh_blocks(path: Path, seen_files: set[Path]) -> list[_SshHostBlock]:
    resolved = path.expanduser().resolve(strict=False)
    if resolved in seen_files or not resolved.is_file():
        return []
    seen_files.add(resolved)

    blocks: list[_SshHostBlock] = []
    current: Optional[_SshHostBlock] = None
    with open(resolved, "r", encoding="utf-8", errors="replace") as fh:
        for line_no, raw_line in enumerate(fh, start=1):
            directive = _read_ssh_directive(raw_line)
            if directive is None:
                continue
            key, value = directive

            if key == "include":
                for include_path in _include_paths(value, resolved.parent):
                    blocks.extend(_read_ssh_blocks(include_path, seen_files))
                continue

            if key == "match":
                current = None
                continue

            if key == "host":
                current = _SshHostBlock(
                    patterns=_split_ssh_words(value),
                    source=str(resolved),
                    line=line_no,
                )
                blocks.append(current)
                continue

            if current is not None and key in _SSH_IMPORT_OPTIONS:
                current.options.setdefault(key, value)

    return blocks


def _is_concrete_ssh_host(pattern: str) -> bool:
    return bool(pattern) and not pattern.startswith("!") and not any(
        ch in pattern for ch in "*?"
    )


def _matches_ssh_patterns(patterns: list[str], alias: str) -> bool:
    matched = False
    for pattern in patterns:
        if pattern.startswith("!"):
            if fnmatch.fnmatchcase(alias, pattern[1:]):
                return False
            continue
        if fnmatch.fnmatchcase(alias, pattern):
            matched = True
    return matched


def _parse_ssh_port(value: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return 22
    return port if 0 < port < 65536 else 22


def _ssh_config_hosts(path: Path) -> list[SshConfigHost]:
    blocks = _read_ssh_blocks(path, set())
    aliases: list[tuple[str, _SshHostBlock]] = []
    seen_aliases: set[str] = set()

    for block in blocks:
        for pattern in block.patterns:
            if not _is_concrete_ssh_host(pattern) or pattern in seen_aliases:
                continue
            seen_aliases.add(pattern)
            aliases.append((pattern, block))

    hosts: list[SshConfigHost] = []
    for alias, source_block in aliases:
        options: dict[str, str] = {}
        for block in blocks:
            if _matches_ssh_patterns(block.patterns, alias):
                for key, value in block.options.items():
                    options.setdefault(key, value)

        hostname = options.get("hostname", alias)
        user = options.get("user") or _default_ssh_user()
        hosts.append(
            SshConfigHost(
                name=alias,
                user=user,
                # Store the SSH alias as the connection host so OpenSSH keeps
                # applying ProxyJump, ProxyCommand and other local config.
                host=alias,
                hostname=hostname,
                port=_parse_ssh_port(options.get("port", "22")),
                identity=options.get("identityfile", ""),
                proxy_jump=options.get("proxyjump", ""),
                proxy_command=options.get("proxycommand", ""),
                source=f"{source_block.source}:{source_block.line}",
            )
        )
    return hosts


@router.get("/api/hosts")
async def list_hosts(request: Request) -> list[dict]:
    mgr = _manager(request)
    return [_host_dict(h) for h in mgr.config.hosts.values()]


@router.get("/api/hosts/ssh-config")
async def list_ssh_config_hosts(path: Optional[str] = None) -> list[SshConfigHost]:
    config_path = (
        Path(os.path.expandvars(os.path.expanduser(path)))
        if path
        else _default_ssh_config_path()
    )
    try:
        return _ssh_config_hosts(config_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/hosts")
async def create_host(request: Request, body: HostIn) -> dict:
    mgr = _manager(request)
    try:
        config_writer.add_host(
            str(mgr.config_path),
            body.name,
            user=body.user,
            host=body.host,
            port=body.port,
            identity=body.identity,
        )
        mgr.reload()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    h = mgr.host(body.name)
    if h is None:
        raise HTTPException(status_code=500, detail="Host not created")
    return _host_dict(h)


@router.put("/api/hosts/{name}")
async def update_host(request: Request, name: str, body: HostUpdate) -> dict:
    mgr = _manager(request)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        config_writer.update_host(str(mgr.config_path), name, **fields)
        mgr.reload()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    h = mgr.host(name)
    if h is None:
        raise HTTPException(status_code=404, detail=f"Unknown host: {name}")
    return _host_dict(h)


@router.delete("/api/hosts/{name}")
async def delete_host(request: Request, name: str) -> dict:
    mgr = _manager(request)
    refs = _host_references(mgr, name)
    if refs:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Host '{name}' is still used by: {', '.join(refs)}. "
                "Remove those entries first."
            ),
        )
    try:
        removed = config_writer.remove_host(str(mgr.config_path), name)
        mgr.reload()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": bool(removed), "name": name}


@router.post("/api/hosts/{name}/test")
async def test_host(request: Request, name: str) -> dict:
    mgr = _manager(request)
    host = mgr.host(name)
    if host is None:
        raise HTTPException(status_code=404, detail=f"Unknown host: {name}")
    try:
        return await run_in_threadpool(remote.test_connection, host)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/hosts/{name}/browse")
async def browse_host(request: Request, name: str, body: BrowseIn) -> dict:
    mgr = _manager(request)
    host = mgr.host(name)
    if host is None:
        raise HTTPException(status_code=404, detail=f"Unknown host: {name}")
    try:
        repos = await run_in_threadpool(
            mirror.list_remote_dirs, host, body.path, body.depth
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return repos
