"""Service lifecycle and definition CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from rdm import config_writer
from rdm.api.manager import ServiceManager
from rdm.api.schemas import (
    MountDiagnostics,
    MountInstallResult,
    MountIn,
    ProxyPatch,
    ReverseProxyIn,
    TunnelIn,
)
from rdm.mount import check_sshfs_installation, launch_sshfs_dependency_installer

router = APIRouter()

_VALID_KINDS = {"tunnel", "mount", "reverse_proxy"}


def _manager(request: Request) -> ServiceManager:
    return request.app.state.manager


async def _stop_before_delete(mgr: ServiceManager, kind: str, name: str) -> None:
    """Best-effort stop so removing a definition does not leave a process behind."""
    if mgr.get(kind, name) is not None:
        await run_in_threadpool(mgr.stop, kind, name)


@router.get("/api/services")
async def list_services(request: Request) -> list[dict]:
    return _manager(request).snapshot()


@router.get("/api/mounts/diagnostics")
async def mount_diagnostics() -> MountDiagnostics:
    return MountDiagnostics(**await run_in_threadpool(check_sshfs_installation))


@router.post("/api/mounts/install-dependencies")
async def install_mount_dependencies() -> MountInstallResult:
    return MountInstallResult(
        **await run_in_threadpool(launch_sshfs_dependency_installer)
    )


@router.post("/api/services/{kind}/{name}/start")
async def start_service(request: Request, kind: str, name: str) -> dict:
    mgr = _manager(request)
    if mgr.get(kind, name) is None:
        raise HTTPException(status_code=404, detail=f"Service not found: {kind}/{name}")
    try:
        info = await run_in_threadpool(mgr.start, kind, name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if info is None:
        raise HTTPException(status_code=404, detail=f"Service not found: {kind}/{name}")
    return info


@router.post("/api/services/{kind}/{name}/stop")
async def stop_service(request: Request, kind: str, name: str) -> dict:
    mgr = _manager(request)
    if mgr.get(kind, name) is None:
        raise HTTPException(status_code=404, detail=f"Service not found: {kind}/{name}")
    try:
        info = await run_in_threadpool(mgr.stop, kind, name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if info is None:
        raise HTTPException(status_code=404, detail=f"Service not found: {kind}/{name}")
    return info


@router.post("/api/services/{kind}/{name}/restart")
async def restart_service(request: Request, kind: str, name: str) -> dict:
    mgr = _manager(request)
    if mgr.get(kind, name) is None:
        raise HTTPException(status_code=404, detail=f"Service not found: {kind}/{name}")
    try:
        info = await run_in_threadpool(mgr.restart, kind, name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if info is None:
        raise HTTPException(status_code=404, detail=f"Service not found: {kind}/{name}")
    return info


@router.patch("/api/services/{kind}/{name}/proxy")
async def patch_proxy(request: Request, kind: str, name: str, body: ProxyPatch) -> dict:
    mgr = _manager(request)
    if mgr.get(kind, name) is None:
        raise HTTPException(status_code=404, detail=f"Service not found: {kind}/{name}")
    try:
        info = await run_in_threadpool(mgr.set_proxy, kind, name, body.proxy)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if info is None:
        raise HTTPException(status_code=404, detail=f"Service not found: {kind}/{name}")
    return info


@router.get("/api/services/{kind}/{name}/log")
async def service_log(request: Request, kind: str, name: str, tail: int = 200) -> dict:
    mgr = _manager(request)
    svc = mgr.get(kind, name)
    if svc is None:
        raise HTTPException(status_code=404, detail=f"Service not found: {kind}/{name}")
    log_path = svc.log_file
    if not log_path.exists():
        return {"lines": []}
    try:
        text = log_path.read_text(errors="replace")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    lines = text.splitlines()
    if tail > 0:
        lines = lines[-tail:]
    return {"lines": lines}


# ---------------------------------------------------------------------------
# Definition CRUD
# ---------------------------------------------------------------------------

@router.post("/api/tunnels")
async def add_tunnel(request: Request, body: TunnelIn) -> dict:
    mgr = _manager(request)
    try:
        config_writer.add_tunnel(
            str(mgr.config_path),
            name=body.name,
            host=body.host,
            proxy=body.proxy,
            forwards=[f.model_dump() for f in body.forwards],
        )
        mgr.reload()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "name": body.name}


@router.delete("/api/tunnels/{name}")
async def delete_tunnel(request: Request, name: str) -> dict:
    mgr = _manager(request)
    try:
        await _stop_before_delete(mgr, "tunnel", name)
        removed = config_writer.remove_tunnel(str(mgr.config_path), name)
        mgr.reload()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": bool(removed), "name": name}


@router.post("/api/mounts")
async def add_mount(request: Request, body: MountIn) -> dict:
    mgr = _manager(request)
    try:
        config_writer.add_mount(
            str(mgr.config_path),
            name=body.name,
            host=body.host,
            remote_path=body.remote_path,
            mount_point=body.mount_point,
            options=list(body.options),
        )
        mgr.reload()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "name": body.name}


@router.delete("/api/mounts/{name}")
async def delete_mount(request: Request, name: str) -> dict:
    mgr = _manager(request)
    try:
        await _stop_before_delete(mgr, "mount", name)
        removed = config_writer.remove_mount(str(mgr.config_path), name)
        mgr.reload()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": bool(removed), "name": name}


@router.post("/api/reverse_proxies")
async def add_reverse_proxy(request: Request, body: ReverseProxyIn) -> dict:
    mgr = _manager(request)
    try:
        config_writer.add_reverse_proxy(
            str(mgr.config_path),
            name=body.name,
            host=body.host,
            local_port=body.local_port,
            remote_port=body.remote_port,
        )
        mgr.reload()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "name": body.name}


@router.delete("/api/reverse_proxies/{name}")
async def delete_reverse_proxy(request: Request, name: str) -> dict:
    mgr = _manager(request)
    try:
        await _stop_before_delete(mgr, "reverse_proxy", name)
        removed = config_writer.remove_reverse_proxy(str(mgr.config_path), name)
        mgr.reload()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": bool(removed), "name": name}
