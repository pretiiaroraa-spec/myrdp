# Validation evidence — 2026-10-06

This report describes the current Linux cloud instance. It is not a Windows certification or a claim that a live signup was completed.

## Executed successfully

```text
cd /workspace/myrdp/dola_profile_manager
DISPLAY=:99 RUN_BROWSER_TESTS=1 ../.venv/bin/python -m pytest -q
38 passed in 13.96s
```

All 38 checks executed; none failed or skipped in this run. Runtime: Python 3.12.14, Playwright 1.63.0, system Chromium 151.0.7922.173, Tk 9.0, Debian 13, Xvfb virtual display.

| Capability | Evidence |
| --- | --- |
| Full application startup | `main.py` ran as a subprocess, created SQLite/log files and exited through its window-close handler. |
| Dashboard | Real Tk forms created three profiles; tested selection, search, notes, rename, duplicate, delete and theme settings. Layout was inspected visually. |
| Concurrent profiles | Two **visible system Chromium** persistent contexts launched simultaneously in different directories. |
| Filesystem isolation | Three unique profile directories and independently copied duplication data verified. Active profiles cannot be deleted or duplicated by the backend or GUI. |
| Browser storage isolation | Profile A's cookies, local storage and IndexedDB did not appear in Profile B. Explicit state import copied supported state; subsequent writes remained isolated. |
| Persistence | Cookies survived closing and reopening the same persistent profile. |
| Manual helper | Phone/OTP text supplied by the test was typed into explicitly focused fields on a synthetic page. No OTP was retrieved. |
| Completion workflow | A synthetic Dola.com page refreshed, context remained active, completion was recorded and cookie export became enabled. |
| Cookie export | JSON and TXT exports executed from both backend and dashboard; domain filtering, attribute preservation and overwrite prevention verified. |
| State export/import | Cookies, local storage and IndexedDB restored in a real persistent context. Import-failure rollback verified through mocks. |
| SQLite/settings | Lifecycle metadata, parameterized name updates, reload persistence, search/sort and single-instance exclusion verified. |
| Edge/Chrome detection | Windows installation-path discovery verified with temporary paths and platform mocks. |
| Playwright channels | `channel="msedge"` and `channel="chrome"`, visible launch and separate data paths verified with mocks. These were **not real Edge/Chrome processes**. |
| Reusable setup | Dependency installation reran successfully. Xvfb was downloaded using Debian's signed repository metadata and checksum verification, extracted into a writable tools folder, stopped and restarted; Tk readiness succeeded. |
| Dependency health | `pip check`: no broken requirements. Python compilation completed. |
| Repository preservation | Existing `.github/workflows/main.yml` was unchanged. Application source, docs and scripts are new files. Runtime profiles, exports, SQLite files, logs, caches and virtual environments are ignored. |

## Outstanding platform/live checks

- This cloud host is Linux. **Real Windows 10/11 behavior and actual Edge/Chrome channels were not tested.** Run `tests/windows_smoke.py` on Windows with both browsers installed. The script uses synthetic pages and disposable profiles.
- HTTPS access to `https://dola.com/` returned a redirect to `https://www.dola.com/`, followed by HTTP 200 using curl with TLS verification.
- A separate visible Chromium navigation through the cloud's supplied proxy failed with **`net::ERR_CERT_AUTHORITY_INVALID`**. TLS verification was not disabled. This is a cloud browser trust limitation; live interactive browser access is not verified here.
- **No real Dola account was created and no live signup/login, phone verification, OTP or CAPTCHA was performed.** These must be checked manually using an authorized account on the target Windows computer.
- Cookie/state behavior was validated with synthetic session data. Live account sessions can involve authentication domains outside `dola.com`; domain-specific cookie export intentionally does not include them.
- Windows `.cmd` scripts and OS-specific registry/browser behavior require the Windows check. No standalone `.exe` was built; this deliverable is complete Python source with setup/launch scripts.

## Saved cloud configuration

`install_script` and `start_skill` were saved to the environment draft. Custom network domains are `dola.com` and `*.dola.com`; existing package-manager presets were preserved. No provider credential requirement exists. Saving the draft does not execute it or publish a snapshot. Review and save it in environment settings, then publish if you want to retain this prepared cloud environment. Fresh-task restoration has not been independently tested.
