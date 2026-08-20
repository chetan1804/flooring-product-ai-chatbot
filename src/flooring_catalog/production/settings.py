"""Validated operational settings with conservative production defaults."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class AppEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


def _integer(values: Mapping[str, str], name: str, default: int) -> int:
    try:
        return int(values.get(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def _boolean(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None:
        return default
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True, slots=True)
class ProductionSettings:
    environment: AppEnvironment = AppEnvironment.DEVELOPMENT
    log_level: str = "INFO"
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    docs_enabled: bool = True
    max_request_body_bytes: int = 16_384
    session_ttl_seconds: int = 86_400
    max_in_memory_sessions: int = 10_000
    database_pool_min_size: int = 1
    database_pool_max_size: int = 10
    database_pool_timeout_seconds: int = 30
    openai_timeout_seconds: int = 30
    openai_max_retries: int = 2

    def __post_init__(self) -> None:
        if self.log_level not in logging.getLevelNamesMapping():
            raise ValueError("LOG_LEVEL is invalid")
        if not self.allowed_hosts:
            raise ValueError("ALLOWED_HOSTS must contain at least one host")
        if self.environment is AppEnvironment.PRODUCTION and "*" in self.allowed_hosts:
            raise ValueError("ALLOWED_HOSTS cannot contain '*' in production")
        positive = {
            "MAX_REQUEST_BODY_BYTES": self.max_request_body_bytes,
            "SESSION_TTL_SECONDS": self.session_ttl_seconds,
            "MAX_IN_MEMORY_SESSIONS": self.max_in_memory_sessions,
            "DATABASE_POOL_MIN_SIZE": self.database_pool_min_size,
            "DATABASE_POOL_MAX_SIZE": self.database_pool_max_size,
            "DATABASE_POOL_TIMEOUT_SECONDS": self.database_pool_timeout_seconds,
            "OPENAI_TIMEOUT_SECONDS": self.openai_timeout_seconds,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.database_pool_min_size > self.database_pool_max_size:
            raise ValueError("DATABASE_POOL_MIN_SIZE cannot exceed DATABASE_POOL_MAX_SIZE")
        if not 0 <= self.openai_max_retries <= 10:
            raise ValueError("OPENAI_MAX_RETRIES must be between 0 and 10")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> ProductionSettings:
        values = os.environ if environ is None else environ
        try:
            environment = AppEnvironment(
                values.get("APP_ENV", AppEnvironment.DEVELOPMENT.value).strip().casefold()
            )
        except ValueError as error:
            raise ValueError("APP_ENV must be development, test, or production") from error
        allowed_hosts = tuple(
            host.strip()
            for host in values.get("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
            if host.strip()
        )
        docs_default = environment is not AppEnvironment.PRODUCTION
        strict_checkpoints = _boolean(values, "LANGGRAPH_STRICT_MSGPACK", False)
        if environment is AppEnvironment.PRODUCTION and not strict_checkpoints:
            raise ValueError("LANGGRAPH_STRICT_MSGPACK must be true in production")
        return cls(
            environment=environment,
            log_level=values.get("LOG_LEVEL", "INFO").strip().upper(),
            allowed_hosts=allowed_hosts,
            docs_enabled=_boolean(values, "API_DOCS_ENABLED", docs_default),
            max_request_body_bytes=_integer(values, "MAX_REQUEST_BODY_BYTES", 16_384),
            session_ttl_seconds=_integer(values, "SESSION_TTL_SECONDS", 86_400),
            max_in_memory_sessions=_integer(values, "MAX_IN_MEMORY_SESSIONS", 10_000),
            database_pool_min_size=_integer(values, "DATABASE_POOL_MIN_SIZE", 1),
            database_pool_max_size=_integer(values, "DATABASE_POOL_MAX_SIZE", 10),
            database_pool_timeout_seconds=_integer(
                values, "DATABASE_POOL_TIMEOUT_SECONDS", 30
            ),
            openai_timeout_seconds=_integer(values, "OPENAI_TIMEOUT_SECONDS", 30),
            openai_max_retries=_integer(values, "OPENAI_MAX_RETRIES", 2),
        )
