"""Persistence for records created in the virtual HBYS.

Seed data (data.py) is code. Patients/visits added through the UI, visit status
changes and reports received from Medicore are stored here so they survive the
free-tier spin-down. With HBYS_SIM_DATABASE_URL set they go to PostgreSQL (one
small JSONB table); without it they live in memory (development and tests).
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

_TABLE = "hbys_sim_records"


class MemoryStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}
        self._order: list[tuple[str, str]] = []
        self._lock = threading.Lock()

    def put(self, kind: str, key: str, data: dict[str, Any]) -> None:
        with self._lock:
            if (kind, key) not in self._rows:
                self._order.append((kind, key))
            self._rows[(kind, key)] = json.loads(json.dumps(data))

    def all(self, kind: str) -> list[dict[str, Any]]:
        with self._lock:
            return [json.loads(json.dumps(self._rows[item])) for item in self._order if item[0] == kind]

    def clear(self) -> None:
        with self._lock:
            self._rows.clear()
            self._order.clear()


class PostgresStore:
    def __init__(self, url: str) -> None:
        import psycopg

        self._psycopg = psycopg
        self._url = url
        with self._connect() as connection:
            connection.execute(
                f"CREATE TABLE IF NOT EXISTS {_TABLE} ("
                " kind text NOT NULL, key text NOT NULL, data jsonb NOT NULL,"
                " created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (kind, key))"
            )

    def _connect(self):
        return self._psycopg.connect(self._url, autocommit=True, connect_timeout=10)

    def put(self, kind: str, key: str, data: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                f"INSERT INTO {_TABLE} (kind, key, data) VALUES (%s, %s, %s::jsonb) "
                "ON CONFLICT (kind, key) DO UPDATE SET data = EXCLUDED.data",
                (kind, key, json.dumps(data, ensure_ascii=False)),
            )

    def all(self, kind: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT data FROM {_TABLE} WHERE kind = %s ORDER BY created_at, key", (kind,),
            ).fetchall()
        return [row[0] if isinstance(row[0], dict) else json.loads(row[0]) for row in rows]

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute(f"DELETE FROM {_TABLE}")


def _normalize(url: str) -> str:
    # Render gives postgres:// or postgresql+driver:// style URLs; psycopg wants postgresql://
    for prefix in ("postgres://", "postgresql+psycopg://", "postgresql+asyncpg://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def make_store():
    url = os.environ.get("HBYS_SIM_DATABASE_URL", "").strip()
    return PostgresStore(_normalize(url)) if url else MemoryStore()
