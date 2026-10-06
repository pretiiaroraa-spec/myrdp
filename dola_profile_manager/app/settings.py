"""User preferences with no credential storage."""
from pathlib import Path
import json

DEFAULTS = {"default_browser": "Microsoft Edge", "cookie_format": "JSON",
            "auto_refresh": True, "theme": "Light", "log_level": "INFO",
            "extension_folder": ""}


class Settings:
    def __init__(self, database, root: Path):
        self.db = database
        self.values = {**DEFAULTS, "profile_folder": str(root / "profiles"), "export_folder": str(root / "exports")}
        with self.db.connection() as db:
            for row in db.execute("SELECT name, value FROM settings"):
                if row["name"] in self.values and row["name"] != "theme":
                    self.values[row["name"]] = json.loads(row["value"])

    def save(self, changes: dict) -> None:
        values = self.values | changes
        # The application intentionally has one consistent light interface.
        # Ignore a legacy stored Dark preference instead of reviving dark mode.
        values["theme"] = "Light"
        if values["default_browser"] not in ("Microsoft Edge", "Google Chrome"):
            raise ValueError("Unsupported browser.")
        if values["cookie_format"] not in ("JSON", "TXT", "NETSCAPE"):
            raise ValueError("Invalid preference.")
        if values["log_level"] not in ("INFO", "WARNING", "ERROR"):
            raise ValueError("Invalid log level.")
        for key in ("profile_folder", "export_folder"):
            path = Path(values[key]).expanduser().resolve()
            path.mkdir(parents=True, exist_ok=True)
            values[key] = str(path)
        extension_folder = str(values.get("extension_folder", "")).strip()
        if extension_folder:
            extension = Path(extension_folder).expanduser().resolve()
            manifest = extension / "manifest.json"
            if not extension.is_dir() or not manifest.is_file():
                raise ValueError("Choose an unpacked browser extension folder containing manifest.json.")
            try:
                metadata = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError("The extension manifest.json is not valid JSON.") from error
            if not isinstance(metadata, dict) or not metadata.get("manifest_version") or not metadata.get("name"):
                raise ValueError("The extension manifest is missing required metadata.")
            values["extension_folder"] = str(extension)
        else:
            values["extension_folder"] = ""
        with self.db.connection() as db:
            for name, value in values.items():
                db.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value", (name, json.dumps(value)))
        self.values = values
