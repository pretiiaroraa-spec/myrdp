import asyncio
import json
from unittest.mock import AsyncMock
import pytest
from app.cookie_manager import export_cookies, load_cookies, validate_cookies
from app.state_manager import export_state, import_state, load_state, validate_state

COOKIE = {'name': 'session', 'value': 'test-only', 'domain': '.dola.com', 'path': '/', 'expires': -1, 'httpOnly': True, 'secure': True, 'sameSite': 'Lax', 'partitionKey': 'https://dola.com'}
STATE = {'cookies': [COOKIE], 'origins': [{'origin': 'https://dola.com', 'localStorage': [{'name': 'key', 'value': 'test'}]}]}


def test_exports_preserve_fields_filter_domains_and_prevent_overwrite(environment, tmp_path):
    p = environment[2].create('Profile 001', 'Microsoft Edge')
    cookies = [COOKIE, COOKIE | {'domain': 'notdola.com'}]
    path = tmp_path / 'cookies.json'
    export_cookies(p, cookies, path, 'JSON')
    assert json.loads(path.read_text())['cookies'] == [COOKIE]
    assert load_cookies(path) == [COOKIE]
    with pytest.raises(FileExistsError):
        export_cookies(p, cookies, path, 'JSON')
    export_cookies(p, cookies, path, 'JSON', overwrite=True)
    txt = tmp_path / 'cookies.txt'
    export_cookies(p, cookies, txt, 'TXT')
    assert 'partitionKey' in txt.read_text() and 'test-only' in txt.read_text()


@pytest.mark.parametrize('cookies', [[COOKIE | {'domain': 'notdola.com'}], [{}], [{'name': 1}], [COOKIE | {'expires': float('nan')}], [COOKIE | {'httpOnly': 'true'}]])
def test_invalid_cookies(cookies):
    with pytest.raises(ValueError):
        validate_cookies(cookies, dola_only=True)


def test_state_export_import(tmp_path):
    context = AsyncMock(); context.pages = []; context.storage_state.return_value = STATE
    path = tmp_path / 'state.json'
    asyncio.run(export_state(context, path))
    assert load_state(path) == STATE
    asyncio.run(import_state(context, STATE))
    context.set_storage_state.assert_awaited_once_with(STATE)
    context.new_page.assert_awaited_once()


def test_state_rollback():
    context = AsyncMock(); context.pages = []
    previous = {'cookies': [], 'origins': []}
    context.storage_state.return_value = previous
    context.set_storage_state.side_effect = [RuntimeError('failed'), None]
    with pytest.raises(ValueError, match='restored'):
        asyncio.run(import_state(context, STATE))
    assert context.set_storage_state.await_args_list[1].args[0] == previous


@pytest.mark.parametrize('state', [{}, {'cookies': [], 'origins': [{'origin': 'file:///etc/passwd'}]}, {'cookies': [], 'origins': 'bad'}, {'cookies': [], 'origins': [{'origin': 'https://dola.com/path'}]}, STATE | {'credentials': []}])
def test_invalid_state(state):
    with pytest.raises(ValueError):
        validate_state(state)
