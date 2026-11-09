# backend/db.py
from __future__ import annotations

import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from config import settings

log = logging.getLogger("spotty.db")

is_sqlite = settings.database_url.startswith("sqlite")

engine_kwargs = {"future": True}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 5

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def _ensure_columns() -> None:
    """
    Minimal forward-only migration: add any model column missing from an
    existing table. create_all() never alters existing tables, so without
    this an older spotty.db would crash on the first query touching a new
    column. Safe to run on every boot.
    """
    from models import Base

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                coltype = col.type.compile(dialect=engine.dialect)
                ddl = f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {coltype}'
                log.info("Migrating: %s", ddl)
                conn.execute(text(ddl))


def init_db() -> None:
    """Create all tables if they don't exist, then add any missing columns."""
    from models import Base

    Base.metadata.create_all(bind=engine)
    _ensure_columns()
