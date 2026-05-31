#!/usr/bin/env bash
# Full desktop build for Remote Dev Manager (rdm) on Linux / macOS.
#
#   1. Build the Python sidecar into a one-file executable with PyInstaller.
#   2. Rename it to the Rust target-triple form Tauri's externalBin expects.
#   3. Build the Tauri desktop app (frontend + bundle).
#
# Linux build dependencies (Debian/Ubuntu):
#   sudo apt-get install -y libwebkit2gtk-4.1-dev build-essential libssl-dev \
#       libayatana-appindicator3-dev librsvg2-dev
#
# Override the Python interpreter with: PYTHON=python3.12 ./scripts/build-desktop.sh
set -euo pipefail

PYTHON="${PYTHON:-python3}"

# --- Resolve repo root (parent of this scripts/ directory) -----------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"
echo "==> Repo root: $REPO_ROOT"

BINARIES_DIR="$REPO_ROOT/desktop/src-tauri/binaries"
SPEC="$REPO_ROOT/desktop/sidecar/rdm-sidecar.spec"

# --- 1. Build the sidecar with PyInstaller ---------------------------------
echo "==> Building sidecar with PyInstaller..."
mkdir -p "$BINARIES_DIR"
"$PYTHON" -m PyInstaller "$SPEC" \
    --distpath "$BINARIES_DIR" \
    --workpath "$REPO_ROOT/build/pyinstaller" \
    --noconfirm

SIDECAR_BIN="$BINARIES_DIR/rdm-sidecar"
if [ ! -f "$SIDECAR_BIN" ]; then
    echo "Expected sidecar not found: $SIDECAR_BIN" >&2
    exit 1
fi

# --- 2. Compute Rust target triple and rename to Tauri convention ----------
echo "==> Resolving Rust target triple..."
triple="$(rustc -Vv | grep '^host:' | cut -d' ' -f2)"
if [ -z "$triple" ]; then
    echo "Could not determine Rust target triple" >&2
    exit 1
fi
echo "    target triple: $triple"

TARGET_BIN="$BINARIES_DIR/rdm-sidecar-$triple"
cp -f "$SIDECAR_BIN" "$TARGET_BIN"
chmod +x "$TARGET_BIN"
echo "==> Sidecar ready: $TARGET_BIN"

# --- 3. Build the Tauri desktop app ----------------------------------------
echo "==> Building Tauri desktop app..."
cd "$REPO_ROOT/desktop"
npm install
# The bundle config overlay adds the sidecar as an externalBin (kept out of the
# default tauri.conf.json so `tauri dev` / `cargo check` work with no artifacts).
npm run tauri build -- --config src-tauri/tauri.bundle.conf.json

# --- Done ------------------------------------------------------------------
echo ""
echo "==> Build complete."
echo "    Installer / bundle: $REPO_ROOT/desktop/src-tauri/target/release/bundle"
