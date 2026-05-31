"""PyInstaller entry point for the rdm FastAPI sidecar.

Started by the Tauri desktop app as an external binary:

    rdm-sidecar --host 127.0.0.1 --port 8765

When frozen by PyInstaller the ``rdm`` package is collected into the bundle.
When run from source (dev), we add the repo root to ``sys.path`` so ``rdm``
is importable without installing the package.
"""

from __future__ import annotations

import argparse
import os
import sys


def _ensure_rdm_importable() -> None:
    # When frozen, PyInstaller collects ``rdm`` into the bundle, so a normal
    # import works. When running from source, make sure the repo root (three
    # levels up: desktop/sidecar/sidecar_entry.py -> repo root) is on sys.path.
    if getattr(sys, "frozen", False):
        return
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
    )
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


def main() -> None:
    parser = argparse.ArgumentParser(prog="rdm-sidecar")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    _ensure_rdm_importable()

    from rdm.api.server import run

    run(host=args.host, port=args.port, config_path=args.config)


if __name__ == "__main__":
    main()
