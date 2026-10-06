r"""Opt-in visible smoke check with real Windows Edge and Chrome installations.

Uses only synthetic pages and test session data; never signs up or logs in.
Run: .venv\Scripts\python.exe tests\windows_smoke.py
"""
import asyncio
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import Database
from app.settings import Settings
from app.profile_manager import ProfileManager
from app.browser_manager import BrowserManager, detect_browser
from app.cookie_manager import export_cookies
from app.state_manager import export_state, import_state, load_state


async def run(root: Path):
    for browser in ('Microsoft Edge', 'Google Chrome'):
        if not detect_browser(browser):
            raise ValueError(f'{browser} is not installed. Install it before running this smoke test.')
    db = Database(root / 'data' / 'app.db')
    settings = Settings(db, root)
    profiles = ProfileManager(db, settings)
    a, b, c = [profiles.create(f'Test {i}', browser) for i, browser in enumerate(('Microsoft Edge','Google Chrome','Microsoft Edge'), 1)]
    assert len({p.directory for p in (a,b,c)}) == 3
    manager = BrowserManager(db, profiles)
    try:
        edge, chrome = await asyncio.gather(manager.launch(a), manager.launch(b))
        assert manager.active(a.id) and manager.active(b.id)
        for context in (edge, chrome):
            await context.route('https://dola.com/**', lambda route: route.fulfill(status=200, content_type='text/html', body='<html><input id="manual"></html>'))
        await manager.open_url(a, 'https://dola.com/')
        await manager.open_url(b, 'https://dola.com/')
        await edge.add_cookies([{'name':'smoke_test', 'value':'synthetic', 'domain':'dola.com', 'path':'/'}])
        pa, pb = await manager.current_page(a), await manager.current_page(b)
        await pa.evaluate("localStorage.setItem('test', 'edge')")
        assert not await chrome.cookies()
        assert await pb.evaluate("localStorage.getItem('test')") is None
        await pa.locator('#manual').focus(); await manager.type_value(a, 'manual test')
        assert await pa.locator('#manual').input_value() == 'manual test'
        await manager.mark_complete(a)
        cookies = await edge.cookies()
        for format in ('JSON','TXT'):
            export_cookies(a, cookies, root / ('cookies.' + format.lower()), format)
        path = root / 'state.json'; await export_state(edge, path)
        await import_state(chrome, load_state(path))
        assert any(c['name'] == 'smoke_test' for c in await chrome.cookies())
        await manager.close(a); await manager.close(b)
        copy = profiles.duplicate(a, 'Copy')
        profiles.rename(copy, 'Renamed'); assert db.get(copy.id).name == 'Renamed'
        profiles.delete(copy); assert not copy.path.exists()
        print('PASS: real Edge + Chrome, simultaneous profiles, isolation, manual input, refresh, JSON/TXT export, state restore, duplicate, rename, delete.')
        print('Live Dola.com signup/login was not tested by this synthetic smoke check.')
    finally:
        await manager.shutdown()


if __name__ == '__main__':
    if platform.system() != 'Windows':
        sys.exit('This check requires Windows 10/11 and both installed browsers.')
    try:
        with TemporaryDirectory(prefix='dola-smoke-') as directory:
            asyncio.run(run(Path(directory)))
    except Exception as error:
        print('FAIL:', str(error) if isinstance(error, ValueError) else type(error).__name__)
        sys.exit(1)
