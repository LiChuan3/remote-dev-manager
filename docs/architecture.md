# Architecture

A concise reference for how Remote Dev Manager is put together. For building the desktop app see [desktop-app.md](desktop-app.md); for the AI-proxy feature see [ai-proxy-setup.md](ai-proxy-setup.md).

---

## Layering

```
┌──────────────────────────────────────────────────────────────────────┐
│  Tauri shell (Rust)        desktop/src-tauri/src/lib.rs                │
│   • spawns + supervises the Python sidecar (kills it on exit)         │
│   • system tray (Show / Quit), close-to-tray, single-instance         │
│   • optional autostart                                                │
└───────────────┬──────────────────────────────────────────────────────┘
                │ hosts a WebView; exposes `get_sidecar_port`, `quit_app`
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  React UI (TypeScript / Vite / Tailwind)   desktop/src/               │
│   • pages/ (Dashboard, Hosts, ...), components/, lib/ (api.ts, ws.ts) │
│   • REST + WebSocket client to the sidecar                            │
└───────────────┬──────────────────────────────────────────────────────┘
                │ http + ws  →  127.0.0.1:8765
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FastAPI sidecar (Python)   rdm/api/                                  │
│   • server.py (app factory + uvicorn), manager.py (ServiceManager)   │
│   • routes/: system, hosts, services, mirror, aiproxy, ws            │
└───────────────┬──────────────────────────────────────────────────────┘
                │ in-process calls
                ▼
┌──────────────────────────────────────────────────────────────────────┐
│  rdm core (Python)   rdm/                                            │
│   config · config_writer · models · process · tunnel · mount ·      │
│   proxy · sync · mirror · remote                                     │
└───────────────┬──────────────────────────────────────────────────────┘
                │ subprocess
                ▼
        system tools:  ssh · rsync · sshfs · scp   →   remote server
```

The **CLI** (`rdm/cli.py`) and **TUI** (`rdm/tui.py`) sit beside the sidecar: they call the same core **in-process**, skipping the http/ws layer. All three front-ends read/write the **same `rdm.yaml`**.

---

## Module map

| Module | Responsibility |
|--------|----------------|
| `rdm/config.py` | Load/parse `rdm.yaml` into dataclasses; locate the config (`$RDM_CONFIG` → `./rdm.yaml` → user config dir); read/write runtime state in `.rdm/state.json` (incl. per-service proxy overrides). |
| `rdm/config_writer.py` | Mutate the YAML in place (add/remove host, tunnel, mount, reverse-proxy, mirror) while preserving structure. Used by the sidecar and `rdm mirror add`. |
| `rdm/models.py` | `Service` abstract base (lifecycle: `start`/`stop`/`restart`/`poll`/`reattach`, PID files, uptime) + `Status` / `ServiceType` enums + backoff fields. |
| `rdm/process.py` | Cross-platform process helpers: hidden spawn, PID read/write/clear, liveness check, process-tree termination, start-time lookup. |
| `rdm/tunnel.py` | `TunnelService` — builds `ssh -N` with `-L`/`-R`/`-D` forwards + keepalive options. |
| `rdm/mount.py` | `MountService` — SSHFS mount/unmount (SSHFS-Win on Windows, `sshfs`/`fusermount` elsewhere). |
| `rdm/proxy.py` | `ReverseProxyService` — `ssh -N -R remote:127.0.0.1:local` to expose the local proxy on the remote. |
| `rdm/sync.py` | One-shot rsync push/pull with excludes; scp fallback. |
| `rdm/mirror.py` | Smart code mirror: rsync with auto-exclude patterns (weights/images/datasets/binaries), `--max-size`, push/pull/status, and remote repo discovery (`list_remote_dirs`). |
| `rdm/remote.py` | SSH automation: `test_connection`, `fetch_file(s)`, and the AI-proxy orchestration (`setup_ai_proxy`, `write_remote_proxy_env`, `verify_remote_proxy`, `remote_launch_command`, teardown). |
| `rdm/api/server.py` | FastAPI app factory + `run()` (uvicorn on `127.0.0.1:8765`). |
| `rdm/api/manager.py` | `ServiceManager` — owns the `Config` and live `Service` objects; reload-preserving-liveness, lock-guarded start/stop/restart/proxy, host lookup, ephemeral service registration. |
| `rdm/api/routes/*` | REST + WS endpoints (see below). |

