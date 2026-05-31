"""Host management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from rdm import config_writer, mirror, remote
from rdm.api.manager import ServiceManager
from rdm.api.schemas import BrowseIn, HostIn, HostUpdate

router = APIRouter()


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


@router.get("/api/hosts")
async def list_hosts(request: Request) -> list[dict]:
    mgr = _manager(request)
    return [_host_dict(h) for h in mgr.config.hosts.values()]


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
