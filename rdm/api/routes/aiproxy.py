"""One-click AI proxy setup/teardown/status routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from rdm import remote
from rdm.api.manager import ServiceManager
from rdm.api.schemas import AiProxySetupIn, AiProxyTeardownIn
from rdm.config import ReverseProxyConfig
from rdm.models import Status
from rdm.proxy import ReverseProxyService

router = APIRouter()


def _manager(request: Request) -> ServiceManager:
    return request.app.state.manager


def _aiproxy_name(host: str) -> str:
    return f"aiproxy-{host}"


def _find_tunnel_for_host(mgr: ServiceManager, host_name: str):
    """Find an existing reverse_proxy service routing to this host."""
    # Prefer one whose config host_ref matches the host.
    for (kind, _name), svc in mgr.services.items():
        if kind != "reverse_proxy":
            continue
        cfg = getattr(svc, "config", None)
        if cfg is not None and getattr(cfg, "host_ref", None) == host_name:
            return svc
    # Fall back to the conventional ephemeral name.
    return mgr.get("reverse_proxy", _aiproxy_name(host_name))


def _ensure_tunnel(mgr: ServiceManager, host_name: str, remote_port: int,
                   local_port: Optional[int] = None):
    """Ensure a reverse-proxy tunnel for *host_name* exists and is RUNNING."""
    host = mgr.host(host_name)
    if host is None:
        raise HTTPException(status_code=404, detail=f"Unknown host: {host_name}")

    clash_port = local_port or mgr.config.defaults.clash_port
    svc = _find_tunnel_for_host(mgr, host_name)
    if svc is None:
        cfg = ReverseProxyConfig(
            name=_aiproxy_name(host_name),
            host_ref=host_name,
            local_port=clash_port,
            remote_port=remote_port,
        )
        svc = ReverseProxyService(
            config=cfg,
            host=host,
            logs_dir=mgr.config.logs_dir,
            clash_port=mgr.config.defaults.clash_port,
        )
        mgr.register("reverse_proxy", svc)

    svc.poll()
    if svc.status != Status.RUNNING:
        svc.user_stopped = False
        svc.start()
        svc.poll()
    return svc


@router.post("/api/ai-proxy/setup")
async def setup(request: Request, body: AiProxySetupIn) -> dict:
    mgr = _manager(request)
    host = mgr.host(body.host)
    if host is None:
        raise HTTPException(status_code=404, detail=f"Unknown host: {body.host}")

    tunnel_info: Optional[dict] = None
    if body.ensure_tunnel:
        try:
            svc = await run_in_threadpool(
                _ensure_tunnel, mgr, body.host, body.remote_port, body.local_port
            )
            tunnel_info = ServiceManager._info(svc)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        setup_result = await run_in_threadpool(
            remote.setup_ai_proxy,
            host,
            body.remote_port,
            body.persistent,
            body.verify,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        launch_claude = remote.remote_launch_command(
            host, "claude", remote_port=body.remote_port
        )
        launch_codex = remote.remote_launch_command(
            host, "codex", remote_port=body.remote_port
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "ok": bool(setup_result.get("ok", False)),
        "tunnel": tunnel_info,
        "setup": setup_result,
        "launch": {"claude": launch_claude, "codex": launch_codex},
    }


@router.post("/api/ai-proxy/teardown")
async def teardown(request: Request, body: AiProxyTeardownIn) -> dict:
    mgr = _manager(request)
    host = mgr.host(body.host)
    if host is None:
        raise HTTPException(status_code=404, detail=f"Unknown host: {body.host}")

    svc = _find_tunnel_for_host(mgr, body.host)
    if svc is not None:
        try:
            svc.user_stopped = True
            await run_in_threadpool(svc.stop)
        except Exception:
            pass

    try:
        result = await run_in_threadpool(remote.teardown_ai_proxy, host)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": bool(result.get("ok", False)), "teardown": result}


@router.get("/api/ai-proxy/status")
async def status(request: Request, host: str, remote_port: int = 7897) -> dict:
    mgr = _manager(request)
    host_cfg = mgr.host(host)
    if host_cfg is None:
        raise HTTPException(status_code=404, detail=f"Unknown host: {host}")

    svc = _find_tunnel_for_host(mgr, host)
    tunnel_running = False
    if svc is not None:
        try:
            svc.poll()
        except Exception:
            pass
        tunnel_running = svc.status == Status.RUNNING

    try:
        verify = await run_in_threadpool(
            remote.verify_remote_proxy, host_cfg, remote_port
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    reachability = {
        "anthropic": verify.get("anthropic", "000"),
        "openai": verify.get("openai", "000"),
        "google": verify.get("google", "000"),
    }
    ok = bool(tunnel_running and verify.get("ok", False))

    return {
        "ok": ok,
        "active": ok,
        "tunnel_running": tunnel_running,
        "verify": verify,
        "reachability": reachability,
    }
