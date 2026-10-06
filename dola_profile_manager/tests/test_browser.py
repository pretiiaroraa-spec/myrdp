import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.browser_manager import BrowserManager, detect_browser


@pytest.mark.parametrize('browser,channel', [('Microsoft Edge', 'msedge'), ('Google Chrome', 'chrome')])
def test_channels_duplicate_launch_and_close(environment, browser, channel):
    db, _, profiles = environment; p = profiles.create('Test', browser)
    manager = BrowserManager(db, profiles)
    playwright = MagicMock(); context = MagicMock(); context.close = AsyncMock()
    playwright.chromium.launch_persistent_context = AsyncMock(return_value=context)
    manager.playwright = playwright
    async def run():
        with patch('app.browser_manager.detect_browser', return_value=Path('browser.exe')):
            assert await manager.launch(p) is context
            with pytest.raises(ValueError, match='already running'):
                await manager.launch(p)
            assert await manager.launch(p, reuse=True) is context
            with pytest.raises(ValueError, match="Close"):
                profiles.delete(p)
            with pytest.raises(ValueError, match="Close"):
                profiles.duplicate(p, "Forbidden")
            await manager.close(p)
            assert not manager.active(p.id)
    asyncio.run(run())
    arguments = playwright.chromium.launch_persistent_context.call_args.kwargs
    assert arguments['channel'] == channel and arguments['user_data_dir'] == str(p.path)
    assert arguments['headless'] is False


@pytest.mark.parametrize('browser', ['Microsoft Edge', 'Google Chrome'])
def test_missing_browser(environment, browser):
    db, _, profiles = environment; p = profiles.create('Test', browser)
    with patch('app.browser_manager.detect_browser', return_value=None):
        with pytest.raises(ValueError, match='not found'):
            asyncio.run(BrowserManager(db, profiles).launch(p))


@pytest.mark.parametrize('browser,relative', [('Microsoft Edge', 'Microsoft/Edge/Application/msedge.exe'), ('Google Chrome', 'Google/Chrome/Application/chrome.exe')])
def test_windows_browser_detection(tmp_path, monkeypatch, browser, relative):
    executable = tmp_path / relative; executable.parent.mkdir(parents=True); executable.touch()
    monkeypatch.setenv('PROGRAMFILES', str(tmp_path))
    with patch('app.browser_manager.platform.system', return_value='Windows'):
        assert detect_browser(browser) == executable
