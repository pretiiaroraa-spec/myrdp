import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import Database
from app.settings import Settings
from app.profile_manager import ProfileManager

@pytest.fixture
def environment(tmp_path):
    db = Database(tmp_path / 'data' / 'app.db')
    settings = Settings(db, tmp_path)
    return db, settings, ProfileManager(db, settings)
