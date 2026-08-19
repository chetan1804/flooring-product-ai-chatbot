"""Local configuration bootstrap shared by command-line entry points."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_local_environment(path: str | Path | None = None) -> bool:
    """Load an optional .env file without replacing deployed environment values."""

    return load_dotenv(dotenv_path=path, override=False)

