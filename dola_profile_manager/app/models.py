from dataclasses import dataclass
from pathlib import Path

BROWSERS = {"Microsoft Edge": "msedge", "Google Chrome": "chrome"}


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    browser: str
    directory: str
    created_at: str
    updated_at: str
    last_opened_at: str | None
    status: str
    notes: str

    @property
    def path(self) -> Path:
        return Path(self.directory)
