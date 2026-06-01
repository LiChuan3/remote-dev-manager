"""Host management routes."""

from __future__ import annotations

import fnmatch
import glob
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from rdm import config_writer, mirror, remote
from rdm.api.manager import ServiceManager
from rdm.api.schemas import BrowseIn, HostIn, HostUpdate, SshConfigHost, SshConfigHostIn

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
    end_line: int = 0


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
    last_line = 0
    with open(resolved, "r", encoding="utf-8", errors="replace") as fh:
        for line_no, raw_line in enumerate(fh, start=1):
            last_line = line_no
            directive = _read_ssh_directive(raw_line)
            if directive is None:
                continue
            key, value = directive

            if key == "include":
                for include_path in _include_paths(value, resolved.parent):
                    blocks.extend(_read_ssh_blocks(include_path, seen_files))
                continue

            if key == "match":
                if current is not None:
                    current.end_line = line_no - 1
                current = None
                continue

            if key == "host":
                if current is not None:
                    current.end_line = line_no - 1
                current = _SshHostBlock(
                    patterns=_split_ssh_words(value),
                    source=str(resolved),
                    line=line_no,
                )
                blocks.append(current)
                continue

            if current is not None and key in _SSH_IMPORT_OPTIONS:
                current.options.setdefault(key, value)

    if current is not None:
        current.end_line = last_line
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


def _source_file(source: str) -> str:
    if source.endswith(":0"):
        return source[:-2]
    path, sep, line = source.rpartition(":")
    return path if sep and line.isdigit() else source


def _ssh_config_hosts(path: Path) -> list[SshConfigHost]:
    root_path = path.expanduser().resolve(strict=False)
    root_source = str(root_path)
    blocks = _read_ssh_blocks(root_path, set())
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
                editable=(
                    source_block.source == root_source
                    and source_block.patterns == [alias]
                ),
            )
        )
    return hosts


def _normalise_ssh_config_body(body: SshConfigHostIn) -> dict[str, Any]:
    data = body.model_dump()
    data = {
        key: (value.strip() if isinstance(value, str) else value)
        for key, value in data.items()
    }
    name = data.get("name") or ""
    if not name:
        raise ValueError("Host 别名不能为空。")
    if any(ch.isspace() for ch in name) or any(ch in name for ch in "*?!"):
        raise ValueError("Host 别名不能包含空格、通配符或 !。")

    for key in ("hostname", "user", "identity", "proxy_jump", "proxy_command"):
        value = data.get(key) or ""
        if "\n" in value or "\r" in value:
            raise ValueError(f"{key} 不能包含换行。")

    port = _parse_ssh_port(str(data.get("port", 22)))
    data["port"] = port

    if data.get("proxy_jump") and data.get("proxy_command"):
        raise ValueError("ProxyJump 和 ProxyCommand 只能填写一个。")
    return data


def _render_ssh_host_block(body: SshConfigHostIn) -> str:
    data = _normalise_ssh_config_body(body)
    lines = [f"Host {data['name']}"]
    if data["hostname"]:
        lines.append(f"  HostName {data['hostname']}")
    if data["user"]:
        lines.append(f"  User {data['user']}")
    if data["port"] != 22:
        lines.append(f"  Port {data['port']}")
    if data["identity"]:
        lines.append(f"  IdentityFile {data['identity']}")
    if data["proxy_jump"]:
        lines.append(f"  ProxyJump {data['proxy_jump']}")
    if data["proxy_command"]:
        lines.append(f"  ProxyCommand {data['proxy_command']}")
    return "\n".join(lines) + "\n"


def _read_ssh_config_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _write_ssh_config_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _find_ssh_config_block(path: Path, name: str) -> _SshHostBlock | None:
    root_path = path.expanduser().resolve(strict=False)
    for block in _read_ssh_blocks(root_path, set()):
        if name in block.patterns:
            return block
    return None


def _ensure_editable_block(path: Path, name: str) -> _SshHostBlock:
    root_path = path.expanduser().resolve(strict=False)
    blocks = [
        block
        for block in _read_ssh_blocks(root_path, set())
        if name in block.patterns
    ]
    block = next((b for b in blocks if b.source == str(root_path)), None)
    if block is None and blocks:
        block = blocks[0]
    if block is None:
        raise KeyError(f"Host '{name}' 不存在。")
    if block.source != str(root_path):
        raise ValueError("该 Host 来自 Include 文件，当前只直接修改 ~/.ssh/config。")
    if block.patterns != [name]:
        raise ValueError("该 Host 块包含多个别名或模式，当前不支持图形化修改。")
    return block


def _ssh_config_create(path: Path, body: SshConfigHostIn) -> SshConfigHost:
    root_path = path.expanduser().resolve(strict=False)
    data = _normalise_ssh_config_body(body)
    existing = _find_ssh_config_block(root_path, data["name"])
    if existing is not None:
        raise ValueError(f"Host '{data['name']}' 已存在。")

    text = _read_ssh_config_text(root_path)
    if text and not text.endswith("\n"):
        text += "\n"
    if text and not text.endswith("\n\n"):
        text += "\n"
    text += _render_ssh_host_block(body)
    _write_ssh_config_text(root_path, text)
    return _ssh_config_get(root_path, data["name"])


def _ssh_config_update(path: Path, name: str, body: SshConfigHostIn) -> SshConfigHost:
    root_path = path.expanduser().resolve(strict=False)
    data = _normalise_ssh_config_body(body)
    block = _ensure_editable_block(root_path, name)
    if data["name"] != name:
        existing = _find_ssh_config_block(root_path, data["name"])
        if existing is not None:
            raise ValueError(f"Host '{data['name']}' 已存在。")

    lines = _read_ssh_config_text(root_path).splitlines(keepends=True)
    start = block.line - 1
    end = block.end_line if block.end_line else block.line
    lines[start:end] = _render_ssh_host_block(body).splitlines(keepends=True)
    _write_ssh_config_text(root_path, "".join(lines))
    return _ssh_config_get(root_path, data["name"])


def _ssh_config_delete(path: Path, name: str) -> dict[str, Any]:
    root_path = path.expanduser().resolve(strict=False)
    block = _ensure_editable_block(root_path, name)
    lines = _read_ssh_config_text(root_path).splitlines(keepends=True)
    start = block.line - 1
    end = block.end_line if block.end_line else block.line
    if end < len(lines) and lines[end].strip() == "":
        end += 1
    del lines[start:end]
    _write_ssh_config_text(root_path, "".join(lines))
    return {"ok": True, "name": name}


def _ssh_config_get(path: Path, name: str) -> SshConfigHost:
    for item in _ssh_config_hosts(path):
        if item.name == name:
            return item
    raise KeyError(f"Host '{name}' 不存在。")


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


@router.post("/api/hosts/ssh-config")
async def create_ssh_config_host(body: SshConfigHostIn) -> SshConfigHost:
    try:
        return await run_in_threadpool(
            _ssh_config_create, _default_ssh_config_path(), body
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/hosts/ssh-config/{name}")
async def update_ssh_config_host(name: str, body: SshConfigHostIn) -> SshConfigHost:
    try:
        return await run_in_threadpool(
            _ssh_config_update, _default_ssh_config_path(), name, body
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/hosts/ssh-config/{name}")
async def delete_ssh_config_host(name: str) -> dict:
    try:
        return await run_in_threadpool(
            _ssh_config_delete, _default_ssh_config_path(), name
        )
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
