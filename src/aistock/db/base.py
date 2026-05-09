from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str):
    return create_engine(database_url, future=True)


def build_session_factory(database_url: str):
    engine = build_engine(database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def initialize_database(database_url: str) -> None:
    from aistock.db.models import Base

    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
