"""Application registry for tracking and managing installed tar apps."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from .models import InstalledApp


class AppRegistry:
    """Manages the database of installed tar applications."""

    USER_DATA_DIR = Path.home() / ".local" / "share" / "tar-apps"
    SYSTEM_DATA_DIR = Path("/var/lib/tar-apps")

    @classmethod
    def get_registry_file(cls, system_wide: bool = False) -> Path:
        if system_wide:
            return cls.SYSTEM_DATA_DIR / "registry.json"
        return cls.USER_DATA_DIR / "registry.json"

    @classmethod
    def load_apps(cls) -> list[InstalledApp]:
        """Loads all installed applications from both user and system registries."""
        apps: dict[str, InstalledApp] = {}

        # 1. System registry
        sys_file = cls.get_registry_file(system_wide=True)
        if sys_file.is_file():
            try:
                with open(sys_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("apps", []):
                        app = InstalledApp.from_dict(item)
                        apps[app.id] = app
            except Exception:
                pass

        # 2. User registry (takes precedence)
        user_file = cls.get_registry_file(system_wide=False)
        if user_file.is_file():
            try:
                with open(user_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("apps", []):
                        app = InstalledApp.from_dict(item)
                        apps[app.id] = app
            except Exception:
                pass

        return sorted(apps.values(), key=lambda a: a.name.lower())

    @classmethod
    def find_app(cls, app_id_or_name: str) -> InstalledApp | None:
        """Finds an installed app by ID or exact/case-insensitive name."""
        query = app_id_or_name.strip().lower()
        for app in cls.load_apps():
            if app.id.lower() == query or app.name.lower() == query:
                return app
        return None

    @classmethod
    def register_app(cls, app: InstalledApp, system_wide: bool = False):
        """Saves a new or updated app record into the registry."""
        reg_file = cls.get_registry_file(system_wide)
        reg_file.parent.mkdir(parents=True, exist_ok=True)

        current_apps: dict[str, InstalledApp] = {}
        if reg_file.is_file():
            try:
                with open(reg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("apps", []):
                        a = InstalledApp.from_dict(item)
                        current_apps[a.id] = a
            except Exception:
                pass

        current_apps[app.id] = app

        with open(reg_file, "w", encoding="utf-8") as f:
            json.dump(
                {"apps": [a.to_dict() for a in current_apps.values()]},
                f,
                indent=2,
            )

    @classmethod
    def unregister_app(cls, app_id: str, system_wide: bool = False):
        """Removes an app record from the registry."""
        reg_file = cls.get_registry_file(system_wide)
        if not reg_file.is_file():
            return

        current_apps: dict[str, InstalledApp] = {}
        try:
            with open(reg_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.get("apps", []):
                    a = InstalledApp.from_dict(item)
                    if a.id != app_id:
                        current_apps[a.id] = a

            with open(reg_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"apps": [a.to_dict() for a in current_apps.values()]},
                    f,
                    indent=2,
                )
        except Exception:
            pass

    @classmethod
    def uninstall(cls, app_id_or_name: str) -> tuple[bool, str]:
        """Completely removes an installed application and all its components."""
        app = cls.find_app(app_id_or_name)
        if not app:
            return False, f"Application '{app_id_or_name}' not found."

        system_wide = app.install_dir.startswith("/opt")
        errors: list[str] = []

        # 1. Remove binary symlink
        if app.symlink_path and os.path.islink(app.symlink_path):
            try:
                os.remove(app.symlink_path)
            except OSError as e:
                errors.append(f"Symlink removal failed: {e}")

        # 2. Remove .desktop file
        if app.desktop_file and os.path.isfile(app.desktop_file):
            try:
                os.remove(app.desktop_file)
            except OSError as e:
                errors.append(f"Desktop entry removal failed: {e}")

        # 3. Remove icon if installed
        if app.icon_path and os.path.isfile(app.icon_path):
            try:
                os.remove(app.icon_path)
            except OSError:
                pass

        # Also cleanup any matching icons across pixmaps and hicolor sizes
        search_bases = [Path("/usr/share")] if system_wide else [Path.home() / ".local" / "share", Path("/usr/share")]
        for base in search_bases:
            for ext in (".png", ".svg", ".ico", ".xpm"):
                pix_f = base / "pixmaps" / f"{app.id}{ext}"
                if pix_f.is_file():
                    try:
                        pix_f.unlink()
                    except OSError:
                        pass
            hicolor = base / "icons" / "hicolor"
            if hicolor.is_dir():
                for icon_f in hicolor.glob(f"*/apps/{app.id}.*"):
                    try:
                        icon_f.unlink()
                    except OSError:
                        pass

        # 4. Remove installation directory
        if app.install_dir and os.path.isdir(app.install_dir):
            try:
                shutil.rmtree(app.install_dir)
            except OSError as e:
                errors.append(f"Install directory removal failed: {e}")

        # 5. Remove from registry
        cls.unregister_app(app.id, system_wide=system_wide)

        # 6. Update desktop database and icon caches
        try:
            target_dt = Path("/usr/share/applications") if system_wide else Path.home() / ".local" / "share" / "applications"
            if target_dt.is_dir():
                subprocess.run(["update-desktop-database", str(target_dt)], check=False, capture_output=True)
            if shutil.which("gtk-update-icon-cache"):
                icon_dir = Path("/usr/share/icons/hicolor") if system_wide else Path.home() / ".local" / "share" / "icons" / "hicolor"
                if icon_dir.is_dir():
                    subprocess.run(["gtk-update-icon-cache", "-q", "-t", str(icon_dir)], check=False, capture_output=True)
        except Exception:
            pass

        if errors:
            return False, f"Partially removed {app.name}: {'; '.join(errors)}"
        return True, f"Successfully uninstalled {app.name}."
