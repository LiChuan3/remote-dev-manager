"""FastAPI app factory and uvicorn runner for the rdm sidecar."""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from rdm.api.manager import ServiceManager
from rdm.api.routes import aiproxy, hosts, mirror, services, system, ws


def create_app(config_path: Optional[str] = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="rdm")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Single shared service manager. Tolerant of a missing config file.
    manager = ServiceManager(config_path)
    app.state.manager = manager

    app.include_router(system.router)
    app.include_router(hosts.router)
    app.include_router(services.router)
    app.include_router(mirror.router)
    app.include_router(aiproxy.router)
    app.include_router(ws.router)

    @app.on_event("startup")
    async def _startup() -> None:
        try:
            manager.poll_all()
        except Exception:
            pass
        app.state.supervisor_task = asyncio.create_task(_supervisor_loop(manager))

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        task = getattr(app.state, "supervisor_task", None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": str(exc)})

    return app


async def _supervisor_loop(manager: ServiceManager) -> None:
    """Keep service status fresh and apply the API-side auto-restart policy."""
    while True:
        await asyncio.to_thread(manager.poll_all)
        await asyncio.sleep(2.0)


def run(
    host: str = "127.0.0.1",
    port: int = 8765,
    config_path: Optional[str] = None,
) -> None:
    """Run the sidecar with uvicorn."""
    import uvicorn

    app = create_app(config_path)
    uvicorn.run(app, host=host, port=port, log_level="warning")
