import hashlib
import logging
import os
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATABASE_PATH = Path(os.getenv("ROUTEWISE_SQLITE_PATH", DATA_DIR / "routewise.sqlite3"))
DATABASE_URL = os.getenv("DATABASE_URL")
_use_postgres = bool(DATABASE_URL)
_LOCK = Lock()
LOGGER = logging.getLogger(__name__)


def _sqlite_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _connection() -> Any:
    global _use_postgres
    if _use_postgres and DATABASE_URL:
        try:
            return psycopg.connect(DATABASE_URL, row_factory=dict_row)
        except (psycopg.Error, OSError) as error:
            _use_postgres = False
            LOGGER.warning("Neon unavailable; falling back to SQLite: %s", error)
    return _sqlite_connection()


def initialize_database() -> None:
    with _LOCK, _connection() as connection:
        schema = """
            CREATE TABLE IF NOT EXISTS request_logs (
                id {id_type},
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                prompt_hash TEXT NOT NULL,
                score REAL NOT NULL,
                threshold REAL NOT NULL,
                chosen_model TEXT NOT NULL,
                cheap {boolean_type} NOT NULL,
                estimated_cost_per_1000 REAL NOT NULL,
                strong_cost_per_1000 REAL NOT NULL,
                latency_ms REAL NOT NULL,
                router_latency_ms REAL NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                fallback_used {boolean_type} NOT NULL DEFAULT {false_value}
            )
        """.format(
            id_type="SERIAL PRIMARY KEY" if _use_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT",
            boolean_type="BOOLEAN" if _use_postgres else "INTEGER",
            false_value="FALSE" if _use_postgres else "0",
        )
        connection.execute(schema)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_request_logs_created_at ON request_logs (created_at)")


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def log_request(result: dict[str, Any], prompt: str, input_tokens: int = 0, output_tokens: int = 0, fallback_used: bool = False) -> None:
    with _LOCK, _connection() as connection:
        placeholder = "%s" if _use_postgres else "?"
        connection.execute(
            f"""
            INSERT INTO request_logs (
                prompt_hash, score, threshold, chosen_model, cheap,
                estimated_cost_per_1000, strong_cost_per_1000, latency_ms,
                router_latency_ms, input_tokens, output_tokens, fallback_used
            ) VALUES ({", ".join([placeholder] * 12)})
            """,
            (
                prompt_hash(prompt),
                result["score"],
                result["threshold"],
                result["chosen_model"],
                bool(result["cheap"]) if _use_postgres else int(result["cheap"]),
                result["estimated_cost_per_1000"],
                result["strong_cost_per_1000"],
                result["latency_ms"],
                result["router_latency_ms"],
                input_tokens,
                output_tokens,
                bool(fallback_used) if _use_postgres else int(fallback_used),
            ),
        )


def dashboard_rows(limit: int = 400) -> list[dict[str, Any]]:
    with _LOCK, _connection() as connection:
        placeholder = "%s" if _use_postgres else "?"
        rows = connection.execute(
            """
            SELECT score, threshold, chosen_model, cheap,
                   estimated_cost_per_1000, strong_cost_per_1000,
                   latency_ms, router_latency_ms
            FROM request_logs
            ORDER BY id DESC
            LIMIT {placeholder}
            """.format(placeholder=placeholder),
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
