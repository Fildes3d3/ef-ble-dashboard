"""Persistence. One SQLite table per device kind, schema derived from its dataclass."""

import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import DeviceKind


class TelemetryStore:
    """One table per device kind, in a single SQLite file."""

    def __init__(self, database_path: Path, kind: DeviceKind) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.kind = kind
        self.connection = sqlite3.connect(database_path, check_same_thread=False)
        columns = ", ".join(
            "timestamp TEXT PRIMARY KEY" if name == "timestamp" else f"{name} REAL"
            for name in kind.fields
        )
        self.connection.execute(
            f"CREATE TABLE IF NOT EXISTS {kind.table} ({columns})"
        )
        self._add_missing_columns()
        self.connection.commit()

    def _add_missing_columns(self) -> None:
        """Bring an older database up to the current snapshot without losing rows."""
        existing = {
            row[1]
            for row in self.connection.execute(f"PRAGMA table_info({self.kind.table})")
        }
        for name in self.kind.reading_fields:
            if name not in existing:
                self.connection.execute(
                    f"ALTER TABLE {self.kind.table} ADD COLUMN {name} REAL"
                )

    def add(self, snapshot: Any) -> None:
        names = ", ".join(self.kind.fields)
        placeholders = ", ".join(f":{name}" for name in self.kind.fields)
        self.connection.execute(
            f"INSERT OR REPLACE INTO {self.kind.table} ({names}) VALUES ({placeholders})",
            asdict(snapshot),
        )
        self.connection.execute(
            f"DELETE FROM {self.kind.table} WHERE timestamp < datetime('now', '-30 days')"
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def history(self, limit: int = 288) -> list[dict[str, Any]]:
        cursor = self.connection.execute(
            f"SELECT * FROM {self.kind.table} ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in reversed(cursor.fetchall())]


