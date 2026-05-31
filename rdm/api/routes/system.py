"""System routes: health, version, config, reload, shutdown."""

from __future__ import annotations

import os
import threading

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from rdm import __version__
from rdm.api.manager import ServiceManager

router = APIRouter()


def _manager(request: Request) -> ServiceManager:
    return request.app.state.manager


@router.get("/api/health")
async def health() -> dict:
    return {"ok": True, "version": __version__}


@router.get("/api/version")
async def version() -> dict:
    return {"version": __version__}


@router.get("/api/config")
async def get_config(request: Request) -> dict:
    """Return the resolved config as plain JSON."""
    mgr = _manager(request)
    cfg = mgr.config

    hosts = [
        {
            "name": h.name,
            "user": h.user,
            "host": h.host,
            "port": h.port,
            "identity": h.identity,
        }
        for h in cfg.hosts.values()
    ]

    tunnels = [
        {
            "name": t.name,
            "host": t.host_ref,
            "proxy": t.proxy,
            "forwards": [
                {
                    "type": f.type,
                    "local_port": f.local_port,
                    "remote_host": f.remote_host,
                    "remote_port": f.remote_port,
                }
                for f in t.forwards
            ],
        }
        for t in cfg.tunnels
    ]

    mounts = [
        {
            "name": m.name,
            "host": m.host_ref,
            "remote_path": m.remote_path,
            "mount_point": m.mount_point,
            "options": list(m.options),
        }
        for m in cfg.mounts
    ]

    reverse_proxies = [
        {
            "name": rp.name,
            "host": rp.host_ref,
            "local_port": rp.local_port,
            "remote_port": rp.remote_port,
        }
        for rp in cfg.reverse_proxies
    ]

    mirrors = [
        {
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
        for mr in cfg.mirrors
    ]

    defaults = {
        "proxy": cfg.defaults.proxy,
        "clash_port": cfg.defaults.clash_port,
        "auto_restart": cfg.defaults.auto_restart,
        "workspace": cfg.defaults.workspace,
        "locale": cfg.defaults.locale,
    }

    return {
        "hosts": hosts,
        "tunnels": tunnels,
        "mounts": mounts,
        "reverse_proxies": reverse_proxies,
        "mirrors": mirrors,
        "defaults": defaults,
        "config_path": str(mgr.config_path),
        "workspace": str(cfg.workspace_path),
    }


@router.post("/api/reload")
async def reload(request: Request) -> dict:
    _manager(request).reload()
    return {"ok": True}


@router.post("/api/shutdown")
async def shutdown(request: Request) -> dict:
    """Stop managed services, then schedule a clean process exit."""

    stopped = await run_in_threadpool(_manager(request).stop_all)

    def _exit() -> None:
        os._exit(0)

    # Defer slightly so the HTTP response can flush first.
    timer = threading.Timer(0.3, _exit)
    timer.daemon = True
    timer.start()
    return {"ok": True, "stopped": stopped}
