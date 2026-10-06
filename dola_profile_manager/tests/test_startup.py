from pathlib import Path
import os
import subprocess
import sys
import pytest
from main import acquire_lock
from app.settings import Settings


def test_instance_lock_excludes_second_process_handle(tmp_path):
    first = acquire_lock(tmp_path / 'app.lock')
    try:
        with pytest.raises(ValueError, match='already running'):
            acquire_lock(tmp_path / 'app.lock')
    finally:
        first.close()
    reopened = acquire_lock(tmp_path / 'app.lock')
    reopened.close()


def test_settings_survive_reload(environment, tmp_path):
    db, settings, _ = environment
    settings.save({'theme': 'Dark', 'default_browser': 'Google Chrome'})
    restored = Settings(db, tmp_path)
    assert restored.values['theme'] == 'Dark'
    assert restored.values['default_browser'] == 'Google Chrome'


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get('DISPLAY') and os.name != 'nt', reason='Desktop display required')
def test_real_entrypoint_starts_and_closes(tmp_path):
    script = '''
import sys
from pathlib import Path
import tkinter as tk
from main import main
original = tk.Tk
class TestRoot(original):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.after(1000, self.request_close)
    def request_close(self):
        self.tk.call(self.protocol('WM_DELETE_WINDOW'))
tk.Tk = TestRoot
sys.argv = ['main.py', '--data-root', sys.argv[1]]
main()
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'data' / 'app.db').is_file()
    assert (tmp_path / 'logs' / 'app.log').is_file()
