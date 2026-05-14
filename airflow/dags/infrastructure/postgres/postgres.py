import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def create_sqlalchemy_engine(database_url: str | None = None) -> Engine:
    if not database_url:
        database_url = os.getenv("DATABASE_URL")
        if database_url is None:
            raise ValueError("DATABASE_URL environment variable is not set.")

    engine = create_engine(database_url.replace("postgres://", "postgresql://"), future=True)
    return engine
