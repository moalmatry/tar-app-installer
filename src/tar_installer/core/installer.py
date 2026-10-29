"""Installation coordinator for deploying extracted archives into system/user application dirs."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from .models import InstallConfig, InstalledApp, DetectedApp
from .registry import AppRegistry


def generate_fallback_svg_icon(app_name: str, dest_path: Path):
    """Generates a clean vector SVG icon using the application's initial letter."""
    initial = (app_name.strip()[:1] or "A").upper()
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Pick a vibrant hue based on app name hash
    hue = abs(hash(app_name)) % 360
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="hsl({hue}, 80%, 55%)" />
      <stop offset="100%" stop-color="hsl({(hue + 45) % 360}, 85%, 40%)" />
    </linearGradient>
  </defs>
  <rect width="256" height="256" rx="56" fill="url(#grad)" />
  <text x="128" y="165" font-family="system-ui, -apple-system, sans-serif" font-size="120" font-weight="bold" fill="#ffffff" text-anchor="middle">{initial}</text>
</svg>"""
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(svg)


def get_dir_size(path: Path) -> int:
    """Calculates total disk usage in bytes for a directory."""
    total = 0
    try:
        for root, _, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                if not os.path.islink(fp):
                    total += os.path.getsize(fp)
    except OSError:
        pass
    return total


class AppInstaller:
    """Installs extracted application packages into Linux desktop standard locations."""

    @classmethod
    def install(
        cls,
        extracted_root: Path,
        detected: DetectedApp,
        config: InstallConfig,
        source_archive: Path | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> tuple[InstalledApp, str]:
        """Performs full installation of the application package."""

        if progress_callback:
            progress_callback(0.1, "Preparing destination directories...")

        # 1. Determine installation paths
        if config.system_wide:
            install_base = Path("/opt")
            bin_dir = Path("/usr/local/bin")
            desktop_dir = Path("/usr/share/applications")
            pixmaps_dir = Path("/usr/share/pixmaps")
            hicolor_base = Path("/usr/share/icons/hicolor")
        else:
            install_base = Path.home() / ".local" / "share" / "tar-apps"
            bin_dir = Path.home() / ".local" / "bin"
            desktop_dir = Path.home() / ".local" / "share" / "applications"
            pixmaps_dir = Path.home() / ".local" / "share" / "pixmaps"
            hicolor_base = Path.home() / ".local" / "share" / "icons" / "hicolor"

        app_install_dir = install_base / config.app_slug
        bin_dir.mkdir(parents=True, exist_ok=True)
        desktop_dir.mkdir(parents=True, exist_ok=True)
        pixmaps_dir.mkdir(parents=True, exist_ok=True)
        (hicolor_base / "scalable" / "apps").mkdir(parents=True, exist_ok=True)

        # 2. Check if already installed; remove old version if upgrading
        if app_install_dir.exists():
            if progress_callback:
                progress_callback(0.2, f"Removing previous installation at {app_install_dir}...")
            shutil.rmtree(app_install_dir)

        # 3. Copy files to permanent location
        if progress_callback:
            progress_callback(0.3, "Copying files to destination...")

        # If archive had a single inner root, copy from inner root to avoid nesting
        if detected.inner_root and (extracted_root / detected.inner_root).is_dir():
            src_files = extracted_root / detected.inner_root
        else:
            src_files = extracted_root

        shutil.copytree(src_files, app_install_dir, symlinks=True)

        if progress_callback:
            progress_callback(0.6, "Configuring executables and permissions...")

        # 4. Locate and configure binary
        # Calculate relative path from src_files to the binary
        exec_rel = config.exec_rel_path
        if detected.inner_root and exec_rel.startswith(f"{detected.inner_root}/"):
            exec_rel = exec_rel[len(detected.inner_root) + 1 :]

        target_binary = app_install_dir / exec_rel
        if not target_binary.is_file():
            # Fallback search if path mismatch
            target_binary = app_install_dir / Path(config.exec_rel_path).name
            if not target_binary.is_file():
                # Pick any executable in root
                for p in app_install_dir.iterdir():
                    if p.is_file() and os.access(p, os.X_OK):
                        target_binary = p
                        break

        # Ensure executable bit
        try:
            mode = os.stat(target_binary).st_mode
            os.chmod(target_binary, mode | 0o755)
        except OSError:
            pass

        # 5. Create binary symlink in bin/
        symlink_path = bin_dir / config.app_slug
        if symlink_path.is_symlink() or symlink_path.exists():
            try:
                os.remove(symlink_path)
            except OSError:
                pass

        try:
            os.symlink(target_binary, symlink_path)
        except OSError:
            pass

        if progress_callback:
            progress_callback(0.75, "Setting up icon and desktop launcher...")

        # 6. Setup Icon
        final_icon_path: str | None = None
        source_icon: Path | None = None

        if config.custom_icon_path and Path(config.custom_icon_path).is_file():
            source_icon = Path(config.custom_icon_path)
        elif config.icon_rel_path:
            icon_rel = config.icon_rel_path
            if detected.inner_root and icon_rel.startswith(f"{detected.inner_root}/"):
                icon_rel = icon_rel[len(detected.inner_root) + 1 :]

            candidate_paths = [
                app_install_dir / icon_rel,
                extracted_root / config.icon_rel_path,
                extracted_root / icon_rel,
                app_install_dir / Path(config.icon_rel_path).name,
            ]
            for cand in candidate_paths:
                if cand.is_file():
                    source_icon = cand
                    break

        if source_icon and source_icon.is_file():
            ext = source_icon.suffix.lower()

            if ext == ".svg":
                dest_pixmap = pixmaps_dir / f"{config.app_slug}.svg"
                dest_hicolor = hicolor_base / "scalable" / "apps" / f"{config.app_slug}.svg"
                dest_hicolor.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_icon, dest_pixmap)
                shutil.copy2(source_icon, dest_hicolor)
                try:
                    os.chmod(dest_pixmap, 0o644)
                    os.chmod(dest_hicolor, 0o644)
                except OSError:
                    pass
                final_icon_path = str(dest_pixmap)
            elif ext == ".ico":
                # Convert ICO to PNG for Linux desktop environments
                dest_pixmap = pixmaps_dir / f"{config.app_slug}.png"
                converted = False
                try:
                    import gi
                    gi.require_version("GdkPixbuf", "2.0")
                    from gi.repository import GdkPixbuf
                    pb = GdkPixbuf.Pixbuf.new_from_file(str(source_icon))
                    pb.savev(str(dest_pixmap), "png", [], [])
                    w, h = pb.get_width(), pb.get_height()
                    size = w if w in (16, 24, 32, 48, 64, 128, 256, 512) else 256
                    dest_hicolor = hicolor_base / f"{size}x{size}" / "apps" / f"{config.app_slug}.png"
                    dest_hicolor.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dest_pixmap, dest_hicolor)
                    try:
                        os.chmod(dest_pixmap, 0o644)
                        os.chmod(dest_hicolor, 0o644)
                    except OSError:
                        pass
                    final_icon_path = str(dest_pixmap)
                    converted = True
                except Exception:
                    pass

                if not converted:
                    dest_pixmap = pixmaps_dir / f"{config.app_slug}.svg"
                    dest_hicolor = hicolor_base / "scalable" / "apps" / f"{config.app_slug}.svg"
                    dest_hicolor.parent.mkdir(parents=True, exist_ok=True)
                    generate_fallback_svg_icon(config.app_name, dest_pixmap)
                    shutil.copy2(dest_pixmap, dest_hicolor)
                    try:
                        os.chmod(dest_pixmap, 0o644)
                        os.chmod(dest_hicolor, 0o644)
                    except OSError:
                        pass
                    final_icon_path = str(dest_pixmap)
            elif ext in (".png", ".xpm", ".jpg", ".jpeg", ".webp"):
                dest_pixmap = pixmaps_dir / f"{config.app_slug}.png"
                copied = False
                if ext != ".png":
                    try:
                        import gi
                        gi.require_version("GdkPixbuf", "2.0")
                        from gi.repository import GdkPixbuf
                        pb = GdkPixbuf.Pixbuf.new_from_file(str(source_icon))
                        pb.savev(str(dest_pixmap), "png", [], [])
                        copied = True
                    except Exception:
                        pass
                if not copied:
                    shutil.copy2(source_icon, dest_pixmap)

                w, h = 0, 0
                try:
                    from .detector import get_png_dimensions
                    w, h = get_png_dimensions(dest_pixmap)
                except Exception:
                    pass

                if w <= 0:
                    try:
                        import gi
                        gi.require_version("GdkPixbuf", "2.0")
                        from gi.repository import GdkPixbuf
                        pb = GdkPixbuf.Pixbuf.new_from_file(str(dest_pixmap))
                        w, h = pb.get_width(), pb.get_height()
                    except Exception:
                        w, h = 256, 256

                if w >= 512:
                    size = 512
                elif w >= 256:
                    size = 256
                elif w >= 128:
                    size = 128
                elif w >= 64:
                    size = 64
                elif w >= 48:
                    size = 48
                elif w >= 32:
                    size = 32
                elif w >= 24:
                    size = 24
                elif w >= 16:
                    size = 16
                else:
                    size = 256

                dest_hicolor = hicolor_base / f"{size}x{size}" / "apps" / f"{config.app_slug}.png"
                dest_hicolor.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest_pixmap, dest_hicolor)
                try:
                    os.chmod(dest_pixmap, 0o644)
                    os.chmod(dest_hicolor, 0o644)
                except OSError:
                    pass
                final_icon_path = str(dest_pixmap)
            else:
                dest_pixmap = pixmaps_dir / f"{config.app_slug}{ext}"
                shutil.copy2(source_icon, dest_pixmap)
                try:
                    os.chmod(dest_pixmap, 0o644)
                except OSError:
                    pass
                final_icon_path = str(dest_pixmap)
        else:
            # Generate fallback vector icon
            dest_pixmap = pixmaps_dir / f"{config.app_slug}.svg"
            dest_hicolor = hicolor_base / "scalable" / "apps" / f"{config.app_slug}.svg"
            dest_hicolor.parent.mkdir(parents=True, exist_ok=True)
            generate_fallback_svg_icon(config.app_name, dest_pixmap)
            shutil.copy2(dest_pixmap, dest_hicolor)
            try:
                os.chmod(dest_pixmap, 0o644)
                os.chmod(dest_hicolor, 0o644)
            except OSError:
                pass
            final_icon_path = str(dest_pixmap)

        # 7. Generate FreeDesktop .desktop entry
        categories_str = ";".join(config.categories)
        if not categories_str.endswith(";"):
            categories_str += ";"

        terminal_str = "true" if config.terminal else "false"
        desktop_file_path = desktop_dir / f"{config.app_slug}.desktop"

        # Explicit absolute path guarantees that all Linux file managers, docks, and app menus render the icon
        icon_ref = final_icon_path or config.app_slug

        desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name={config.app_name}
Comment={config.comment or config.app_name}
Exec={symlink_path} %U
Icon={icon_ref}
Path={app_install_dir}
Terminal={terminal_str}
StartupNotify=true
Categories={categories_str}
"""
        with open(desktop_file_path, "w", encoding="utf-8") as f:
            f.write(desktop_content)
        os.chmod(desktop_file_path, 0o644)

        if progress_callback:
            progress_callback(0.9, "Updating desktop database and icon caches...")

        # 8. Trigger desktop and icon cache updates
        try:
            subprocess.run(["update-desktop-database", str(desktop_dir)], check=False, capture_output=True)
            if shutil.which("gtk-update-icon-cache"):
                if hicolor_base.is_dir():
                    subprocess.run(["gtk-update-icon-cache", "-q", "-t", str(hicolor_base)], check=False, capture_output=True)
        except Exception:
            pass

        # 9. Register in AppRegistry
        installed_record = InstalledApp(
            id=config.app_slug,
            name=config.app_name,
            version=config.version,
            comment=config.comment,
            categories=config.categories,
            install_dir=str(app_install_dir),
            binary_path=str(target_binary),
            symlink_path=str(symlink_path),
            desktop_file=str(desktop_file_path),
            icon_path=final_icon_path,
            installed_at=time.time(),
            archive_source=str(source_archive) if source_archive else None,
            size_bytes=get_dir_size(app_install_dir),
        )
        AppRegistry.register_app(installed_record, system_wide=config.system_wide)

        if progress_callback:
            progress_callback(1.0, f"{config.app_name} successfully installed!")

        return installed_record, f"Successfully installed {config.app_name}!"
