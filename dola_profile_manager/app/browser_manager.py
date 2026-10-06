"""Async Playwright lifecycle; never shares persistent user-data directories."""
import asyncio
import logging
import os
from pathlib import Path
import platform
import shutil
from .models import BROWSERS, Profile
from .utils import dola_domain, now, valid_url
from urllib.parse import urlsplit

log = logging.getLogger(__name__)
DOLA_URL = "https://dola.com/"


def detect_browser(browser: str) -> Path | None:
    """Find stable installed browser, including per-user Windows installations."""
    if browser not in BROWSERS:
        raise ValueError("Unsupported browser.")
    if platform.system() == "Windows":
        relative = "Microsoft/Edge/Application/msedge.exe" if browser == "Microsoft Edge" else "Google/Chrome/Application/chrome.exe"
        roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        candidates = [Path(root) / relative for root in roots if root]
        try:
            import winreg
            executable = "msedge.exe" if browser == "Microsoft Edge" else "chrome.exe"
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                    try:
                        with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{executable}", 0, winreg.KEY_READ | view) as key:
                            candidates.append(Path(winreg.QueryValue(key, None).strip('"')))
                    except OSError:
                        pass
        except ImportError:
            pass
    elif platform.system() == "Darwin":
        label = "Microsoft Edge" if browser == "Microsoft Edge" else "Google Chrome"
        candidates = [Path(f"/Applications/{label}.app/Contents/MacOS/{label}")]
    else:
        names = ("microsoft-edge", "microsoft-edge-stable") if browser == "Microsoft Edge" else ("google-chrome", "google-chrome-stable")
        candidates = [Path(value) for name in names if (value := shutil.which(name))]
    return next((p for p in candidates if p.is_file()), None)


