from __future__ import annotations

from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.schema import CreateColumn


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
    inspector = inspect(engine)

    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue

            existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns or column.primary_key:
                    continue

                compiled_column = CreateColumn(column).compile(dialect=engine.dialect)
                try:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table.name} ADD COLUMN {compiled_column}"
                    )
                    existing_columns.add(column.name)
                except OperationalError as exc:
                    if "duplicate column name" in str(exc).lower():
                        existing_columns.add(column.name)
                        continue
                    raise
