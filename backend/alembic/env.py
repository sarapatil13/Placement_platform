"""Alembic environment. Reads the active DATABASE_URL from app settings so
migrations always target the same database the app uses."""

# ruff: noqa: E402  (sys.path must be set before the app imports below)

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Any, Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import engine_from_config, pool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR / "src") not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR / "src"))

from app.core.config import settings
from app.core.crypto import EncryptedString
from app.db import models  # noqa: F401  (registers all mappers)
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def render_item(
    type_: str, obj: Any, autogen_context: AutogenContext
) -> str | Literal[False]:
    """Render EncryptedString as a plain VARCHAR so migrations never depend on
    application code. Encryption is handled transparently at the type level, so
    the SQL schema is identical whether or not a key is configured."""
    if type_ == "type" and isinstance(obj, EncryptedString):
        length = getattr(getattr(obj, "impl_instance", None), "length", None) or 32
        return f"sa.String({length})"
    return False


def run_migrations_offline() -> None:
    """Emit SQL to a stream instead of executing it."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=settings.is_sqlite,
        compare_type=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=settings.is_sqlite,
            compare_type=True,
            render_item=render_item,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()