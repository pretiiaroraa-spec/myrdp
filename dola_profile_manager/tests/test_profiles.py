import json
import pytest
from app.utils import valid_url


def test_lifecycle_and_filesystem_isolation(environment):
    db, settings, manager = environment
    profiles = [manager.create(f'Profile {i:03}', browser) for i, browser in enumerate(('Microsoft Edge', 'Google Chrome', 'Microsoft Edge'), 1)]
    assert len({p.directory for p in profiles}) == 3
    for profile in profiles:
        assert manager.is_clean_browser_profile(profile)
        assert (profile.path / 'First Run').is_file()
        assert json.loads((profile.path / 'Local State').read_text()) == {
            'signin': {'allowed': False}, 'sync': {'requested': False},
        }
    assert len(db.list()) == 3
    assert len(db.list('Chrome')) == 1
    assert db.list(profiles[0].id)[0].id == profiles[0].id
    assert [p.name for p in db.list(sort='name')] == ['Profile 001', 'Profile 002', 'Profile 003']
    manager.rename(profiles[0], "Renamed ' ; DROP TABLE profiles;")
    assert db.get(profiles[0].id).name.startswith('Renamed')
    (profiles[0].path / 'test.txt').write_text('test data')
    duplicate = manager.duplicate(profiles[0], 'Copy')
    assert duplicate.path != profiles[0].path
    assert (duplicate.path / 'test.txt').read_text() == 'test data'
    (duplicate.path / 'test.txt').write_text('changed')
    assert (profiles[0].path / 'test.txt').read_text() == 'test data'
    manager.delete(duplicate)
    assert not duplicate.path.exists()
    assert len(db.list()) == 3 and profiles[0].path.is_dir()


@pytest.mark.parametrize('operation', ['delete', 'duplicate'])
def test_active_profile_protected(environment, operation):
    manager = environment[2]
    p = manager.create('P', 'Microsoft Edge')
    with pytest.raises(ValueError, match='Close'):
        getattr(manager, operation)(p, *(['Copy'] if operation == 'duplicate' else []), active=True)
    assert p.path.exists()


def test_tampered_marker(environment):
    manager = environment[2]
    p = manager.create('P', 'Google Chrome')
    (p.path / '.profile-owner').write_text('different')
    with pytest.raises(ValueError):
        manager.delete(p)
    assert environment[0].get(p.id)


def test_new_profile_folder_preserves_old_profiles(environment, tmp_path):
    _, settings, manager = environment
    old = manager.create('Old', 'Google Chrome')
    settings.save({'profile_folder': str(tmp_path / 'new_profiles'), 'theme': 'Dark'})
    new = manager.create('New', 'Google Chrome')
    assert old.path.parent != new.path.parent
    assert manager.verify(old) == old.path and manager.verify(new) == new.path


@pytest.mark.parametrize('name,browser', [('', 'Microsoft Edge'), ('x', 'Firefox'), ('x'*121, 'Google Chrome')])
def test_invalid_creation(environment, name, browser):
    with pytest.raises(ValueError):
        environment[2].create(name, browser)


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'javascript:alert(1)', 'https://user:pass@example.com', 'garbage'])
def test_invalid_urls(url):
    with pytest.raises(ValueError):
        valid_url(url)


def test_external_lock_blocks_delete(environment):
    manager = environment[2]
    p = manager.create('P', 'Google Chrome')
    (p.path / 'SingletonLock').touch()
    with pytest.raises(ValueError, match='locked'):
        manager.delete(p)
    assert p.path.exists()
