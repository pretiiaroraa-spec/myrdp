"""Playwright state snapshots including IndexedDB, with rollback on failed import."""
import json
import logging
from pathlib import Path
from urllib.parse import urlsplit
from .cookie_manager import validate_cookies
from .utils import read_json, valid_url, write_private

log = logging.getLogger(__name__)


def validate_state(value: object) -> dict:
    if not isinstance(value, dict) or set(value) - {"cookies", "origins"}:
        raise ValueError("Expected a Playwright state file containing cookies and origins only.")
    validate_cookies(value.get("cookies"))
    origins = value.get("origins")
    if not isinstance(origins, list):
        raise ValueError("State origins must be an array.")
    seen = set()
    for entry in origins:
        if not isinstance(entry, dict) or set(entry) - {"origin", "localStorage", "indexedDB"}:
            raise ValueError("Invalid origin entry.")
        origin = entry.get("origin")
        if not isinstance(origin, str):
            raise ValueError("Invalid storage origin.")
        parts = urlsplit(valid_url(origin))
        if origin != f"{parts.scheme}://{parts.netloc}" or origin in seen:
            raise ValueError("Storage origins must be unique and must not contain paths.")
        seen.add(origin)
        storage = entry.get("localStorage", [])
        if not isinstance(storage, list) or any(not isinstance(item, dict) or set(item) != {"name", "value"} or not all(isinstance(v, str) for v in item.values()) for item in storage):
            raise ValueError("Invalid local storage data.")
        databases = entry.get("indexedDB", [])
        if not isinstance(databases, list):
            raise ValueError("Invalid IndexedDB data.")
        for db in databases:
            if not isinstance(db, dict) or not isinstance(db.get("name"), str) or type(db.get("version")) is not int or db["version"] < 1 or not isinstance(db.get("stores"), list):
                raise ValueError("Invalid IndexedDB database.")
            for store in db["stores"]:
                if not isinstance(store, dict) or not isinstance(store.get("name"), str) or not isinstance(store.get("records"), list) or not isinstance(store.get("indexes", []), list):
                    raise ValueError("Invalid IndexedDB store.")
                if "autoIncrement" in store and not isinstance(store["autoIncrement"], bool):
                    raise ValueError("Invalid IndexedDB autoIncrement flag.")
                for record in store["records"]:
                    if not isinstance(record, dict) or not ({"value", "valueEncoded"} & set(record)):
                        raise ValueError("Invalid IndexedDB record.")
    return value


def load_state(path: Path) -> dict:
    return validate_state(read_json(path))


async def export_state(context, path: Path, overwrite: bool = False) -> None:
    state = await context.storage_state(indexed_db=True)
    write_private(path, json.dumps(state, indent=2, ensure_ascii=False, allow_nan=False), overwrite)
    log.info("Browser state exported.")


async def import_state(context, state: dict) -> None:
    state = validate_state(state)
    previous = await context.storage_state(indexed_db=True)
    # Stop live scripts from racing with storage replacement. The GUI warns about tab closure.
    old_pages = list(context.pages)
    # A visible persistent browser exits when its last tab closes. Keep a blank guard tab.
    guard_page = await context.new_page()
    for page in old_pages:
        await page.close()
    try:
        await context.set_storage_state(state)
    except Exception:
        try:
            await context.set_storage_state(previous)
        except Exception:
            raise ValueError("Import and rollback failed. Close this profile and restore your exported backup.") from None
        raise ValueError("State import failed; previous supported state was restored.") from None
    await guard_page.bring_to_front()
    log.info("Browser state imported.")
