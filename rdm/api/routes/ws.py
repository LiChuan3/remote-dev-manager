"""WebSocket routes: live status stream and live log tailing."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from rdm.api.manager import ServiceManager

router = APIRouter()


def _manager(ws: WebSocket) -> ServiceManager:
    return ws.app.state.manager


@router.websocket("/ws/status")
async def ws_status(websocket: WebSocket) -> None:
    await websocket.accept()
    mgr = _manager(websocket)
    try:
        while True:
            await run_in_threadpool(mgr.poll_all)
            await websocket.send_json(mgr.snapshot())
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
        return


@router.websocket("/ws/logs/{kind}/{name}")
async def ws_logs(websocket: WebSocket, kind: str, name: str) -> None:
    await websocket.accept()
    mgr = _manager(websocket)

    svc = mgr.get(kind, name)
    if svc is None:
        await websocket.send_json({"error": f"Service not found: {kind}/{name}"})
        await websocket.close()
        return

    log_path = svc.log_file
    pos = 0
    try:
        # Send the existing tail first.
        if log_path.exists():
            try:
                text = log_path.read_text(errors="replace")
                if text:
                    await websocket.send_text(text)
                pos = log_path.stat().st_size
            except OSError:
                pos = 0

        while True:
            await asyncio.sleep(0.5)
            if not log_path.exists():
                continue
            try:
                size = log_path.stat().st_size
            except OSError:
                continue
            if size < pos:
                # Truncated / rotated: restart from the beginning.
                pos = 0
            if size > pos:
                def _read(start: int) -> str:
                    with open(log_path, "r", errors="replace") as fh:
                        fh.seek(start)
                        return fh.read()

                chunk = await run_in_threadpool(_read, pos)
                if chunk:
                    await websocket.send_text(chunk)
                pos = size
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
        return
