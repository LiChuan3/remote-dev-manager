# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the rdm sidecar (one-file executable).

Build (from the repo root):

    pyinstaller desktop/sidecar/rdm-sidecar.spec \
        --distpath desktop/src-tauri/binaries \
        --workpath build/pyinstaller --noconfirm

Produces ``rdm-sidecar(.exe)`` which the desktop build scripts then rename
to the Rust target-triple form Tauri's ``externalBin`` expects, e.g.
``rdm-sidecar-x86_64-pc-windows-msvc.exe``.
"""

import os

from PyInstaller.utils.hooks import collect_submodules

# This spec file lives at <repo>/desktop/sidecar/rdm-sidecar.spec.
# SPECPATH is provided by PyInstaller and points to this directory.
SPEC_DIR = os.path.abspath(SPECPATH)
REPO_ROOT = os.path.abspath(os.path.join(SPEC_DIR, os.pardir, os.pardir))

ENTRY = os.path.join(SPEC_DIR, "sidecar_entry.py")

hiddenimports = [
    # uvicorn internals that are imported lazily / by string.
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "websockets",
    "websockets.legacy",
    "anyio",
    # rdm modules that may be imported lazily.
    "rdm",
    "rdm.api",
    "rdm.api.server",
    "rdm.api.manager",
    "rdm.api.routes.system",
    "rdm.api.routes.hosts",
    "rdm.api.routes.services",
    "rdm.api.routes.mirror",
    "rdm.api.routes.aiproxy",
    "rdm.api.routes.ws",
    "rdm.remote",
    "rdm.config_writer",
    "rdm.tunnel",
    "rdm.mount",
    "rdm.proxy",
    "rdm.sync",
    "rdm.mirror",
]

# Be safe: pull in all submodules of uvicorn and rdm.
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("rdm")


a = Analysis(
    [ENTRY],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="rdm-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
