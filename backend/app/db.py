from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .config import settings

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def connect() -> psycopg.Connection:
    return psycopg.connect(settings.database_url, row_factory=dict_row)


def init_schema(conn: psycopg.Connection) -> None:
    conn.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
    conn.commit()
