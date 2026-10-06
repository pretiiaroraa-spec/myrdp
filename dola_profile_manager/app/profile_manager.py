"""Profile lifecycle operations with guarded filesystem ownership."""
from pathlib import Path
import json
import logging
import shutil
import uuid
from .models import BROWSERS, Profile
from .utils import now

log = logging.getLogger(__name__)


class ProfileManager:
    def __init__(self, database, settings):
        self.db, self.settings = database, settings
        self.active_ids: set[str] = set()

    @staticmethod
    def _initialize_clean_browser_data(path: Path, profile_id: str) -> None:
        """Create a fresh Chromium data root with sync and first-run import disabled."""
        (path / ".profile-owner").write_text(profile_id, encoding="utf-8")
        (path / ".clean-browser-profile").write_text("1", encoding="utf-8")
        # Chromium-family browsers use this sentinel to skip first-run import.
        (path / "First Run").touch(exist_ok=True)
        local_state = {
            "signin": {"allowed": False},
            "sync": {"requested": False},
        }
        (path / "Local State").write_text(json.dumps(local_state), encoding="utf-8")

    def is_clean_browser_profile(self, profile: Profile) -> bool:
        path = self.verify(profile)
        marker = path / ".clean-browser-profile"
        return marker.is_file() and not marker.is_symlink() and marker.read_text(encoding="utf-8") == "1"

    def verify(self, profile: Profile) -> Path:
        path = profile.path
        if not path.is_dir() or path.is_symlink() or path.name != profile.id:
            raise ValueError("Profile directory is missing or unsafe.")
        marker = path / ".profile-owner"
        if marker.is_symlink() or marker.read_text(encoding="utf-8") != profile.id:
            raise ValueError("Profile directory ownership could not be verified.")
        resolved = path.resolve()
        if any(p.id != profile.id and (p.path.resolve() == resolved or resolved in p.path.resolve().parents or p.path.resolve() in resolved.parents) for p in self.db.list()):
            raise ValueError("Overlapping profile directories detected.")
        return path

    def create(self, name: str, browser: str, notes: str = "") -> Profile:
        name = name.strip()
        if not name or len(name) > 120:
            raise ValueError("Profile name must contain 1–120 characters.")
        if browser not in BROWSERS:
            raise ValueError("Unsupported browser.")
        profile_id = "profile_" + uuid.uuid4().hex
        root = Path(self.settings.values["profile_folder"]).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        path = root / profile_id
        path.mkdir(mode=0o700)
        self._initialize_clean_browser_data(path, profile_id)
        stamp = now()
        p = Profile(profile_id, name, browser, str(path), stamp, stamp, None, "Closed", notes)
        try:
            self.db.insert(p)
        except Exception:
            shutil.rmtree(path)
            raise
        log.info("Profile created: %s", p.id)
        return p

    def rename(self, p: Profile, name: str) -> None:
        if not name.strip() or len(name.strip()) > 120:
            raise ValueError("Profile name must contain 1–120 characters.")
        self.db.update(p.id, name=name.strip())
        log.info("Profile renamed: %s", p.id)

    def ensure_closed(self, p: Profile, active: bool) -> Path:
        if active or p.id in self.active_ids:
            raise ValueError("Close this profile before duplicating or deleting it.")
        path = self.verify(p)
        if any((path / n).exists() or (path / n).is_symlink() for n in ("SingletonLock", "SingletonSocket", "lockfile")):
            raise ValueError("Profile appears locked by another browser. Close it first.")
        return path

    def duplicate(self, p: Profile, name: str, active: bool = False) -> Profile:
        source = self.ensure_closed(p, active)
        if any(item.is_symlink() for item in source.rglob("*")):
            raise ValueError("Profile contains symbolic links; duplication refused.")
        duplicate = self.create(name, p.browser, p.notes)
        try:
            shutil.copytree(source, duplicate.path, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".profile-owner", "Singleton*", "DevToolsActivePort"))
        except Exception:
            self.delete(duplicate)
            raise
        log.info("Profile duplicated: %s to %s", p.id, duplicate.id)
        return duplicate

    def delete(self, p: Profile, active: bool = False) -> None:
        path = self.ensure_closed(p, active)
        tombstone = path.with_name(".deleted_" + p.id)
        path.rename(tombstone)
        try:
            self.db.delete(p.id)
        except Exception:
            tombstone.rename(path)
            raise
        shutil.rmtree(tombstone)
        log.info("Profile deleted: %s", p.id)
