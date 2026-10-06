"""Sensitive cookie export/import without logging session values."""
from pathlib import Path
import json
import logging
import math
from .utils import dola_domain, now, write_private, read_json

log = logging.getLogger(__name__)
WARNING = "Exported browser cookies may contain active login sessions. Store these files securely and never share them publicly."


def validate_cookies(value: object, dola_only: bool = False) -> list[dict]:
    if not isinstance(value, list):
        raise ValueError("Cookies must be a JSON array.")
    for cookie in value:
        if not isinstance(cookie, dict) or not all(isinstance(cookie.get(k), str) for k in ("name", "value", "domain", "path")):
            raise ValueError("Invalid cookie entry.")
        if not cookie["domain"] or not cookie["path"].startswith("/"):
            raise ValueError("Invalid cookie domain or path.")
        if dola_only and not dola_domain(cookie["domain"]):
            raise ValueError("Cookie imports must contain only Dola.com cookies.")
        if "expires" in cookie and (type(cookie["expires"]) not in (int, float) or not math.isfinite(cookie["expires"])):
            raise ValueError("Invalid cookie expiry.")
        for k in ("secure", "httpOnly"):
            if k in cookie and not isinstance(cookie[k], bool):
                raise ValueError("Invalid cookie flag.")
        if "sameSite" in cookie and cookie["sameSite"] not in ("Lax", "Strict", "None"):
            raise ValueError("Invalid SameSite value.")
    return value


def export_cookies(profile, cookies: list[dict], path: Path, format: str, overwrite: bool = False) -> None:
    cookies = [cookie for cookie in cookies if dola_domain(cookie["domain"])]
    if not cookies:
        raise ValueError("No Dola.com cookies found in this profile.")
    payload = {"profile_name": profile.name, "browser": profile.browser, "website": "dola.com", "exported_at": now(), "cookies": cookies}
    if format == "JSON":
        text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)
    elif format == "TXT":
        lines = ["Dola.com Cookie Export", "========================", f"Profile: {profile.name}", f"Browser: {profile.browser}", "Website: dola.com", f"Exported: {payload['exported_at']}"]
        for index, cookie in enumerate(cookies, 1):
            lines += ["", "-" * 50, f"COOKIE {index}", "-" * 50]
            lines += [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in cookie.items()]
        text = "\n".join(lines) + "\n"
    else:
        raise ValueError("Choose JSON or TXT.")
    write_private(path, text, overwrite)
    log.info("Cookie export completed: %s", profile.id)


def load_cookies(path: Path) -> list[dict]:
    value = read_json(path)
    if isinstance(value, dict):
        value = value.get("cookies")
    return validate_cookies(value, dola_only=True)
