import hashlib
import os
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATABASE_PATH = Path(os.getenv("ROUTEWISE_SQLITE_PATH", DATA_DIR / "routewise.sqlite3"))
_LOCK = Lock()


def _connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with _LOCK, _connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS request_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                prompt_hash TEXT NOT NULL,
                score REAL NOT NULL,
                threshold REAL NOT NULL,
                chosen_model TEXT NOT NULL,
                cheap INTEGER NOT NULL,
                estimated_cost_per_1000 REAL NOT NULL,
                strong_cost_per_1000 REAL NOT NULL,
                latency_ms REAL NOT NULL,
                router_latency_ms REAL NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                fallback_used INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_request_logs_created_at ON request_logs (created_at)"
        )


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def log_request(result: dict[str, Any], prompt: str, input_tokens: int = 0, output_tokens: int = 0, fallback_used: bool = False) -> None:
    with _LOCK, _connection() as connection:
        connection.execute(
            """
            INSERT INTO request_logs (
                prompt_hash, score, threshold, chosen_model, cheap,
                estimated_cost_per_1000, strong_cost_per_1000, latency_ms,
                router_latency_ms, input_tokens, output_tokens, fallback_used
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prompt_hash(prompt),
                result["score"],
                result["threshold"],
                result["chosen_model"],
                int(result["cheap"]),
                result["estimated_cost_per_1000"],
                result["strong_cost_per_1000"],
                result["latency_ms"],
                result["router_latency_ms"],
                input_tokens,
                output_tokens,
                int(fallback_used),
            ),
        )


def dashboard_rows(limit: int = 400) -> list[dict[str, Any]]:
    with _LOCK, _connection() as connection:
        rows = connection.execute(
            """
            SELECT score, threshold, chosen_model, cheap,
                   estimated_cost_per_1000, strong_cost_per_1000,
                   latency_ms, router_latency_ms
            FROM request_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
