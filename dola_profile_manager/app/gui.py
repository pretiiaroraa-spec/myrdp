"""Responsive Tk dashboard. Browser operations run on a dedicated asyncio loop."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import logging
import os
import queue
import re
import subprocess
import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog, scrolledtext
from .models import BROWSERS
from .browser_manager import BrowserManager
from .cookie_manager import WARNING, export_cookies, load_cookies
from .state_manager import export_state, import_state, load_state
from .utils import filename
from .worker import Worker

log = logging.getLogger(__name__)


class Application:
    def __init__(self, root, database, settings, profiles) -> None:
        self.root, self.db, self.settings, self.profiles = root, database, settings, profiles
        self.worker = Worker()
        self.browsers = BrowserManager(database, profiles)
        self.results = queue.Queue()
        self.busy = False
        self.closing = False
        self.log_path = Path(self.db.path).parent.parent / "logs" / "app.log"
        self.log_offset = 0
        self.log_last_read = 0.0
        root.title("Dola.com • Multi-Browser Profile Manager")
        root.geometry("1180x850")
        root.minsize(1000, 760)
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.style = ttk.Style(root)
        self.style.theme_use("clam")
        self.apply_theme()
        self.browser = tk.StringVar(value=settings.values["default_browser"])
        self.search = tk.StringVar()
        self.sort = tk.StringVar(value="name")
        self.status = tk.StringVar(value="Ready • Signup and verification are completed manually in the browser.")
        titlebar = ttk.Frame(root)
        titlebar.pack(fill="x", padx=20, pady=(15, 4))
        ttk.Label(titlebar, text="MULTI-BROWSER PROFILE MANAGER", font=("Segoe UI", 19, "bold")).pack(side="left")
        ttk.Label(titlebar, text="Created by Kashif Hassan", font=("Segoe UI", 10, "bold")).pack(side="right")
        ttk.Label(root, text="Dola.com  |  Isolated local sessions  |  Microsoft Edge & Google Chrome").pack(anchor="w", padx=20)
        tabs = ttk.Notebook(root)
        tabs.pack(fill="both", expand=True, padx=15, pady=12)
        dashboard, preferences, logs = [ttk.Frame(tabs, padding=12) for _ in range(3)]
        tabs.add(dashboard, text="Profiles")
        tabs.add(preferences, text="Settings")
        tabs.add(logs, text="Live Logs")
        self.build_dashboard(dashboard)
        self.build_settings(preferences)
        self.build_logs(logs)
        ttk.Label(root, textvariable=self.status, wraplength=1120).pack(fill="x", padx=20, pady=(0, 12))
        self.search.trace_add("write", lambda *_: self.reload())
        self.reload()
        root.after(100, self.poll)

    def apply_theme(self) -> None:
        dark = self.settings.values["theme"] == "Dark"
        bg, fg, field = ("#202733", "#f0f3f8", "#303b4b") if dark else ("#f4f6fa", "#172638", "#ffffff")
        self.root.configure(bg=bg)
        self.style.configure(".", background=bg, foreground=fg, font=("Segoe UI", 10))
        self.style.configure("Treeview", background=field, fieldbackground=field, foreground=fg, rowheight=29)
        self.style.configure("TEntry", fieldbackground=field, foreground=fg)
        self.style.configure("TCombobox", fieldbackground=field, foreground=fg)
        self.style.configure("TButton", padding=(10, 6))
        self.style.map("Treeview", background=[("selected", "#2563eb")], foreground=[("selected", "white")])

    def button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=lambda: self.guard(command))
        button.pack(side="left", padx=3, pady=3)
        return button

    def guard(self, command) -> None:
        if self.busy:
            messagebox.showinfo("Operation in progress", "Wait for the current operation to finish.")
            return
        try:
            command()
        except (ValueError, OSError) as error:
            messagebox.showerror("Unable to complete action", str(error))
        except Exception as error:
            log.error("GUI operation failed: %s", type(error).__name__)
            messagebox.showerror("Unable to complete action", "The operation failed. Check permissions and logs, then try again.")

    def build_dashboard(self, frame) -> None:
        controls = ttk.Frame(frame)
        controls.pack(fill="x")
        ttk.Label(controls, text="Browser:").pack(side="left")
        ttk.Combobox(controls, textvariable=self.browser, values=list(BROWSERS), state="readonly", width=19).pack(side="left", padx=6)
        ttk.Label(controls, text="Search:").pack(side="left", padx=(15, 0))
        ttk.Entry(controls, textvariable=self.search, width=26).pack(side="left", padx=6)
        ttk.Combobox(controls, textvariable=self.sort, values=["name", "created", "last opened", "status"], state="readonly", width=12).pack(side="left", padx=6)
        self.sort.trace_add("write", lambda *_: self.reload())
        self.button(controls, "+ Create Profile", self.create)
        self.button(controls, "Launch Selected", self.launch_selected)
        self.button(controls, "Launch All on Dola.com", self.launch_all)
        pane = ttk.Panedwindow(frame, orient="horizontal")
        pane.pack(fill="both", expand=True, pady=12)
        left, right = ttk.Frame(pane), ttk.Frame(pane, padding=(15, 0))
        pane.add(left, weight=3)
        pane.add(right, weight=2)
        columns = ("name", "browser", "status", "opened")
        self.table = ttk.Treeview(left, columns=columns, show="headings", selectmode="extended")
        for key, label, width in zip(columns, ("Profile", "Browser", "Status", "Last opened (UTC)"), (150, 100, 130, 165)):
            self.table.heading(key, text=label)
            self.table.column(key, width=width, minwidth=60)
        self.table.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.table.yview)
        scroll.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scroll.set)
        self.table.bind("<<TreeviewSelect>>", lambda *_: self.detail())
        self.details = tk.StringVar(value="Select a profile.")
        ttk.Label(right, text="Selected Profile", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(right, textvariable=self.details, wraplength=390, justify="left").pack(fill="x", pady=8)
        row = ttk.Frame(right); row.pack(fill="x")
        for text, fn in (("Launch", self.launch), ("Close", self.close), ("Rename", self.rename)):
            self.button(row, text, fn)
        row = ttk.Frame(right); row.pack(fill="x")
        for text, fn in (("Duplicate", self.duplicate), ("Delete", self.delete), ("Open Folder", self.open_folder)):
            self.button(row, text, fn)
        ttk.Label(right, text="Notes").pack(anchor="w", pady=(6, 0))
        self.notes = ttk.Entry(right); self.notes.pack(fill="x")
        row = ttk.Frame(right); row.pack(fill="x")
        self.button(row, "Save Notes", self.save_notes)
        row = ttk.Frame(right); row.pack(fill="x", pady=(8, 0))
        self.button(row, "Open Dola.com", lambda: self.navigate("https://dola.com/"))
        self.button(row, "Refresh Page", self.refresh)
        self.url = tk.StringVar(value="https://dola.com/")
        ttk.Entry(right, textvariable=self.url).pack(fill="x", pady=4)
        row = ttk.Frame(right); row.pack(fill="x")
        self.button(row, "Open URL", lambda: self.navigate(self.url.get()))
        self.button(row, "Mark Signup Complete", self.complete)
        row = ttk.Frame(right); row.pack(fill="x", pady=(8, 0))
        self.cookie_button = self.button(row, "Export Dola Cookies", self.export_cookie)
        self.button(row, "Import Cookies", self.import_cookie)
        row = ttk.Frame(right); row.pack(fill="x")
        self.button(row, "Export All Profile Cookies", self.export_all_cookies)
        row = ttk.Frame(right); row.pack(fill="x")
        self.button(row, "Export Browser State", self.export_browser_state)
        self.button(row, "Import Browser State", self.import_browser_state)
        helper = ttk.LabelFrame(frame, text="Manual verification helper • Focus the target field in the browser before pasting", padding=7)
        helper.pack(fill="x")
        self.phone, self.otp = tk.StringVar(), tk.StringVar()
        for label, variable in (("Phone Number", self.phone), ("OTP", self.otp)):
            row = ttk.Frame(helper); row.pack(fill="x")
            ttk.Label(row, text=label, width=14).pack(side="left")
            ttk.Entry(row, textvariable=variable, width=34, show="•" if label == "OTP" else "").pack(side="left", padx=5)
            self.button(row, "Copy", lambda v=variable: self.copy(v.get()))
            self.button(row, "Paste to Browser" if label != "OTP" else "Enter OTP", lambda v=variable: self.paste(v.get()))
        self.button(helper, "Clear Sensitive Fields", lambda: (self.phone.set(""), self.otp.set("")))
        ttk.Label(helper, text="Complete login, CAPTCHA and all verification yourself. Marking complete is your confirmation, not an account-status check.").pack(anchor="w")

    def selected(self):
        selection = self.table.selection()
        if not selection:
            raise ValueError("Select a profile first.")
        return self.db.get(selection[0])

    def selected_profiles(self):
        selected = self.table.selection()
        if not selected:
            raise ValueError("Select one or more profiles first.")
        return [self.db.get(profile_id) for profile_id in selected]

    def reload(self) -> None:
        selected = self.table.selection() if hasattr(self, "table") else ()
        if not hasattr(self, "table"):
            return
        profiles = self.db.list(self.search.get(), self.sort.get())
        self.table.delete(*self.table.get_children())
        for p in profiles:
            self.table.insert("", "end", iid=p.id, values=(p.name, p.browser.replace("Microsoft ", "").replace("Google ", ""), p.status, p.last_opened_at or "Never"))
        if selected and self.table.exists(selected[0]):
            self.table.selection_set(selected[0])
        self.detail()

    def detail(self) -> None:
        try:
            p = self.selected()
            active = self.browsers.active(p.id)
            self.details.set(f"{p.name}\n{p.browser}  •  {p.status}\nID: {p.id}\nDirectory: {p.directory}\nCreated: {p.created_at}")
            self.notes.delete(0, "end"); self.notes.insert(0, p.notes)
            self.cookie_button.configure(state="normal" if active and p.id in self.browsers.ready else "disabled")
        except ValueError:
            self.details.set("Select a profile.")
            self.cookie_button.configure(state="disabled")

    def submit(self, coroutine, message="Completed.", callback=None) -> None:
        self.busy = True
        self.status.set("Working… Browser windows remain interactive.")
        future = self.worker.submit(coroutine)
        future.add_done_callback(lambda result: self.results.put((result, message, callback)))

    def poll(self) -> None:
        if self.closing:
            return
        try:
            while True:
                future, message, callback = self.results.get_nowait()
                self.busy = False
                try:
                    result = future.result()
                    self.status.set(message)
                    if callback:
                        callback(result)
                except Exception as error:
                    log.error("Background operation failed: %s", type(error).__name__)
                    safe = str(error) if isinstance(error, ValueError) else "Operation failed. Check the browser, network access and folder permissions."
                    self.status.set(safe)
                    messagebox.showerror("Operation failed", safe)
                self.reload()
        except queue.Empty:
            pass
        # Keep rows synchronized after the user closes a browser directly.
        changed = False
        for p in self.db.list():
            if self.table.exists(p.id):
                if self.table.set(p.id, "status") != p.status:
                    self.table.set(p.id, "status", p.status)
                    if p.id in self.table.selection():
                        changed = True
        if changed:
            self.detail()
        self.refresh_logs()
        self.root.after(200, self.poll)

    def build_logs(self, frame) -> None:
        header = ttk.Frame(frame)
        header.pack(fill="x")
        ttk.Label(header, text="LIVE ACTIVITY LOG", font=("Segoe UI", 14, "bold")).pack(side="left")
        self.follow_logs = tk.BooleanVar(value=True)
        ttk.Checkbutton(header, text="Follow live", variable=self.follow_logs).pack(side="left", padx=12)
        self.button(header, "Clear View", self.clear_log_view)
        self.log_text = scrolledtext.ScrolledText(
            frame, height=30, wrap="word", state="disabled", font=("Cascadia Mono", 9)
        )
        if self.settings.values["theme"] == "Dark":
            self.log_text.configure(background="#171b22", foreground="#d9e2ef", insertbackground="#d9e2ef")
        self.log_text.pack(fill="both", expand=True, pady=(10, 0))
        self.refresh_logs(force=True)

    def clear_log_view(self) -> None:
        """Clear the screen only; the permanent log file remains intact."""
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def refresh_logs(self, force: bool = False) -> None:
        if not hasattr(self, "log_text") or (not force and time.monotonic() - self.log_last_read < 0.5):
            return
        self.log_last_read = time.monotonic()
        try:
            size = self.log_path.stat().st_size
            if size < self.log_offset:
                self.log_offset = 0
                self.clear_log_view()
            with self.log_path.open("r", encoding="utf-8", errors="replace") as log_file:
                log_file.seek(self.log_offset)
                entries = log_file.read()
                self.log_offset = log_file.tell()
        except OSError:
            return
        if not entries:
            return
        self.log_text.configure(state="normal")
        self.log_text.insert("end", entries)
        if int(self.log_text.index("end-1c").split(".")[0]) > 2_000:
            self.log_text.delete("1.0", "500.0")
        if self.follow_logs.get():
            self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def create(self) -> None:
        dialog = tk.Toplevel(self.root); dialog.title("Create Profile"); dialog.transient(self.root); dialog.grab_set()
        name = tk.StringVar(value=f"Profile {len(self.db.list()) + 1:03d}")
        browser = tk.StringVar(value=self.browser.get()); notes = tk.StringVar(); quantity = tk.StringVar(value="1")
        for label, variable in (("Profile Name", name), ("Browser", browser), ("Notes", notes)):
            ttk.Label(dialog, text=label).pack(anchor="w", padx=15, pady=(8, 0))
            widget = ttk.Combobox(dialog, textvariable=variable, values=list(BROWSERS), state="readonly") if label == "Browser" else ttk.Entry(dialog, textvariable=variable, width=45)
            widget.pack(fill="x", padx=15)
        ttk.Label(dialog, text="Profiles to create").pack(anchor="w", padx=15, pady=(8, 0))
        ttk.Entry(dialog, textvariable=quantity, width=12).pack(anchor="w", padx=15)
        ttk.Label(dialog, text="For more than one profile, sequential names are created automatically.", wraplength=330).pack(anchor="w", padx=15, pady=(4, 0))
        def save():
            try:
                count = int(quantity.get())
            except ValueError:
                raise ValueError("Profiles to create must be a whole number.") from None
            if count < 1:
                raise ValueError("Profiles to create must be at least 1.")
            names = self.profile_names(name.get(), count)
            chosen_browser, chosen_notes = browser.get(), notes.get()
            dialog.destroy()
            async def run():
                return await asyncio.to_thread(
                    lambda: [self.profiles.create(profile_name, chosen_browser, chosen_notes) for profile_name in names]
                )
            def select_created(created):
                self.reload()
                self.table.selection_set(created[0].id)
                self.detail()
            self.submit(run(), f"Created {count} isolated profile{'s' if count != 1 else ''}.", select_created)
        row = ttk.Frame(dialog); row.pack(pady=12)
        self.button(row, "Create", save)
        self.button(row, "Cancel", dialog.destroy)

    def launch(self) -> None:
        self.submit(self.browsers.launch_and_open_dola(self.selected()), "Profile launched and Dola.com opened.")

    def launch_selected(self) -> None:
        profiles = self.selected_profiles()
        if len(profiles) == 1:
            self.launch()
            return
        self.launch_profiles(profiles)

    def launch_all(self) -> None:
        profiles = self.db.list()
        if not profiles:
            raise ValueError("Create at least one profile first.")
        self.launch_profiles(profiles)

    def launch_profiles(self, profiles) -> None:
        def display(result):
            opened, failures = result
            self.status.set(
                f"Opened Dola.com in {len(opened)} of {len(profiles)} profile"
                f"{'s' if len(profiles) != 1 else ''}."
            )
            if failures:
                messagebox.showwarning(
                    "Some profiles did not open",
                    f"Opened {len(opened)} of {len(profiles)} profiles.\n\n" + "\n".join(failures),
                )
        self.submit(
            self.browsers.launch_all_and_open_dola(profiles),
            "Opening Dola.com in saved profiles.",
            display,
        )

    @staticmethod
    def profile_names(first_name: str, count: int) -> list[str]:
        """Generate readable consecutive display names without limiting the count."""
        first_name = first_name.strip()
        if count == 1:
            return [first_name]
        match = re.fullmatch(r"(.*?)(\d+)", first_name)
        if match:
            prefix, number = match.groups()
            width, start = len(number), int(number)
            return [f"{prefix}{start + offset:0{width}d}" for offset in range(count)]
        return [f"{first_name} {number}" for number in range(1, count + 1)]

    def close(self) -> None:
        self.submit(self.browsers.close(self.selected()), "Profile closed.")

    def navigate(self, url) -> None:
        self.submit(self.browsers.open_url(self.selected(), url), "Website opened.")

    def refresh(self) -> None:
        self.submit(self.browsers.refresh(self.selected()), "Page refreshed.")

    def complete(self) -> None:
        p = self.selected()
        if messagebox.askyesno("Confirm manual signup", f"Have you completed signup/login in {p.name}? The Dola.com page will refresh."):
            self.submit(self.browsers.mark_complete(p), "Signup marked complete. Cookie export enabled.")

    def rename(self) -> None:
        p = self.selected()
        name = simpledialog.askstring("Rename", "New profile name:", initialvalue=p.name)
        if name is not None:
            self.profiles.rename(p, name); self.reload()

    def duplicate(self) -> None:
        p = self.selected()
        self.profiles.ensure_closed(p, self.browsers.active(p.id))
        if not messagebox.askyesno("Sensitive session data", "The duplicate may contain active login sessions. Create a separate copy?"):
            return
        name = simpledialog.askstring("Duplicate", "New profile name:", initialvalue=p.name + " Copy")
        if name:
            async def run():
                return await asyncio.to_thread(self.profiles.duplicate, p, name, False)
            self.submit(run(), "Profile duplicated into a separate directory.")

    def delete(self) -> None:
        p = self.selected()
        self.profiles.ensure_closed(p, self.browsers.active(p.id))
        if messagebox.askyesno("Delete profile permanently", f"Delete '{p.name}'?\n\n{p.directory}\n\nAll browser data in this profile will be removed."):
            async def run():
                await asyncio.to_thread(self.profiles.delete, p, False)
            self.submit(run(), "Profile deleted.")

    def open_folder(self) -> None:
        path = self.profiles.verify(self.selected())
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def save_notes(self) -> None:
        self.db.update(self.selected().id, notes=self.notes.get()); self.reload()

    def copy(self, value) -> None:
        self.root.clipboard_clear(); self.root.clipboard_append(value)
        self.status.set("Copied. Clipboard clears after 30 seconds if it still contains this value.")
        def clear():
            try:
                if self.root.clipboard_get() == value:
                    self.root.clipboard_clear()
            except tk.TclError:
                pass
        self.root.after(30000, clear)

    def paste(self, value) -> None:
        self.submit(self.browsers.type_value(self.selected(), value), "User-provided value typed into the focused browser field.")

    def save_path(self, p, suffix, extension):
        folder = Path(self.settings.values["export_folder"]); folder.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(initialdir=folder, initialfile=filename(p.name, suffix) + extension, defaultextension=extension, filetypes=[(extension.upper(), "*" + extension)], confirmoverwrite=False)
        if not path:
            return None
        path = Path(path)
        overwrite = path.exists()
        if overwrite and not messagebox.askyesno("Replace existing file?", f"Replace {path.name}?"):
            return None
        return path, overwrite

    def export_cookie(self) -> None:
        p = self.selected()
        if p.id not in self.browsers.ready:
            raise ValueError("Mark signup complete in this active session first.")
        if not messagebox.askyesno("WARNING", WARNING + "\n\nContinue?"):
            return
        format = simpledialog.askstring("Export Format", "JSON, TXT, or NETSCAPE:", initialvalue=self.settings.values["cookie_format"])
        if not format:
            return
        format = format.upper().strip()
        if format not in ("JSON", "TXT", "NETSCAPE"):
            raise ValueError("Choose JSON, TXT, or NETSCAPE.")
        extension = ".json" if format == "JSON" else ".txt"
        target = self.save_path(p, "Dola_Cookies", extension)
        if target:
            async def run():
                cookies = await self.browsers.context(p).cookies()
                await asyncio.to_thread(export_cookies, p, cookies, target[0], format, target[1])
            self.submit(run(), "Dola.com cookies exported. Store the file securely.")

    def export_all_cookies(self) -> None:
        profiles = self.db.list()
        if not profiles:
            raise ValueError("Create at least one profile first.")
        scope = messagebox.askyesnocancel(
            "Choose cookie scope",
            "Export cookies from every saved Edge and Chrome profile?\n\n"
            "Yes: all websites in each profile.\n"
            "No: Dola.com cookies only.\n"
            "Cancel: do nothing.",
        )
        if scope is None:
            return
        dola_only = not scope
        warning = WARNING if dola_only else (
            "Exporting all browser cookies can include active sessions for websites other than Dola.com. "
            "Store the files securely and never share them publicly."
        )
        if not messagebox.askyesno("Sensitive cookie export", warning + "\n\nInactive profiles will be opened briefly and then closed. Continue?"):
            return
        format = simpledialog.askstring("Export Format", "JSON, TXT, or NETSCAPE:", initialvalue=self.settings.values["cookie_format"])
        if not format:
            return
        format = format.upper().strip()
        if format not in ("JSON", "TXT", "NETSCAPE"):
            raise ValueError("Choose JSON, TXT, or NETSCAPE.")
        folder = filedialog.askdirectory(initialdir=self.settings.values["export_folder"], mustexist=False)
        if not folder:
            return
        destination = Path(folder)
        destination.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")

        async def run():
            saved, skipped = [], []
            for profile in profiles:
                was_active = self.browsers.active(profile.id)
                try:
                    context = await self.browsers.launch(profile, reuse=True)
                    cookies = await context.cookies()
                    suffix = ("Dola_Cookies" if dola_only else "All_Browser_Cookies") + "_" + timestamp
                    path = self.bulk_export_path(destination, profile, suffix, ".json" if format == "JSON" else ".txt")
                    await asyncio.to_thread(export_cookies, profile, cookies, path, format, False, dola_only)
                    saved.append(path.name)
                except ValueError as error:
                    skipped.append(f"{profile.name}: {error}")
                finally:
                    if not was_active and self.browsers.active(profile.id):
                        await self.browsers.close(profile)
            log.info("Bulk cookie export completed: %d saved, %d skipped", len(saved), len(skipped))
            return saved, skipped

        def display(result):
            saved, skipped = result
            self.status.set(f"Exported cookies from {len(saved)} of {len(profiles)} profiles to {destination}.")
            if skipped:
                messagebox.showwarning(
                    "Some cookie exports were skipped",
                    f"Exported {len(saved)} of {len(profiles)} profiles.\n\n" + "\n".join(skipped),
                )
        self.submit(run(), "Exporting cookies from saved profiles.", display)

    @staticmethod
    def bulk_export_path(folder: Path, profile, suffix: str, extension: str) -> Path:
        """Avoid overwriting a previous bulk export, even with duplicate display names."""
        base = filename(f"{profile.name}_{profile.id[-8:]}", suffix)
        candidate = folder / (base + extension)
        number = 2
        while candidate.exists():
            candidate = folder / f"{base}_{number}{extension}"
            number += 1
        return candidate

    def import_cookie(self) -> None:
        p = self.selected(); self.browsers.context(p)
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        cookies = load_cookies(Path(path))
        if messagebox.askyesno("Import cookies", f"Import cookies into '{p.name}'? Matching cookies will be replaced. These cookies may contain active sessions."):
            async def run():
                await self.browsers.context(p).add_cookies(cookies)
                log.info("Cookies imported: %s", p.id)
            self.submit(run(), "Cookies imported. Refresh the browser page to use them.")

    def export_browser_state(self) -> None:
        p = self.selected(); self.browsers.context(p)
        if not messagebox.askyesno("Sensitive browser state", WARNING + "\nBrowser state includes storage for all origins. Continue?"):
            return
        target = self.save_path(p, "Browser_State", ".json")
        if target:
            self.submit(export_state(self.browsers.context(p), target[0], target[1]), "Browser state exported securely.")

    def import_browser_state(self) -> None:
        p = self.selected(); self.browsers.context(p)
        path = filedialog.askopenfilename(filetypes=[("Playwright state JSON", "*.json")])
        if not path:
            return
        state = load_state(Path(path))
        if messagebox.askyesno("Replace browser state", f"Import into '{p.name}'?\n\nAll tabs will close. Cookies, local storage, IndexedDB and origin private files will be replaced. Export a backup first. Cache and preferences are not part of storage-state files."):
            async def run():
                await import_state(self.browsers.context(p), state)
                self.browsers.ready.discard(p.id)
                self.db.update(p.id, status="Active")
            self.submit(run(), "State imported. Reopen the website; confirm signup again before cookie export.")

    def build_settings(self, frame) -> None:
        self.preference_vars = {}
        choices = {"default_browser": list(BROWSERS), "cookie_format": ["JSON", "TXT", "NETSCAPE"], "theme": ["Light", "Dark"], "log_level": ["INFO", "WARNING", "ERROR"]}
        for key, label in (("default_browser", "Default Browser"), ("profile_folder", "Default Profile Folder"), ("export_folder", "Default Export Folder"), ("cookie_format", "Cookie Export Format"), ("theme", "Theme"), ("log_level", "Log Level")):
            row = ttk.Frame(frame); row.pack(fill="x", pady=7)
            ttk.Label(row, text=label, width=24).pack(side="left")
            variable = tk.StringVar(value=str(self.settings.values[key])); self.preference_vars[key] = variable
            widget = ttk.Combobox(row, textvariable=variable, values=choices[key], state="readonly", width=35) if key in choices else ttk.Entry(row, textvariable=variable, width=65)
            widget.pack(side="left")
            if key.endswith("folder"):
                def choose(v=variable):
                    directory = filedialog.askdirectory()
                    if directory:
                        v.set(directory)
                self.button(row, "Choose Folder", choose)
        self.auto_refresh = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="Auto Refresh After Signup (required to enable cookie export)", variable=self.auto_refresh, state="disabled").pack(anchor="w", pady=8)
        ttk.Label(frame, text="Mark Signup Complete always refreshes the Dola.com page before enabling cookie export.\nChanging the profile folder affects new profiles only.").pack(anchor="w", pady=15)
        row = ttk.Frame(frame); row.pack(fill="x")
        self.button(row, "Save Settings", self.save_settings)

    def save_settings(self) -> None:
        self.settings.save({key: v.get() for key, v in self.preference_vars.items()})
        self.browser.set(self.settings.values["default_browser"])
        logging.getLogger("app").setLevel(self.settings.values["log_level"])
        self.apply_theme(); self.status.set("Settings saved.")

    def quit(self) -> None:
        if self.busy:
            messagebox.showinfo("Operation in progress", "Wait for the current operation, then close the application.")
            return
        if self.browsers.contexts and not messagebox.askyesno("Close application", "Close all managed browser windows and exit?"):
            return
        self.busy = True
        future = self.worker.submit(self.browsers.shutdown())
        def finish():
            if not future.done():
                self.root.after(100, finish); return
            self.closing = True
            self.phone.set(""); self.otp.set("")
            self.worker.stop(); self.root.destroy()
        finish()
