# Desktop App Developer Guide

The Remote Dev Manager desktop app is a **Tauri v2** application that runs natively on **Windows, macOS, and Linux**: a small Rust shell hosting a **React/TypeScript/Vite** frontend, which talks to a **Python FastAPI sidecar** (the same `rdm` core) over http/ws on `127.0.0.1:8765`. The Rust shell auto-spawns and manages the sidecar, runs a system tray, and supports optional autostart.

The UI is built with **shadcn/ui (the `radix-nova` style)** on Tailwind, with a **light/dark theme** toggle. It ships with "desktop batteries" so it feels like a native app rather than a webview:

- **No startup flash** — the window stays hidden until the UI has painted, then reveals itself.
- **External links open in the system browser** rather than navigating the app webview.
- **Native scroll and text-selection behavior** (no accidental rubber-banding or drag-select of chrome).
- An **optimized release binary** (release-profile Rust build + production Vite bundle).

This guide covers building and hacking on the desktop app. For the CLI/TUI, see the main [README](../README.md).

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| **Node.js** | 18+ (LTS recommended) | Runs Vite + the Tauri CLI. |
| **Rust** | stable toolchain via [rustup](https://rustup.rs/) | Builds the Tauri shell. |
| **Python** | 3.10+ | Runs the FastAPI sidecar. |
| **PyInstaller** | latest | Only needed for *release* builds (bundles the sidecar). |

Install the Python package with the `api` extra so the sidecar's deps (FastAPI + uvicorn) are present:

```bash
pip install -e ".[api]"
```

### Linux system dependencies

Tauri needs WebKitGTK and friends. On Debian/Ubuntu:

```bash
sudo apt-get install -y \
    libwebkit2gtk-4.1-dev \
    build-essential \
    libssl-dev \
    libayatana-appindicator3-dev \
    librsvg2-dev
```

(Other distros: install the equivalent `webkit2gtk-4.1`, `openssl`, `libayatana-appindicator`, and `librsvg` development packages.)

macOS and Windows need their standard Tauri prerequisites (Xcode command-line tools / the MSVC build tools + WebView2, respectively) — see the [Tauri prerequisites guide](https://tauri.app/start/prerequisites/).

---

## Dev workflow

From the `desktop/` directory:

```bash
cd desktop
npm install
npm run tauri dev
```

What happens:

1. Tauri runs `beforeDevCommand` (`npm run dev`), which starts the **Vite dev server on `http://localhost:1420`**.
2. The Rust shell launches and, in its `setup` hook, **spawns the Python sidecar**. In debug builds it runs `python -m rdm.api --port 8765` (falling back to `python3`) with the working directory set to the repo root (two levels up from `desktop/src-tauri`).
3. The React UI calls `get_sidecar_port` via Tauri `invoke`, then talks to the sidecar over `http://127.0.0.1:8765` (REST) and `ws://127.0.0.1:8765` (live status + log streaming).

> **Ports:** Vite dev server `:1420`, sidecar `:8765` (fixed, see `SIDECAR_PORT` in `src-tauri/src/lib.rs`).

Because debug mode runs the sidecar straight from your Python environment, edits to the `rdm` Python package take effect on the next sidecar restart (re-launch the app, or stop/start the dev process).

---

## Project layout

```
desktop/
├── index.html                  # Vite entry HTML
├── package.json                # Frontend deps + scripts (dev, build, tauri)
├── vite.config.ts              # Vite config (dev server on :1420)
├── tailwind.config.js          # Tailwind setup
├── src/                        # React/TypeScript UI
│   ├── main.tsx                # React entry
│   ├── router.tsx              # Routes
│   ├── pages/                  # DashboardPage, HostsPage, ...
│   ├── components/             # Reusable UI (Card, Table, Modal, Toast, ...)
│   └── lib/                    # api.ts (REST client), ws.ts (sockets), types.ts
│
├── sidecar/                    # Python sidecar packaging
│   ├── sidecar_entry.py        # PyInstaller entry: `rdm-sidecar --host --port`
│   └── rdm-sidecar.spec        # PyInstaller spec (one-file build)
│
└── src-tauri/                  # Rust/Tauri shell
    ├── Cargo.toml
    ├── tauri.conf.json         # Window, bundle, externalBin config
    ├── capabilities/           # Tauri permission capabilities
    ├── icons/                  # App icon set (generated)
    ├── binaries/               # Built sidecar lands here (target-triple named)
    └── src/
        ├── main.rs
        └── lib.rs              # Sidecar spawn/kill, tray, autostart, window events
```

The actual `rdm` core (config, tunnel, mount, proxy, sync, mirror, remote, `api/`) lives in the repo's top-level `rdm/` package — the sidecar imports it.

---

## Building releases

Use the build scripts; they do three things in order: build the sidecar with PyInstaller, rename it to the Rust target-triple form Tauri expects, then run the Tauri build.

**Windows:**

```powershell
.\scripts\build-desktop.ps1
# optional: -Python python3.12
```

**Linux / macOS:**

```bash
./scripts/build-desktop.sh
# optional: PYTHON=python3.12 ./scripts/build-desktop.sh
```

### What the scripts do

1. **Build the sidecar.** Run PyInstaller against `desktop/sidecar/rdm-sidecar.spec`, producing a one-file `rdm-sidecar` (`.exe` on Windows) into `desktop/src-tauri/binaries/`.
2. **Target-triple rename.** Tauri's `externalBin` requires the sidecar named with the Rust host triple. The script reads it from `rustc -Vv` (the `host:` line) and copies the binary to, e.g.:
   - `rdm-sidecar-x86_64-pc-windows-msvc.exe`
   - `rdm-sidecar-x86_64-unknown-linux-gnu`
   - `rdm-sidecar-aarch64-apple-darwin`

   `tauri.conf.json` declares `"externalBin": ["binaries/rdm-sidecar"]`, and Tauri appends the triple automatically when bundling.
3. **Build the app.** `npm install` then `npm run tauri build` (which runs `npm run build` → `tsc && vite build`, then the Rust release build).

### Output

Installers and bundles land in:

```
desktop/src-tauri/target/release/bundle/
```

(`.msi`/`.exe` on Windows, `.deb`/`.AppImage`/`.rpm` on Linux, `.dmg`/`.app` on macOS — per `"targets": "all"`.)

In a **release** build the shell looks for the bundled `rdm-sidecar` next to the app executable or in the Tauri resource dir (including a `binaries/` subdir) — *not* your Python environment.

---

## CI / cross-platform release workflow

Two GitHub Actions workflows back the project:

- **[`ci.yml`](../.github/workflows/ci.yml)** — runs on every push/PR to `main`. A Python job (matrix **3.10 / 3.11 / 3.12**) installs `pip install -e ".[api,dev]"`, runs an import smoke test (`import rdm, rdm.api.server`), and runs `pytest` (tolerating "no tests collected"). A frontend job runs `npm ci && npm run build` in `desktop/`. CI deliberately does **not** run a full `tauri build`.
- **[`desktop-build.yml`](../.github/workflows/desktop-build.yml)** — the release workflow. It is modeled on [`tauri-apps/tauri-action`](https://github.com/tauri-apps/tauri-action) and triggers on `workflow_dispatch` or pushing a `v*` tag.

To cut a release, push a version tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The workflow runs a matrix (fail-fast disabled) of four legs and publishes a **draft** GitHub release with the installers attached:

| Leg | Runner | Tauri target |
|-----|--------|--------------|
| Windows | `windows-latest` | (host) `x86_64-pc-windows-msvc` |
| macOS Apple Silicon | `macos-latest` | `aarch64-apple-darwin` |
| macOS Intel | `macos-latest` | `x86_64-apple-darwin` |
| Linux | `ubuntu-22.04` | (host) `x86_64-unknown-linux-gnu` |

Each leg, in order: checkout → install Rust (with both Apple targets on macOS) + `rust-cache` → set up Python 3.12 and `pip install -e ".[api,dev]"` → set up Node 20 and `npm ci` → (Linux only) install the WebKitGTK/appindicator system deps + `patchelf` → **build the PyInstaller sidecar and rename it to the matrix target triple** → `tauri-action` (which bundles the triple-named sidecar via `--config src-tauri/tauri.bundle.conf.json ${{ matrix.args }}`). The sidecar is built **before** `tauri-action` so the triple-named binary exists when Tauri bundles it.

> **macOS Intel note (accepted limitation).** GitHub's `macos-latest` runner is Apple Silicon. PyInstaller cannot cross-freeze a true `x86_64` Mach-O sidecar on an arm64 host, so the Intel leg builds the sidecar for the **host arch (arm64)** and names it `rdm-sidecar-x86_64-apple-darwin` so the Intel bundle has a sidecar present. The resulting "Intel" `.dmg` therefore carries an arm64 sidecar — this is documented in the workflow and the run summary rather than silently mislabeled. For a genuinely native Intel sidecar, move that matrix leg to an Intel macOS runner (e.g. `macos-13`).

Code signing / notarization is left to the maintainer: supply the Apple, Windows, and Tauri-updater secrets and wire them into `tauri-action` / the bundle config.

---

## Generating app icons

Tauri generates the full multi-resolution icon set from a single square PNG:

```bash
cd desktop
npm run tauri icon path/to/app-icon.png
```

This writes the `.png`/`.ico`/`.icns` files referenced by the `bundle.icon` array in `tauri.conf.json` into `src-tauri/icons/`.

---

## System tray behavior

Implemented in `src-tauri/src/lib.rs`:

- **Tray menu:** *Show Window* and *Quit*.
- **Left-click the tray icon** toggles the main window's visibility.
- **Closing the window** does **not** quit — `CloseRequested` is intercepted and the window is hidden to the tray instead. Use tray → **Quit** (or the `quit_app` command) to exit.
- On quit/exit, the shell **kills the sidecar child** and reaps it so it doesn't linger.
- **Single instance:** launching a second copy focuses the existing window instead of starting another.

---

## Autostart

The app bundles `tauri-plugin-autostart` (and the matching JS plugin `@tauri-apps/plugin-autostart`). The UI can enable/disable launch-at-login; on macOS it uses a Launch Agent. Autostart is **opt-in** — nothing is registered unless the user turns it on.

---

## Troubleshooting

**Sidecar didn't start / UI stuck "connecting".**
Check the shell's stderr (run `npm run tauri dev` from a terminal). In debug it logs which interpreter it tried (`python`, then `python3`) and the cwd. Make sure `python -m rdm.api` runs from the repo root and that you installed `pip install -e ".[api]"`. In release builds, confirm the target-triple-named `rdm-sidecar` exists in `binaries/` and got bundled.

**Port 8765 already in use.**
The sidecar port is fixed at `8765` (`SIDECAR_PORT` in `lib.rs`). Free the port (another rdm instance, a stale sidecar, or an unrelated process) before launching. On exit the shell kills its own sidecar, but a hard crash can leave one behind — kill any orphaned `rdm-sidecar` / `python -m rdm.api` process.

**Blank / white window.**
Usually the frontend failed to load. In dev, ensure the Vite server on `:1420` is up (Tauri starts it via `beforeDevCommand`; a `:1420` conflict breaks it). In a release build, a blank window means the bundled frontend is missing — rebuild with `npm run tauri build`.

**Linux: build fails on `webkit2gtk` / `glib`.**
Install the system dependencies listed above (notably `libwebkit2gtk-4.1-dev`). The `4.1` dev package is required for Tauri v2.

**Mounts/mirrors fail from the GUI but ssh works.**
The sidecar shells out to `ssh`/`rsync`/`sshfs`/`scp` on your `PATH`. A GUI app may launch with a different environment than your shell — make sure those tools are on the system `PATH` the app inherits (see [configuration.md](configuration.md) for platform notes, e.g. SSHFS-Win paths on Windows).
