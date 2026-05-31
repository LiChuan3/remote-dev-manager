"""Mirror routes: CRUD, pull/push/status, and ad-hoc file fetch."""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from rdm import config_writer, remote
from rdm.api.manager import ServiceManager
from rdm.api.schemas import FetchFileIn, MirrorIn
from rdm.config import MirrorConfig
from rdm.mirror import mirror_pull, mirror_push, mirror_status

router = APIRouter()


def _manager(request: Request) -> ServiceManager:
    return request.app.state.manager


def _mirror_dict(mr: MirrorConfig) -> dict:
    return {
        "name": mr.name,
        "host": mr.host_ref,
        "remote_path": mr.remote_path,
        "local_path": mr.local_path,
        "direction": mr.direction,
        "auto_exclude": mr.auto_exclude,
        "max_file_size": mr.max_file_size,
        "exclude": list(mr.exclude),
        "include": list(mr.include),
        "delete": mr.delete,
    }


def _find_mirror(mgr: ServiceManager, name: str) -> MirrorConfig:
    for mc in mgr.config.mirrors:
        if mc.name == name:
            # Resolve local_path default to <workspace>/mirrors/<name>.
            if not mc.local_path:
                resolved = str(mgr.config.workspace_path / "mirrors" / mc.name)
                return replace(mc, local_path=resolved)
            return mc
    raise HTTPException(status_code=404, detail=f"Mirror not found: {name}")


@router.get("/api/mirrors")
async def list_mirrors(request: Request) -> list[dict]:
    mgr = _manager(request)
    return [_mirror_dict(mc) for mc in mgr.config.mirrors]


@router.post("/api/mirrors")
async def add_mirror(request: Request, body: MirrorIn) -> dict:
    mgr = _manager(request)
    try:
        config_writer.add_mirror(
            str(mgr.config_path),
            name=body.name,
            host=body.host,
            remote_path=body.remote_path,
            local_path=body.local_path,
            direction=body.direction,
            auto_exclude=body.auto_exclude,
            max_file_size=body.max_file_size,
            exclude=list(body.exclude),
            include=list(body.include),
            delete=body.delete,
        )
        mgr.reload()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "name": body.name}


@router.delete("/api/mirrors/{name}")
async def delete_mirror(request: Request, name: str) -> dict:
    mgr = _manager(request)
    try:
        removed = config_writer.remove_mirror(str(mgr.config_path), name)
        mgr.reload()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": bool(removed), "name": name}


@router.post("/api/mirrors/{name}/pull")
async def pull_mirror(request: Request, name: str, dry_run: bool = False) -> dict:
    mgr = _manager(request)
    mc = _find_mirror(mgr, name)
    host = mgr.host(mc.host_ref)
    if host is None:
        raise HTTPException(status_code=404, detail=f"Unknown host: {mc.host_ref}")
    try:
        return await run_in_threadpool(mirror_pull, mc, host, dry_run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/mirrors/{name}/push")
async def push_mirror(request: Request, name: str, dry_run: bool = False) -> dict:
    mgr = _manager(request)
    mc = _find_mirror(mgr, name)
    host = mgr.host(mc.host_ref)
    if host is None:
        raise HTTPException(status_code=404, detail=f"Unknown host: {mc.host_ref}")
    try:
        return await run_in_threadpool(mirror_push, mc, host, dry_run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/mirrors/{name}/status")
async def status_mirror(request: Request, name: str) -> dict:
    mgr = _manager(request)
    mc = _find_mirror(mgr, name)
    host = mgr.host(mc.host_ref)
    if host is None:
        raise HTTPException(status_code=404, detail=f"Unknown host: {mc.host_ref}")
    try:
        return await run_in_threadpool(mirror_status, mc, host)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/fetch-file")
async def fetch_file(request: Request, body: FetchFileIn) -> dict:
    mgr = _manager(request)
    host = mgr.host(body.host)
    if host is None:
        raise HTTPException(status_code=404, detail=f"Unknown host: {body.host}")
    local_path = body.local_path
    if not local_path:
        remote_name = body.remote_path.rstrip("/").rsplit("/", 1)[-1] or "download"
        local_path = str(mgr.config.workspace_path / "fetched" / remote_name)
    try:
        return await run_in_threadpool(
            remote.fetch_file, host, body.remote_path, local_path
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