### Sidecar endpoints (overview)

- **system:** `GET /api/health`, `GET /api/version`, `GET /api/config`, `POST /api/reload`, `POST /api/shutdown`
- **hosts:** `GET/POST /api/hosts`, `PUT/DELETE /api/hosts/{name}`, `POST /api/hosts/{name}/test`, `POST /api/hosts/{name}/browse`
- **services:** `GET /api/services`, `POST /api/services/{kind}/{name}/{start|stop|restart}`, `PATCH .../proxy`, `GET .../log`; definition CRUD for `tunnels` / `mounts` / `reverse_proxies`
- **mirror:** `GET/POST /api/mirrors`, `DELETE /api/mirrors/{name}`, `POST /api/mirrors/{name}/{pull|push}`, `GET /api/mirrors/{name}/status`, `POST /api/fetch-file`
- **ai-proxy:** `POST /api/ai-proxy/setup`, `POST /api/ai-proxy/teardown`, `GET /api/ai-proxy/status`
- **ws:** `/ws/status` (status snapshots every ~2s), `/ws/logs/{kind}/{name}` (live log tail)

---

## Data flow: "Enable AI Proxy" end to end

1. **UI → sidecar.** The desktop app `POST`s `/api/ai-proxy/setup` with `{ host, remote_port, persistent, verify, ensure_tunnel }`.
2. **Ensure the tunnel.** `aiproxy.py` finds or creates a `ReverseProxyService` for the host (binding `clash_port` → `remote_port`) and ensures it's `RUNNING`. That spawns `ssh -N -R <remote_port>:127.0.0.1:<clash_port> …` via `rdm.process`.
3. **Write the remote env.** `remote.setup_ai_proxy` runs over SSH: it tests the connection, then writes `~/.rdm_proxy.sh` on the remote (exporting `ALL_PROXY`/`HTTPS_PROXY`/`HTTP_PROXY`/`NO_PROXY`), optionally appending a guarded `source` line to `~/.bashrc` when `persistent`.
4. **Verify.** `remote.verify_remote_proxy` curls Anthropic/OpenAI/Google through `socks5h://127.0.0.1:<remote_port>` on the remote; a reachable-but-unauthorized code (401/403/404/...) counts as success.
5. **Launch commands.** `remote.remote_launch_command` builds copy-pasteable `ssh -t … 'source ~/.rdm_proxy.sh; claude'` / `codex` strings (not executed — a PTY can't be captured).
6. **Response → UI.** The endpoint returns `{ ok, tunnel, setup{steps,...}, launch{claude,codex} }`; the UI renders the per-step results and the launch commands.

Blocking SSH work is offloaded with `run_in_threadpool` so the event loop stays responsive.

---

## Where state, config, and logs live

| What | Location |
|------|----------|
| **Config** | `rdm.yaml` — found via `$RDM_CONFIG` → `./rdm.yaml` → `~/.config/rdm/config.yaml` (Linux/macOS) / `%APPDATA%\rdm\config.yaml` (Windows). |
| **Workspace** | `defaults.workspace`, else the config file's directory. Root for the `.rdm/` tree, default mount points, and `mirrors/`. |
| **Runtime state** | `<workspace>/.rdm/state.json` — per-service proxy overrides, etc. |
| **Logs** | `<workspace>/.rdm/logs/<service>.log` (append mode). |
| **PID files** | `<workspace>/.rdm/logs/<service>.pid` — used to reattach to running services across restarts. |
| **Remote env** | `~/.rdm_proxy.sh` on the remote host (+ an optional `~/.bashrc` source line). |

Proxy resolution order for a service: runtime override in `state.json` → the service's `proxy` field → `defaults.proxy`.

---

## Process & supervision model

- Services are independent background processes tracked by PID file, not children of the front-end. Quitting the CLI/TUI does **not** stop them; the desktop shell, however, **kills its sidecar** on exit (the sidecar's services persist unless explicitly stopped).
- `Service.poll()` detects unexpected exits and schedules a retry using exponential backoff (`models.py`: base 2s, capped at 300s) when `auto_restart` is on.
- On startup, `reattach()` reads PID files and restores `RUNNING` state for processes that are still alive, cleaning up stale entries otherwise.
