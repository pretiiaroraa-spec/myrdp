"""User preferences with no credential storage."""
from pathlib import Path
import json

DEFAULTS = {"default_browser": "Microsoft Edge", "cookie_format": "JSON",
            "auto_refresh": True, "theme": "Light", "log_level": "INFO"}


class Settings:
    def __init__(self, database, root: Path):
        self.db = database
        self.values = {**DEFAULTS, "profile_folder": str(root / "profiles"), "export_folder": str(root / "exports")}
        with self.db.connection() as db:
            for row in db.execute("SELECT name, value FROM settings"):
                if row["name"] in self.values:
                    self.values[row["name"]] = json.loads(row["value"])

    def save(self, changes: dict) -> None:
        values = self.values | changes
        if values["default_browser"] not in ("Microsoft Edge", "Google Chrome"):
            raise ValueError("Unsupported browser.")
        if values["cookie_format"] not in ("JSON", "TXT") or values["theme"] not in ("Light", "Dark"):
            raise ValueError("Invalid preference.")
        if values["log_level"] not in ("INFO", "WARNING", "ERROR"):
            raise ValueError("Invalid log level.")
        for key in ("profile_folder", "export_folder"):
            path = Path(values[key]).expanduser().resolve()
            path.mkdir(parents=True, exist_ok=True)
            values[key] = str(path)
        with self.db.connection() as db:
            for name, value in values.items():
                db.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value", (name, json.dumps(value)))
        self.values = values
