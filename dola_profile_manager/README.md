# Dola.com Multi-Browser Profile Manager

A local Windows 10/11 desktop application for independent Microsoft Edge and Google Chrome profiles. Each browser window stays fully interactive. Login, phone entry, OTP and CAPTCHA are completed by the user. There is no SMS provider integration, number purchasing, OTP retrieval, account creation automation, fingerprint spoofing or security bypass.

## Install and launch on Windows

1. Install **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/windows/), including Tcl/Tk and the Python Launcher.
2. Install [Microsoft Edge](https://www.microsoft.com/edge) and/or [Google Chrome](https://www.google.com/chrome/). Install both for the Windows smoke check.
3. Put this folder in a location your Windows account can write to. Double-click **Setup.cmd**, then **Launch.cmd**.

Alternatively, in a terminal opened in this directory:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

The dependencies are pinned. Tkinter, SQLite and pathlib are included with standard Python. Playwright uses the installed stable browsers via `channel="msedge"` or `channel="chrome"`; **a bundled Chromium download is not needed**. `python -m playwright install chromium` is optional for separate Playwright development, not required by this application's launch path. Do not run `playwright install chrome` or `msedge` unless you intend to install/replace a system browser.

Browser detection checks standard per-user and system Windows paths and App Paths registry entries. If a browser is absent, the GUI shows a clear error. Installing Edge does not install Chrome, or vice versa. Enterprise browser policies can prevent automation even when detection succeeds.

### Data location

By default, data is stored next to `main.py`. For a writable per-user location:

```powershell
.venv\Scripts\python.exe main.py --data-root "$env:LOCALAPPDATA\DolaProfileManager"
```

The application creates `data/app.db`, `profiles/`, `exports/`, `imports/` and `logs/app.log` at startup. SQLite schema creation is automatic. The single-instance lock applies to this data root. Use the same data root consistently; never manually open a managed profile directory in another browser process.

## Using the dashboard

1. Select Microsoft Edge or Google Chrome, then **Create Profile**. Enter its name, browser, optional non-sensitive notes and how many isolated profiles to create. For a batch, names such as `Profile 001` continue sequentially (`Profile 002`, `Profile 003`, and so on). There is no application-defined maximum.
2. Select one or more rows with Ctrl/Shift and click **Launch Selected**, or click **Launch All on Dola.com**. Each selected profile opens independently; the app continues if one browser launch fails and reports the affected profile.
3. Complete signup/login manually in the visible browser. Enter your phone number, password, OTP and any verification yourself.
4. The optional helper can copy supplied phone/OTP text, or type it into the browser field you have explicitly focused. **Enter OTP types text only; it does not press Submit or retrieve a code.** The helper does not identify form selectors automatically. Cross-origin embedded frames are not supported by the helper; enter text directly in the browser for those fields.
5. Click **Mark Signup Complete** after you finish. The app reloads an open `dola.com` page, waits for load completion and confirms the context remains managed. This is your confirmation of completion, not an automated check of account status.
6. Export Dola cookies as JSON or readable TXT; choose the destination in the save dialog. Cookie export is enabled only after completion in the **current active session**.
7. Close the profile and repeat independently with other profiles. There is no configured profile-count limit; RAM, disk and browser resources determine practical concurrency.

The URL field accepts HTTP/HTTPS URLs and rejects embedded credentials. Refresh acts on the focused tab where detectable, otherwise the last open tab. Signup completion selects an open Dola.com tab. Passwords and OTPs are never written to SQLite or logs. Helper fields remain only in memory and can be cleared. Copied values clear from the application clipboard after 30 seconds if still unchanged; OS clipboard history and other clipboard tools remain under your control.

Search matches profile name, ID, browser and status. Sort by name, created date, last opened date or status. Timestamps are labeled UTC. Notes can be saved from the selected-profile panel.

## Profile isolation and lifecycle

Each profile gets a UUID ID and an independent `profiles/profile_<uuid>/` directory. Names such as "Profile 001" are display names. New profiles write a Chromium first-run sentinel and start with browser sync disabled, so they do not import the normal Microsoft Edge or Chrome profile. The database enforces unique directory paths; ownership markers and path checks guard lifecycle operations. Each launch uses a separate persistent browser context and data directory. Cookies, local storage, IndexedDB, cache and preferences are separated by normal Chrome/Edge filesystem behavior. The same profile cannot be launched twice by this application; native browser locking provides another layer of protection.

Profiles made with older releases are left unchanged. If the app identifies one as older, it blocks launch rather than risk opening personal browser data. Create a new profile for a fresh session; the app never silently deletes or changes an existing profile.

- **Rename:** changes metadata only; the directory stays stable.
- **Duplicate:** requires closure, warns about session data and copies into a newly allocated directory. It refuses links and known external lock files. A duplicate intentionally starts with copied browser state; later changes are independent. Browser/OS encryption may limit portability across machines or Windows accounts.
- **Delete:** requires closure, displays the exact name and directory and asks for confirmation. Directory ownership is checked before deleting. A database failure restores the temporarily renamed directory. If cleanup fails after the database deletion, an unlisted `.deleted_profile_*` folder may remain; it can be removed manually after verifying its identity and closing browsers.
- **Open Folder:** opens the verified profile directory in Explorer.

Isolation separates storage; it does not imply anonymity or bypass duplicate-account detection. Browser extensions, websites, account providers and network addresses can still connect sessions through normal mechanisms.

## Cookies and state files

**Treat exports as credentials.** They may grant access to active sessions. Do not commit them, share them publicly or store them in cloud-synced folders without appropriate protection. Files are plaintext; Windows inherits directory ACLs, so use a private Windows user folder, restrict sharing and use disk encryption where needed.

Cookie export retrieves cookies through Playwright and filters to `dola.com` and its subdomains. It preserves every returned cookie field and never changes values. Other authentication domains are not included. No matching cookies produces a clear error rather than an empty success. Examples:

- `Profile_001_Dola_Cookies.json` — metadata plus the complete cookie objects.
- `Profile_001_Dola_Cookies.txt` — readable, JSON-escaped attribute values, preserving additional fields such as partition keys.
- **NETSCAPE** format — standard seven-column Netscape/curl cookie-jar TXT for compatible tools. It cannot preserve modern extra attributes, so JSON remains the full-fidelity option.
- `Profile_001_Browser_State.json` — Playwright state for **all origins** in the selected context.

The save dialog supports folders and custom/timestamped filenames. Existing files require confirmation before replacement; writes refuse an unexpected overwrite by default. **Export All Profile Cookies** processes every saved Edge/Chrome profile, opening an inactive profile only long enough to read its cookies and then closing it. Choose either Dola.com-only or all current browser domains. The all-domains choice exports files containing credentials for other sites and has a separate warning.

Cookie import accepts the exported JSON object or a Playwright cookie array, validates fields and domains, and asks before replacing matching Dola cookies in the selected active profile. TXT is for reading, not import.

Browser-state export includes cookies, local storage and IndexedDB through `storage_state(indexed_db=True)`. Import uses the pinned Playwright `set_storage_state` API, validates the JSON, asks before replacement and closes existing tabs while retaining a blank guard tab. It saves supported previous state in memory and attempts rollback if replacement fails. Export a disk backup first. Reopen the site after import and confirm signup again to enable cookie export.

A storage-state file is **not a complete browser-directory backup**: it does not contain cache, extensions, preferences, sessionStorage or origin private filesystem contents. Replacement can clear origin private files; these are not recoverable from the rollback snapshot. Virtual WebAuthn credentials are intentionally excluded and rejected on import. Browser-profile duplication copies the full closed directory instead. Importing files from untrusted sources can activate somebody else's sessions; inspect the provenance first.

## Settings and logging

Settings persist in SQLite: default browser, new-profile folder, export folder, cookie format, light/dark theme and log level. Folder changes apply to future profiles; existing profiles retain their paths. Auto-refresh after signup remains required to enable cookie export and is shown as a fixed enabled setting. The Live Logs tab tails `logs/app.log` as events occur; Clear View clears only the on-screen log, never the file.

Logs rotate at 2 MB with three backups. They record lifecycle, navigation, completion, import/export and error categories. The application never logs cookies, passwords, OTPs, authentication tokens or full browser exception text. Do not put secrets in profile names or notes.

## Tests and validation

From this directory:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe tests\windows_smoke.py
```

Unit tests cover SQLite, lifecycle and filesystem separation, safe deletion, browser detection, both Playwright channels through mocks, missing-browser errors, cookie formats/validation and state export/import/rollback. GUI checks run when a desktop display is available. Real-browser integration is opt-in and uses system Chromium on Linux, including two simultaneous visible contexts, cookies, local storage and IndexedDB isolation, persistence, manual-field entry and state restoration. The test pages are **synthetic**, not live Dola login pages:

```bash
DISPLAY=:99 RUN_BROWSER_TESTS=1 ../.venv/bin/python -m pytest -q
```

The Windows smoke script runs the installed **actual Edge and Chrome channels simultaneously**, creates three temporary profiles, checks independent storage, manual input, signup refresh, exports, state restore and lifecycle operations. It cleans up its disposable synthetic session data. It must be run on Windows; it does not perform a real signup or contact the live website.

See [VALIDATION.md](VALIDATION.md) for the checks actually executed in this cloud environment. Real Windows launch, enterprise policies and live Dola login require validation on your Windows computer. No actual account signup was performed.

## Troubleshooting

- **Browser not found:** install the selected stable browser, restart the app and retry. Custom/portable browser builds are not selected by this GUI.
- **Playwright unavailable:** install `requirements.txt` using the same interpreter that launches the app. Version 1.63.0 is required for state replacement.
- **Already running / profile locked:** close the managed browser, wait for it to exit and retry. Do not remove lock files from a running browser. The app uses separate directories, never your personal default browser profile.
- **Missing profile directory:** restore its original folder from your own backup. The app refuses to silently create a blank replacement or delete an unverified directory.
- **Permission denied:** move the application/data root to a private writable user directory. Avoid Program Files and shared/network profile folders.
- **Navigation timeout / live-site errors:** check connectivity and browser policies. Use the interactive browser normally. No bypass is provided. Cookie export remains disabled if the required completion refresh fails.
- **OTP paste did not work:** focus the intended editable field in the selected browser, then click the helper. For an iframe or unsupported input, type directly into the browser.
- **Invalid state/JSON:** use a genuine supported Playwright state file. File imports are limited to 50 MB; cookie TXT files cannot be imported.
- **Export failure:** choose a writable private folder and confirm replacement if necessary.
- **Database failure:** close the application before backing up/restoring `data/`. Never delete a live SQLite database or its WAL files.
- **Unexpected browser closure:** the close event updates profile status and disables the completion session; launch again. Managed windows close on normal application exit. Forced process termination can leave a browser to close manually.
- **Cloud GUI:** this is a Windows desktop app, not a web preview. A Linux cloud instance needs a display or virtual display for GUI tests and cannot verify Windows-specific behavior.

## Architecture

`main.py` initializes logging, the data root, SQLite and single-instance lock. `app/gui.py` is the Tk dashboard; `worker.py` owns the background asyncio loop. `database.py`, `models.py` and `settings.py` store metadata/preferences. `profile_manager.py` owns directory lifecycle. `browser_manager.py` owns persistent contexts, navigation and explicit manual input. `cookie_manager.py` and `state_manager.py` handle sensitive exports/imports. `utils.py` provides input and file helpers. The `tests/` directory contains unit, desktop and real-browser checks.
