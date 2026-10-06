"""Run the real Tk dashboard and operate forms against disposable test data."""
import os
from pathlib import Path
import time
from unittest.mock import patch
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.skipif(not os.environ.get('DISPLAY') and os.name != 'nt', reason='A display is required for Tk GUI checks')]


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def wait(root, app, timeout=20):
    deadline = time.monotonic() + timeout
    while app.busy and time.monotonic() < deadline:
        root.update(); time.sleep(.02)
    assert not app.busy, 'GUI operation did not finish'
    root.update()


def test_dashboard_forms_settings_and_errors(environment, tmp_path):
    import tkinter as tk
    from tkinter import ttk
    from app.gui import Application
    db, settings, profiles = environment
    root = tk.Tk()
    errors = []
    with patch('app.gui.messagebox.showerror', side_effect=lambda title, text: errors.append(text)):
        app = Application(root, db, settings, profiles)
        root.update()
        try:
            for _ in range(3):
                app.create(); root.update()
                dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
                create = next(w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget('text') == 'Create')
                create.invoke(); wait(root, app)
            assert len(db.list()) == 3 and len(app.table.get_children()) == 3
            assert app.profile_names('Profile 009', 3) == ['Profile 009', 'Profile 010', 'Profile 011']
            assert app.profile_names('Team', 3) == ['Team 1', 'Team 2', 'Team 3']
            p = db.list()[0]; app.table.selection_set(p.id); app.detail()
            assert str(app.cookie_button.cget('state')) == 'disabled'
            with patch('app.gui.simpledialog.askstring', return_value='GUI Rename'):
                app.rename()
            assert db.get(p.id).name == 'GUI Rename'
            app.notes.insert(0, 'Non-sensitive notes'); app.save_notes()
            assert db.get(p.id).notes == 'Non-sensitive notes'
            app.preference_vars['theme'].set('Dark'); app.save_settings()
            assert settings.values['theme'] == 'Dark'
            app.search.set('GUI Rename'); root.update()
            assert len(app.table.get_children()) == 1
            app.search.set(''); root.update()
            app.table.selection_set(p.id)
            with patch('app.gui.messagebox.askyesno', return_value=True), patch('app.gui.simpledialog.askstring', return_value='GUI Duplicate'):
                app.duplicate(); wait(root, app)
            duplicate = next(p for p in db.list() if p.name == 'GUI Duplicate')
            assert duplicate.path != p.path
            app.table.selection_set(duplicate.id)
            with patch('app.gui.messagebox.askyesno', return_value=True):
                app.delete(); wait(root, app)
            assert len(db.list()) == 3
            assert not errors
        finally:
            app.worker.submit(app.browsers.shutdown()).result(timeout=10)
            app.closing = True; app.worker.stop(); root.destroy()


@pytest.mark.skipif(os.environ.get('RUN_BROWSER_TESTS') != '1', reason='Opt in to real browser GUI workflow')
def test_gui_browser_exports_and_state_workflow(environment, tmp_path):
    import tkinter as tk
    import shutil
    executable = shutil.which('chromium')
    if not executable:
        pytest.skip('System Chromium unavailable')
    from app.gui import Application
    db, settings, profiles = environment
    root = tk.Tk(); errors = []
    with patch('app.gui.messagebox.showerror', side_effect=lambda title, text: errors.append(text)), patch('app.gui.messagebox.askyesno', return_value=True):
        app = Application(root, db, settings, profiles)
        app.browsers.test_executable = Path(executable)
        with patch.object(app.browsers, 'launch_and_open_dola', side_effect=app.browsers.launch):
            first, second = [profiles.create(f'GUI Browser {i}', 'Google Chrome') for i in (1, 2)]
            app.reload()
            for p in (first, second):
                app.table.selection_set(p.id); app.launch(); wait(root, app)
        try:
            assert len(app.browsers.contexts) == 2
            async def prepare():
                for context in app.browsers.contexts.values():
                    await context.route('https://dola.com/**', lambda route: route.fulfill(status=200, content_type='text/html', body='<html><input id="phone"><input id="otp"></html>'))
            app.worker.submit(prepare()).result(timeout=10)
            app.table.selection_set(first.id)
            app.navigate('https://dola.com/'); wait(root, app)
            async def focus_and_seed():
                context = app.browsers.context(first)
                await context.add_cookies([{'name':'gui-test', 'value':'synthetic', 'domain':'dola.com', 'path':'/'}])
                page = await app.browsers.current_page(first)
                await page.locator('#phone').focus()
            app.worker.submit(focus_and_seed()).result(timeout=10)
            app.phone.set('+15550000000'); app.paste(app.phone.get()); wait(root, app)
            app.complete(); wait(root, app)
            assert str(app.cookie_button.cget('state')) == 'normal'
            for format in ('JSON', 'TXT'):
                target = tmp_path / ('GUI_Cookies.' + format.lower())
                with patch('app.gui.simpledialog.askstring', return_value=format), patch('app.gui.filedialog.asksaveasfilename', return_value=str(target)):
                    app.export_cookie(); wait(root, app)
                assert target.exists()
            state = tmp_path / 'GUI_State.json'
            with patch('app.gui.filedialog.asksaveasfilename', return_value=str(state)):
                app.export_browser_state(); wait(root, app)
            app.table.selection_set(second.id)
            with patch('app.gui.filedialog.askopenfilename', return_value=str(state)):
                app.import_browser_state(); wait(root, app)
            assert second.id not in app.browsers.ready
            with patch('app.gui.filedialog.askopenfilename', return_value=str(tmp_path / 'GUI_Cookies.json')):
                app.import_cookie(); wait(root, app)
            for p in (first, second):
                app.table.selection_set(p.id); app.close(); wait(root, app)
            assert not app.browsers.contexts
            assert not errors, errors
        finally:
            app.worker.submit(app.browsers.shutdown()).result(timeout=15)
            app.closing = True; app.worker.stop(); root.destroy()
