"""Uvicorn entry point for the hosted recommendation API."""

from __future__ import annotations

import argparse

import uvicorn

from flooring_catalog.api.app import create_app
from flooring_catalog.config import load_local_environment

load_local_environment()
app = create_app()


def run() -> None:
    parser = argparse.ArgumentParser(description="Run the flooring recommendation API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    uvicorn.run(
        "flooring_catalog.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    run()
