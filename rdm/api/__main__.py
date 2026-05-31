"""Command-line entry point: ``python -m rdm.api``."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="rdm.api",
        description="Run the rdm FastAPI sidecar (local REST + WebSocket API).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8765, help="Bind port")
    parser.add_argument("--config", default=None, help="Path to config file")
    args = parser.parse_args()

    from rdm.api.server import run

    run(host=args.host, port=args.port, config_path=args.config)


if __name__ == "__main__":
    main()
