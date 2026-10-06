"""Metadata-only SQLite storage; one connection per transaction."""
from pathlib import Path
from contextlib import contextmanager
import sqlite3
from .models import Profile
from .utils import now


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, browser TEXT NOT NULL,
                    directory TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL, last_opened_at TEXT,
                    status TEXT NOT NULL, notes TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')
            db.execute("UPDATE profiles SET status='Closed' WHERE status='Active'")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self, search: str = "", sort: str = "name") -> list[Profile]:
        order = {"name": "name COLLATE NOCASE", "created": "created_at", "last opened": "last_opened_at DESC", "status": "status"}.get(sort, "name")
        with self.connection() as db:
            rows = db.execute(f"SELECT * FROM profiles ORDER BY {order}").fetchall()
        profiles = [Profile(**dict(row)) for row in rows]
        return [p for p in profiles if search.casefold() in " ".join((p.id, p.name, p.browser, p.status)).casefold()]

    def get(self, profile_id: str) -> Profile:
        with self.connection() as db:
            row = db.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        if row is None:
            raise ValueError("Profile no longer exists.")
        return Profile(**dict(row))

    def insert(self, p: Profile) -> None:
        with self.connection() as db:
            db.execute("INSERT INTO profiles VALUES (?,?,?,?,?,?,?,?,?)", tuple(p.__dict__.values()))

    def update(self, profile_id: str, **values) -> None:
        if not values or not set(values) <= {"name", "notes", "status", "last_opened_at"}:
            raise ValueError("Invalid metadata update.")
        values["updated_at"] = now()
        with self.connection() as db:
            db.execute("UPDATE profiles SET " + ", ".join(f"{k}=?" for k in values) + " WHERE id=?", (*values.values(), profile_id))

    def delete(self, profile_id: str) -> None:
        with self.connection() as db:
            db.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
