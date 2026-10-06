"""Windows desktop entry point."""
from pathlib import Path
import argparse
import logging
from logging.handlers import RotatingFileHandler
import tkinter as tk
from tkinter import messagebox
from app.database import Database
from app.settings import Settings
from app.profile_manager import ProfileManager


def acquire_lock(path: Path):
    """Hold an OS lock so a second app cannot race profile lifecycle operations."""
    handle = path.open("a+b")
    try:
        import os
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            if not handle.read(1):
                handle.write(b"0"); handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise ValueError("The application is already running for this data folder.") from None
    return handle


def main() -> None:
    parser = argparse.ArgumentParser(description="Dola.com local browser profile manager")
    parser.add_argument("--data-root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root_folder = args.data_root.expanduser().resolve()
    for name in ("data", "profiles", "exports", "imports", "logs"):
        (root_folder / name).mkdir(parents=True, exist_ok=True)
    try:
        instance_lock = acquire_lock(root_folder / "data" / "app.lock")
    except ValueError as error:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Already running", str(error)); root.destroy(); return
    handler = RotatingFileHandler(root_folder / "logs" / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    app_logger = logging.getLogger("app")
    app_logger.addHandler(handler)
    app_logger.setLevel(logging.INFO)
    root = tk.Tk()
    try:
        database = Database(root_folder / "data" / "app.db")
        settings = Settings(database, root_folder)
        app_logger.setLevel(settings.values["log_level"])
        from app.gui import Application
        Application(root, database, settings, ProfileManager(database, settings))
        root.mainloop()
    except Exception as error:
        app_logger.error("Application startup failed: %s", type(error).__name__)
        messagebox.showerror("Startup failed", "Unable to start. Check dependencies and write permissions for the data folder.")
        root.destroy()
    finally:
        instance_lock.close()


if __name__ == "__main__":
    main()
