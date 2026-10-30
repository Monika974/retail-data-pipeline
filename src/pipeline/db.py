from __future__ import annotations

from sqlalchemy import Engine, create_engine

from .config import get_settings


def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or get_settings().database_url, future=True, pool_pre_ping=True)
