"""Safe filesystem and input helpers."""
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import json
import os
import re
import tempfile


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def valid_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Enter an HTTP or HTTPS URL without embedded credentials.")
    return value.strip()


def dola_domain(domain: str) -> bool:
    domain = domain.lstrip(".").lower()
    return domain == "dola.com" or domain.endswith(".dola.com")


def filename(name: str, suffix: str) -> str:
    cleaned = re.sub(r"[^\w-]+", "_", name, flags=re.ASCII).strip("_")[:80] or "Profile"
    return f"{cleaned}_{suffix}"


def write_private(path: Path, content: str, overwrite: bool = False) -> None:
    """Create exclusively by default; replace atomically on explicit consent."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        with path.open("x", encoding="utf-8") as handle:
            os.chmod(path, 0o600)
            handle.write(content)
        return
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".export-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_json(path: Path) -> object:
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError("Import file exceeds 50 MB.")
    return json.loads(path.read_text(encoding="utf-8"))
