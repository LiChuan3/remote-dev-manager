# Remote Dev Manager (rdm)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Built with Tauri](https://img.shields.io/badge/desktop-Tauri%20v2-24C8DB.svg)](https://tauri.app/)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**A desktop app, CLI, and TUI for running Claude Code / Codex against remote servers — edit remote code locally, route remote AI traffic through your own proxy.**

English | [简体中文](README_zh.md)

---

## What it does

Remote Dev Manager (`rdm`) manages the plumbing between your laptop and your remote dev boxes: SSH tunnels, SSHFS mounts, reverse-proxy tunnels, and smart code mirrors. Its flagship workflow is built for developers who use AI coding tools (**Claude Code**, **Codex CLI**) against remote servers: **one click** sets up a reverse tunnel so the remote machine routes its API traffic through your *local* Clash proxy — so AI tools work even on servers behind a firewall or the GFW that can't reach `api.anthropic.com` / `api.openai.com`. Pair that with the **code mirror** feature to pull a remote repo into a local folder (auto-excluding model weights, datasets, and binaries) and your AI tools read code fast locally while the server stays the execution environment.

Use it whichever way fits your workflow: a native **desktop GUI**, the `rdm` **CLI**, or a terminal **TUI**.

---

## Screenshots

> **Note:** the images below are placeholders. Drop real captures into `docs/screenshots/` before publishing.

![Dashboard](docs/screenshots/dashboard.png)
![Hosts](docs/screenshots/hosts.png)
![AI Proxy](docs/screenshots/ai-proxy.png)

---

## Features

### Desktop GUI

- Native app for **Windows, macOS, and Linux**, built on **Tauri v2** (Rust shell + React/TypeScript/Vite UI).
- Polished **shadcn/ui (radix-nova) interface** with a **light/dark theme** toggle.
- **Desktop batteries:** no startup flash (the window stays hidden until the UI is painted), external links open in the system browser, native scroll/selection behavior, and an optimized release binary.
- **System tray** (Show / Quit) — closing the window hides to tray instead of quitting.
- Optional **autostart** at login.
- Live status and log streaming over WebSocket; single-instance enforced.

### Tunnels & Mounts

- **SSH tunnels** — local (`-L`), remote (`-R`), and dynamic (`-D`) port forwarding, with keepalive and an exponential-backoff auto-restart supervisor.
- **SSHFS mounts** — mount a remote directory into a local folder and edit remote code locally. Windows uses SSHFS-Win + WinFsp; Linux/macOS use `sshfs`.
- **Reverse-proxy tunnels** — expose your local Clash/SOCKS proxy on the remote server via SSH `-R`.
- **Proxy routing for the SSH connections themselves**: `direct`, via local Clash (SOCKS5), or via an SSH jump host.

### AI Proxy (flagship)

- **One-click AI Proxy** — sets up a reverse tunnel **+** writes `~/.rdm_proxy.sh` on the remote (`ALL_PROXY`/`HTTPS_PROXY`/`HTTP_PROXY=socks5://127.0.0.1:7897`) **+** verifies connectivity by curling AI endpoints through the tunnel.
- Generates ready-to-run `ssh -t … claude` / `codex` launch commands.
- Optional persistence via `~/.bashrc`.

### Code Mirror

- **Smart code mirror** — rsync a remote repo to a local directory, auto-excluding model weights, images, datasets, and binaries (107 built-in patterns) with a `--max-size` cap.
- Two-way **push / pull**, plus a **browse** command to discover repos on a remote host.
- **Quick file clone** — scp a single remote file to local in one action.

### CLI & TUI

- Full-featured `rdm` CLI: `up`, `down`, `status`, `log`, `sync`, `mirror`, `init`, `tui`.
- Textual-powered terminal **TUI** dashboard to start/stop/restart and monitor every service.

---

## Why

The core use case is the modern remote-dev loop for AI coding tools:

1. **Edit remote code locally.** Mount it (SSHFS) or mirror it (rsync) so your editor and AI tools read fast, local files — without dragging gigabytes of model weights and datasets across the wire.
2. **Run the tools remotely.** Keep the server as the execution environment (GPUs, data, services).
3. **Route the AI traffic through your proxy.** Even if the server can't reach `api.anthropic.com` / `api.openai.com`, a reverse tunnel sends its requests back through your local Clash, so Claude Code / Codex Just Work.

---

## Architecture

```
                          Desktop app (Tauri v2)
   ┌─────────────────────────────────────────────────────────────┐
   │  Rust shell  ⇄  React/TS UI                                   │
   │  (tray, autostart,   │                                        │
   │   spawns sidecar)    │  http + ws  →  127.0.0.1:8765          │
   └──────────────────────┼────────────────────────────────────────┘
                          │
                          ▼
              FastAPI sidecar  (python -m rdm.api)
                          │
                          ▼
                      rdm core
       (config · process supervisor · tunnel · mount ·
        proxy · sync · mirror · remote SSH automation)
                          │
                          ▼
            system tools:  ssh · rsync · sshfs · scp
                          │
                          ▼
                     Remote server

  AI-proxy path:
    remote AI tool  →  socks5://127.0.0.1:7897 (remote)
                    →  ssh -R reverse tunnel
                    →  local Clash :7897  →  Internet
```

