from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from free_frontier.app import create_app
from free_frontier.config import ConfigurationError, load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Free Frontier proxy")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to TOML configuration (default: free-frontier.toml)",
    )
    parser.add_argument("--host", default=None, help="Override configured bind host")
    parser.add_argument("--port", type=int, default=None, help="Override configured bind port")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    try:
        config = load_config(args.config)
    except ConfigurationError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc

    app = create_app(config=config)
    uvicorn.run(
        app,
        host=args.host or config.server.host,
        port=args.port or config.server.port,
    )