class BrowserManager:
    def __init__(self, database, profiles, *, test_executable: Path | None = None, headless: bool = False):
        self.db, self.profiles = database, profiles
        self.contexts: dict = {}
        self.ready: set[str] = set()
        self.playwright = None
        self.test_executable = test_executable
        self.headless = headless
        # Each persistent directory has its own launch lock.  A global lock
        # made bulk launches needlessly serial: profile 2 waited for profile 1
        # to open the website, and so on.  Separate locks preserve the
        # one-context-per-directory guarantee while allowing different browser
        # profiles to start at the same time.
        self.profile_locks: dict[str, asyncio.Lock] = {}
        self.playwright_lock = asyncio.Lock()

    def active(self, profile_id: str) -> bool:
        return profile_id in self.contexts

    def extension_args(self) -> list[str]:
        """Load an approved local unpacked extension for each managed launch.

        The application neither downloads extensions nor configures their
        network behaviour.  Settings validation guarantees the selected folder
        contains a manifest before this command-line argument is used.
        """
        folder = str(self.profiles.settings.values.get("extension_folder", "")).strip()
        if not folder:
            return []
        extension = Path(folder).expanduser().resolve()
        if not (extension.is_dir() and (extension / "manifest.json").is_file()):
            raise ValueError("Configured extension folder is missing manifest.json. Choose it again in Settings.")
        return [f"--load-extension={extension}"]

    async def launch(
        self,
        p: Profile,
        reuse: bool = False,
        window_bounds: tuple[int, int, int, int] | None = None,
    ):
        lock = self.profile_locks.setdefault(p.id, asyncio.Lock())
        async with lock:
            if self.active(p.id):
                if reuse:
                    return self.contexts[p.id]
                raise ValueError("This profile is already running.")
            self.profiles.verify(p)
            if not self.profiles.is_clean_browser_profile(p):
                raise ValueError(
                    "This legacy profile may contain imported personal browser data. "
                    "It was left unchanged. Create a new profile for a fresh browser session."
                )
            installed = self.test_executable or detect_browser(p.browser)
            if not installed:
                raise ValueError(f"{p.browser} was not found on this computer.")
            try:
                if self.playwright is None:
                    async with self.playwright_lock:
                        if self.playwright is None:
                            from playwright.async_api import async_playwright
                            self.playwright = await async_playwright().start()
                kwargs = {"executable_path": str(installed)} if self.test_executable else {"channel": BROWSERS[p.browser]}
                # Playwright is optimized for test automation and disables the
                # extension/update path by default.  This desktop manager uses
                # normal, visible browsers, so restore the browser features
                # required by Edge Add-ons and Chrome Web Store installations.
                ignored_default_args = [
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-default-apps",
                ]
                if platform.system() == "Windows":
                    # Windows does not need this Linux sandbox flag; leaving it
                    # in causes Edge to show an unsupported-flag warning.
                    ignored_default_args.append("--no-sandbox")
                kwargs["ignore_default_args"] = ignored_default_args
                browser_args = [
                    "--no-first-run", "--no-default-browser-check", "--disable-sync",
                    "--enable-extensions", *self.extension_args(),
                ]
                if window_bounds:
                    x, y, width, height = window_bounds
                    browser_args.extend((f"--window-position={x},{y}", f"--window-size={width},{height}"))
                context = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir=str(p.path), headless=self.headless, no_viewport=True,
                    args=browser_args, **kwargs)
            except ImportError:
                raise ValueError("Playwright is unavailable. Install requirements.txt.") from None
            except Exception:
                log.error("Browser launch failed: %s", p.id)
                raise ValueError("Browser launch failed. Close other browsers using this profile and check installation and folder permissions.") from None
            self.contexts[p.id] = context
            self.profiles.active_ids.add(p.id)
            context.on("close", lambda *_: self._closed(p.id, context))
            try:
                self.db.update(p.id, status="Active", last_opened_at=now())
            except Exception:
                await context.close()
                raise
            log.info("Profile launched: %s", p.id)
            return context

    def _closed(self, profile_id: str, context) -> None:
        if self.contexts.get(profile_id) is context:
            self.contexts.pop(profile_id, None)
            self.profiles.active_ids.discard(profile_id)
            self.ready.discard(profile_id)
            try:
                self.db.update(profile_id, status="Closed")
            except Exception:
                log.error("Could not update closed profile metadata: %s", profile_id)
            log.info("Profile closed: %s", profile_id)

    def context(self, p: Profile):
        if not self.active(p.id):
            raise ValueError("Launch this profile first.")
        return self.contexts[p.id]

    async def close(self, p: Profile) -> None:
        lock = self.profile_locks.setdefault(p.id, asyncio.Lock())
        async with lock:
            context = self.context(p)
            await context.close()
            self._closed(p.id, context)

    async def current_page(self, p: Profile, dola: bool = False):
        context = self.context(p)
        pages = [page for page in context.pages if not page.is_closed()]
        if dola:
            pages = [page for page in pages if dola_domain(urlsplit(page.url).hostname or "")]
        if not pages:
            raise ValueError("Open Dola.com first." if dola else "No browser page is open.")
        for page in reversed(pages):
            try:
                if await page.evaluate("document.hasFocus()"):
                    return page
            except Exception:
                pass
        return pages[-1]

    async def open_url(self, p: Profile, url: str, window_bounds: tuple[int, int, int, int] | None = None) -> None:
        url = valid_url(url)
        context = await self.launch(p, reuse=True, window_bounds=window_bounds)
        pages = [page for page in context.pages if not page.is_closed()]
        # A persistent context normally starts with an empty tab. Reuse it so
        # Launch does not leave an unnecessary blank tab beside Dola.com.
        page = next((page for page in reversed(pages) if page.url == "about:blank"), None)
        if page is None:
            page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await page.bring_to_front()
        log.info("Dola.com opened: %s" if dola_domain(urlsplit(url).hostname or "") else "Website opened: %s", p.id)

    async def launch_and_open_dola(self, p: Profile, window_bounds: tuple[int, int, int, int] | None = None) -> None:
        """Launch one independent profile and bring Dola.com to the foreground."""
        try:
            await self.open_url(p, DOLA_URL, window_bounds)
        except ValueError:
            raise
        except Exception:
            raise ValueError(
                "The profile launched, but Dola.com could not be opened. "
                "Check your Internet connection and browser certificate settings, then use Open Dola.com to retry."
            ) from None

    async def launch_all_and_open_dola(
        self,
        profiles: list[Profile],
        window_bounds: dict[str, tuple[int, int, int, int]] | None = None,
    ) -> tuple[list[Profile], list[str]]:
        """Open every saved profile independently, continuing if one fails."""
        async def open_one(profile: Profile) -> tuple[Profile, str | None]:
            try:
                bounds = window_bounds.get(profile.id) if window_bounds else None
                await self.launch_and_open_dola(profile, bounds)
                return profile, None
            except ValueError as error:
                return profile, str(error)

        # Launches use different user-data directories, so they can safely
        # start concurrently.  Results remain in the caller's selected order.
        results = await asyncio.gather(*(open_one(profile) for profile in profiles))
        opened = [profile for profile, error in results if error is None]
        failures = [f"{profile.name}: {error}" for profile, error in results if error]
        return opened, failures

    async def refresh(self, p: Profile) -> None:
        await (await self.current_page(p)).reload(wait_until="load", timeout=45000)

    async def mark_complete(self, p: Profile) -> None:
        page = await self.current_page(p, dola=True)
        await page.reload(wait_until="load", timeout=45000)
        self.context(p)
        self.ready.add(p.id)
        self.db.update(p.id, status="Signup Complete")
        log.info("Signup marked complete: %s", p.id)

    async def type_value(self, p: Profile, value: str) -> None:
        """Type only supplied text, into the field the user focused in the browser."""
        if not value:
            raise ValueError("Enter a value first.")
        page = await self.current_page(p)
        editable = await page.evaluate("""() => {
            const e = document.activeElement;
            return e && !e.disabled && !e.readOnly &&
                (e.isContentEditable || e.tagName === 'TEXTAREA' ||
                 (e.tagName === 'INPUT' && ['text','tel','password','number','email','search'].includes(e.type)));
        }""")
        if not editable:
            raise ValueError("Click the intended input field in the browser first.")
        await page.keyboard.insert_text(value)

    async def shutdown(self) -> None:
        for context in list(self.contexts.values()):
            try:
                await context.close()
            except Exception:
                log.error("Browser close failed.")
        if self.playwright:
            await self.playwright.stop()
