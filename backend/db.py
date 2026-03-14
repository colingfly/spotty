# backend/db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import settings

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


def init_db():
    """Create all tables if they don't exist."""
    from models import Base
    Base.metadata.create_all(bind=engine)
