# Contributing to Remote Dev Manager

Thanks for your interest in improving rdm! This guide gets you a working dev environment and explains how the pieces fit together. PRs are welcome.

---

## Repository layout

```
rdm/                  Python core + CLI/TUI + FastAPI sidecar
  cli.py              argparse CLI (up/down/status/log/sync/mirror/init/tui)
  tui.py              Textual terminal dashboard
  config.py           YAML loading + runtime state (.rdm/)
  config_writer.py    YAML mutation (add/remove host/tunnel/mount/...)
  models.py           Service base class + Status/ServiceType enums
  process.py          Cross-platform process spawn/kill/PID helpers
  tunnel.py           SSH tunnel service (-L / -R / -D)
  mount.py            SSHFS mount service
  proxy.py            Reverse-proxy tunnel service
  sync.py             One-shot rsync/scp push/pull
  mirror.py           Smart code mirror (rsync + auto-excludes)
  remote.py           SSH automation: test, fetch, AI-proxy setup/verify
  api/                FastAPI sidecar (server, manager, routes/)

desktop/              Tauri v2 desktop app
  src/                React/TypeScript/Vite/Tailwind UI
  src-tauri/          Rust shell (tray, autostart, sidecar spawn)
  sidecar/            PyInstaller entry + spec for the bundled sidecar

docs/                 Documentation
scripts/              Build/setup scripts
```

---

## Setting up your dev environment

### Python core + sidecar

```bash
git clone https://github.com/your-org/remote-dev-manager.git
cd remote-dev-manager
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[api]"      # installs the rdm package + FastAPI/uvicorn for the sidecar
```

Run things:

```bash
rdm --help                   # CLI
rdm tui                      # terminal UI
python -m rdm.api --port 8765   # run the sidecar standalone (then hit http://127.0.0.1:8765/api/health)
```

You'll also want `ssh`, `rsync`, and `sshfs` on your `PATH` to exercise the tunnel/mirror/mount features.

### Desktop app

You need Node 18+, a Rust toolchain (via rustup), and on Linux the WebKitGTK system deps. Then:

```bash
cd desktop
npm install
npm run tauri dev
```

In dev, the Rust shell auto-spawns the sidecar with `python -m rdm.api --port 8765`, so your local Python edits are picked up on restart. Full details — release builds, the target-triple sidecar naming, icons, tray, troubleshooting — are in **[docs/desktop-app.md](docs/desktop-app.md)**.

---

## Architecture at a glance

The same `rdm` core backs all three front-ends:

- **CLI/TUI** call the core **in-process**.
- **Desktop app** calls it **over http/ws** through the FastAPI sidecar on `127.0.0.1:8765`; the Rust shell spawns and manages that sidecar.

All front-ends read/write the **same `rdm.yaml`** config. For the full picture (layering, module map, the end-to-end "Enable AI Proxy" data flow, where state/logs live), see **[docs/architecture.md](docs/architecture.md)**.

---

## Code style

- **Python:** type hints everywhere; target 3.10+ (`from __future__ import annotations` is used throughout). Keep functions small and pure where practical; the API layer offloads blocking SSH/rsync work with `run_in_threadpool`. Match the existing module style (dataclasses for config, clear docstrings).
- **TypeScript/React:** functional components, hooks, and the existing component patterns in `desktop/src/components`. Data fetching uses `@tanstack/react-query`; the REST/WS clients live in `desktop/src/lib`.
- **Rust:** keep the shell minimal — it only spawns/kills the sidecar, runs the tray, and manages the window. Avoid pulling business logic into Rust; it belongs in the Python core.
- **Language:** code identifiers and comments in **English**. Docs and user-facing strings may be **bilingual** (English + 中文) — that's welcome.
- Avoid `gen`, `async`, `await`, `try`, `box`, `move`, `dyn`, etc. as Rust identifiers (they're reserved/keywords).

---

## How to add things

### A new service type

1. Add a config dataclass + parser in `rdm/config.py`, and (if the GUI/sidecar should manage it) a `config_writer.py` add/remove pair.
2. Implement a `Service` subclass (`models.py` defines the base) — your class builds the command line, spawns via `rdm.process`, and sets `pid`/`started_at`/`status`. Look at `tunnel.py` / `proxy.py` as templates.
3. Wire it into the service factory in both `rdm/cli.py` (`build_services`) and `rdm/api/manager.py` (`_build_services`).
4. Expose CRUD/lifecycle routes under `rdm/api/routes/` if the desktop app should drive it.

### A new desktop page

1. Add a page component under `desktop/src/pages/` and register it in `desktop/src/router.tsx` (+ the sidebar in `components/Sidebar.tsx`).
2. Add the REST/WS calls to `desktop/src/lib/api.ts` / `ws.ts` and types to `lib/types.ts`.
3. Make sure the backing sidecar endpoints exist in `rdm/api/routes/`.

---

## Pull request guidelines

- **Open an issue first** for anything non-trivial so we can agree on direction.
- Keep PRs focused; one logical change per PR.
- Update the relevant docs (`docs/`, `config.example.yaml`, READMEs) when you change behavior or config.
- Don't introduce new network endpoints or CLI flags without documenting them.
- Be accurate: ports (`8765` sidecar, `7897` Clash default), config search order, and the AI-proxy env contract (`~/.rdm_proxy.sh`) are load-bearing — keep code and docs in sync.

Happy hacking!
