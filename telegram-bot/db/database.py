import logging
import sqlite3
from pathlib import Path
from typing import Optional


DB_PATH = Path(__file__).resolve().parent.parent / "tasks.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    logging.info("Initializing database at %s", DB_PATH)
    connection: Optional[sqlite3.Connection] = None
    try:
        connection = get_connection()
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        connection.executescript(schema_sql)
        connection.commit()
        logging.info("Database initialized successfully")
    except Exception:
        if connection:
            connection.rollback()
        logging.exception("Failed to initialize database")
        raise
    finally:
        if connection:
            connection.close()