The same `rdm` core powers all three front-ends. The CLI/TUI call it in-process; the desktop app calls it over http/ws through the FastAPI sidecar. All of them read and write the **same `rdm.yaml`** config file.

---

## Install

### 1. Desktop app (recommended)

Download a prebuilt installer from the [Releases page](https://github.com/your-org/remote-dev-manager/releases) *(placeholder — no releases published yet)*.

> You still need `ssh`, and `rsync` / `sshfs` on your `PATH` for the mount and mirror features (see [Configuration](docs/configuration.md) for platform notes).

### 2. Build the desktop app from source

See **[docs/desktop-app.md](docs/desktop-app.md)** for the full developer guide. Short version (Windows, macOS, or Linux):

```bash
cd desktop
npm install
npm run tauri dev      # dev mode (auto-spawns the Python sidecar)
```

To produce an installer locally, run `scripts/build-desktop.ps1` (Windows) or `scripts/build-desktop.sh` (macOS/Linux). To build installers for all three platforms at once, push a `vX.Y.Z` tag and let the [GitHub release workflow](.github/workflows/desktop-build.yml) build and draft the release.

### 3. CLI / TUI via pip

```bash
git clone https://github.com/your-org/remote-dev-manager.git
cd remote-dev-manager
pip install -e ".[api]"     # the [api] extra adds FastAPI + uvicorn for the sidecar / `rdm web`
```

---

## Quick start (desktop)

1. **Launch the app.** It spawns the local sidecar and opens the dashboard.
2. **Add a host** on the Hosts page (user, host, port, identity key).
3. **Test** the connection — you should see the remote user, hostname, and OS.
4. **Enable AI Proxy** for that host with one click, or **add a mirror** to pull a repo locally.
5. Closing the window hides it to the **system tray**; use tray → **Quit** to fully exit.

---

## Quick start (CLI)

```bash
# Generate a starter config in the current directory
rdm init

# Edit rdm.yaml — add your hosts, tunnels, mounts, reverse proxies, mirrors

# Start everything (or name specific services)
rdm up
rdm up gpu-jupyter cloud-clash

# Watch status / tail logs
rdm status
rdm log gpu-jupyter

# Interactive terminal dashboard
rdm tui            # (also the default when you run `rdm` with no args)
```

Mirror commands:

```bash
rdm mirror browse gpu-server                  # discover repos on the remote
rdm mirror add gpu-server /home/u/proj --name proj
rdm mirror pull proj                          # remote → local (auto-excludes weights/data)
rdm mirror push proj                          # local → remote
rdm mirror status proj                        # show pending changes
rdm mirror list
```

Pass an explicit config with `rdm -c /path/to/config.yaml <command>`.

---

## The AI Proxy workflow

The remote server often can't reach `api.anthropic.com` / `api.openai.com`. rdm fixes this by reverse-tunnelling the server's proxy port back to your local Clash:

1. **Run a local proxy** (Clash / mihomo / V2Ray) — typically SOCKS5 on `127.0.0.1:7897`.
2. **One-click AI Proxy** in the desktop app (or `rdm up <reverse-proxy>` from the CLI). This:
   - Starts an `ssh -R 7897:127.0.0.1:7897` reverse tunnel.
   - Writes `~/.rdm_proxy.sh` on the remote with the SOCKS5 env vars.
   - Verifies the tunnel by curling AI endpoints through it.
3. **Launch on the remote** with the proxy active — rdm hands you a copy-pasteable command like:
   ```bash
   ssh -t user@host 'source ~/.rdm_proxy.sh; claude'
   ```

Traffic now flows: **remote AI tool → reverse tunnel → your local Clash → Internet.**

Full deep-dive (including Codex notes and troubleshooting): **[docs/ai-proxy-setup.md](docs/ai-proxy-setup.md)**.

---

## Configuration

rdm is configured by a single YAML file, searched in this order:

1. `$RDM_CONFIG`
2. `./rdm.yaml`
3. `~/.config/rdm/config.yaml` (Linux/macOS) or `%APPDATA%\rdm\config.yaml` (Windows)

The **desktop UI, the CLI, and the TUI all read and write this same file**.

- Fully commented example: **[config.example.yaml](config.example.yaml)**
- Complete field reference: **[docs/configuration.md](docs/configuration.md)**

---

## Build from source

- **Desktop app (Windows / macOS / Linux):** see **[docs/desktop-app.md](docs/desktop-app.md)** (prerequisites, dev workflow, release builds, icons, tray, troubleshooting). Build locally with `scripts/build-desktop.ps1` / `scripts/build-desktop.sh`, or push a `vX.Y.Z` tag to trigger the [cross-platform release workflow](.github/workflows/desktop-build.yml).
- **CLI/TUI only:** `pip install -e ".[api]"`.
- **Architecture reference:** **[docs/architecture.md](docs/architecture.md)**.

---

## Contributing

PRs welcome! See **[CONTRIBUTING.md](CONTRIBUTING.md)** for dev setup, code style, and the architecture overview.

## License

[MIT](LICENSE)
