"""Real Chromium validation; opt in with RUN_BROWSER_TESTS=1.

Branded channels are covered separately with mocks and a Windows smoke script.
Synthetic Dola.com pages do not validate the live website or its login flow.
"""
import asyncio
import json
import os
from pathlib import Path
import shutil
import pytest
from app.browser_manager import BrowserManager
from app.cookie_manager import export_cookies
from app.state_manager import export_state, import_state, load_state

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.environ.get('RUN_BROWSER_TESTS') != '1', reason='Set RUN_BROWSER_TESTS=1 for real Chromium integration')]

HTML = '<html><head><title>Local Dola workflow fixture</title></head><body><input id="phone"><input id="otp"></body></html>'


def test_real_browser_isolation_persistence_state_and_manual_input(environment, tmp_path):
    executable = shutil.which('chromium')
    if not executable:
        pytest.skip('System Chromium not installed')
    db, _, profiles = environment
    a, b, c = [profiles.create(f'Profile {n}', 'Google Chrome') for n in range(1, 4)]
    assert len({p.directory for p in (a, b, c)}) == 3
    manager = BrowserManager(db, profiles, test_executable=Path(executable), headless=not bool(os.environ.get('DISPLAY')))
    async def run():
        try:
            first, second = await asyncio.gather(manager.launch(a), manager.launch(b))
            assert manager.active(a.id) and manager.active(b.id)
            for context in (first, second):
                await context.route('https://dola.com/**', lambda route: route.fulfill(status=200, content_type='text/html', body=HTML))
            await manager.open_url(a, 'https://dola.com/')
            await manager.open_url(b, 'https://dola.com/')
            pa = await manager.current_page(a); pb = await manager.current_page(b)
            await first.add_cookies([{'name':'isolation', 'value':'profile-a-only', 'domain':'dola.com', 'path':'/', 'secure':True, 'sameSite':'Lax'}])
            await pa.evaluate("localStorage.setItem('isolation', 'profile-a-only')")
            await pa.evaluate('''() => new Promise((resolve, reject) => {
                const r = indexedDB.open('isolation', 1);
                r.onupgradeneeded = () => r.result.createObjectStore('records');
                r.onerror = () => reject(r.error);
                r.onsuccess = () => {
                    const db=r.result; const t=db.transaction('records','readwrite');
                    t.objectStore('records').put({text:'a-only'}, 'key');
                    t.oncomplete=()=>{db.close();resolve(true)};
                };
            })''')
            assert not await second.cookies()
            assert await pb.evaluate("localStorage.getItem('isolation')") is None
            assert await pb.evaluate("indexedDB.databases().then(x=>x.length)") == 0
            await pa.locator('#phone').focus()
            await manager.type_value(a, '+15550000000')
            assert await pa.locator('#phone').input_value() == '+15550000000'
            await pa.locator('#otp').focus()
            await manager.type_value(a, '123456')
            assert await pa.locator('#otp').input_value() == '123456'
            await manager.mark_complete(a)
            assert a.id in manager.ready and db.get(a.id).status == 'Signup Complete'
            cookies = await first.cookies()
            for format in ('JSON', 'TXT'):
                export_cookies(a, cookies, tmp_path / ('cookies.' + format.lower()), format)
            state_path = tmp_path / 'state.json'
            await export_state(first, state_path)
            state = load_state(state_path)
            assert state['origins'][0]['indexedDB'][0]['name'] == 'isolation'
            await import_state(second, state)
            await manager.open_url(b, 'https://dola.com/')
            restored = await manager.current_page(b)
            assert await restored.evaluate("localStorage.getItem('isolation')") == 'profile-a-only'
            assert any(cookie['name'] == 'isolation' for cookie in await second.cookies())
            value = await restored.evaluate('''() => new Promise(resolve => {
                const r=indexedDB.open('isolation');
                r.onsuccess=()=>{
                    const db=r.result; const q=db.transaction('records').objectStore('records').get('key');
                    q.onsuccess=()=>{db.close();resolve(q.result.text)};
                };
            })''')
            assert value == 'a-only'
            await restored.evaluate("localStorage.setItem('isolation', 'profile-b-changed')")
            assert await pa.evaluate("localStorage.getItem('isolation')") == 'profile-a-only'
            await manager.close(a)
            reopened = await manager.launch(a)
            assert any(cookie['name'] == 'isolation' for cookie in await reopened.cookies())
            await manager.close(a); await manager.close(b)
            duplicate = profiles.duplicate(a, 'Independent copy')
            assert duplicate.path != a.path
            profiles.rename(duplicate, 'Renamed Copy')
            assert db.get(duplicate.id).name == 'Renamed Copy'
            profiles.delete(duplicate)
            assert not duplicate.path.exists() and a.path.exists()
        finally:
            await manager.shutdown()
    asyncio.run(run())
