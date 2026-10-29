"""Command-line interface for Tar App Installer."""
from __future__ import annotations

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ..core.archive import extract_archive, is_archive, parse_archive_argument, ArchiveError
from ..core.detector import detect_app, clean_slug
from ..core.installer import AppInstaller
from ..core.models import InstallConfig
from ..core.registry import AppRegistry


def format_size(bytes_val: int) -> str:
    """Formats bytes into human readable MB/GB string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if bytes_val < 1024.0:
            return f"{bytes_val:3.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} PB"


def cmd_install(args: argparse.Namespace):
    archive_path = parse_archive_argument(args.archive)
    if not archive_path or not archive_path.is_file():
        print(f"[✗] Error: File '{args.archive}' does not exist or is not a valid file.", file=sys.stderr)
        sys.exit(1)

    if not is_archive(archive_path):
        print(f"[✗] Error: '{archive_path.name}' is not a supported archive (.tar.gz, .tgz, .tar.xz, .zip).", file=sys.stderr)
        sys.exit(1)

    print(f"📦 Inspecting package: {archive_path.name}...")

    with tempfile.TemporaryDirectory(prefix="tar_install_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 1. Extract to temp
        try:
            print("  [1/3] Extracting archive...")
            extract_archive(archive_path, tmp_path)
        except ArchiveError as e:
            print(f"[✗] Extraction failed: {e}", file=sys.stderr)
            sys.exit(1)

        # 2. Detect
        print("  [2/3] Analyzing application structure...")
        detected = detect_app(tmp_path, source_archive_name=archive_path.name)

        if not detected.candidates_exec:
            print(f"[✗] Error: Could not find any executable binary in '{archive_path.name}'.", file=sys.stderr)
            sys.exit(1)

        # Apply CLI overrides if specified
        final_name = args.name or detected.name
        final_slug = clean_slug(args.name or detected.slug)
        final_version = args.version or detected.version
        final_exec = args.exec or detected.selected_exec
        final_icon = args.icon or detected.selected_icon
        final_categories = [args.category] if args.category else detected.categories
        system_wide = bool(args.system)

        # Validate chosen exec exists
        exec_full = tmp_path / final_exec
        if not exec_full.is_file():
            # Check relative to inner root
            if detected.inner_root and (tmp_path / detected.inner_root / final_exec).is_file():
                final_exec = f"{detected.inner_root}/{final_exec}"
            else:
                print(f"[✗] Error: Specified executable '{final_exec}' not found in archive.", file=sys.stderr)
                sys.exit(1)

        print("\n" + "=" * 55)
        print("           Application Installation Summary            ")
        print("=" * 55)
        print(f"  Name:        {final_name}")
        print(f"  Slug:        {final_slug}")
        print(f"  Version:     {final_version}")
        print(f"  Binary:      {final_exec}")
        print(f"  Icon:        {final_icon or '(Will generate clean vector icon)'}")
        print(f"  Category:    {', '.join(final_categories)}")
        print(f"  Scope:       {'System-wide (/opt)' if system_wide else 'User (~/.local/share/tar-apps)'}")
        print("=" * 55 + "\n")

        # Interactive confirmation if not -y / --yes
        if not args.yes and sys.stdin.isatty():
            ans = input("Proceed with installation? [Y/n]: ").strip().lower()
            if ans in ("n", "no"):
                print("Installation cancelled.")
                sys.exit(0)

        # 3. Perform Installation
        print("  [3/3] Installing application into system...")
        config = InstallConfig(
            app_name=final_name,
            app_slug=final_slug,
            version=final_version,
            comment=detected.comment,
            categories=final_categories,
            exec_rel_path=final_exec,
            icon_rel_path=final_icon,
            system_wide=system_wide,
            terminal=args.terminal or detected.terminal,
        )

        try:
            installed, msg = AppInstaller.install(
                extracted_root=tmp_path,
                detected=detected,
                config=config,
                source_archive=archive_path,
            )
            print(f"\n[✓] {msg}")
            print(f"  • Launcher:   {installed.desktop_file}")
            print(f"  • Command:    {installed.symlink_path} (Run from any terminal!)")
            print(f"  • Installed:  {installed.install_dir} ({format_size(installed.size_bytes)})")
            print(f"\n🚀 {final_name} is now available in your Start Menu and Application Launcher!")
        except Exception as e:
            print(f"[✗] Installation failed: {e}", file=sys.stderr)
            sys.exit(1)


def cmd_list(args: argparse.Namespace):
    apps = AppRegistry.load_apps()
    if not apps:
        print("No applications currently installed via Tar App Installer.")
        return

    print("=" * 75)
    print(f"{'NAME':<20} {'VERSION':<10} {'SIZE':<10} {'COMMAND':<20} {'INSTALLED'}")
    print("=" * 75)
    for a in apps:
        date_str = datetime.datetime.fromtimestamp(a.installed_at).strftime("%Y-%m-%d") if a.installed_at else "-"
        cmd_name = Path(a.symlink_path).name if a.symlink_path else a.id
        print(f"{a.name:<20} {a.version:<10} {format_size(a.size_bytes):<10} {cmd_name:<20} {date_str}")
    print("=" * 75)
    print(f"Total installed: {len(apps)} app(s)")


def cmd_remove(args: argparse.Namespace):
    app_id_or_name = args.app
    app = AppRegistry.find_app(app_id_or_name)
    if not app:
        print(f"[✗] Error: App '{app_id_or_name}' not found.", file=sys.stderr)
        sys.exit(1)

    if not args.yes and sys.stdin.isatty():
        ans = input(f"Are you sure you want to uninstall '{app.name}'? [y/N]: ").strip().lower()
        if ans not in ("y", "yes"):
            print("Cancelled.")
            sys.exit(0)

    ok, msg = AppRegistry.uninstall(app.id)
    if ok:
        print(f"[✓] {msg}")
    else:
        print(f"[✗] {msg}", file=sys.stderr)
        sys.exit(1)


def cmd_info(args: argparse.Namespace):
    app = AppRegistry.find_app(args.app)
    if not app:
        print(f"[✗] Error: App '{args.app}' not found.", file=sys.stderr)
        sys.exit(1)

    date_str = datetime.datetime.fromtimestamp(app.installed_at).strftime("%Y-%m-%d %H:%M:%S") if app.installed_at else "-"
    print("=" * 60)
    print(f"  Application Info: {app.name}")
    print("=" * 60)
    print(f"  ID:          {app.id}")
    print(f"  Version:     {app.version}")
    print(f"  Category:    {', '.join(app.categories)}")
    print(f"  Location:    {app.install_dir}")
    print(f"  Binary:      {app.binary_path}")
    print(f"  CLI Command: {app.symlink_path}")
    print(f"  Desktop:     {app.desktop_file}")
    print(f"  Icon:        {app.icon_path or 'N/A'}")
    print(f"  Disk Size:   {format_size(app.size_bytes)}")
    print(f"  Installed:   {date_str}")
    if app.archive_source:
        print(f"  Source:      {app.archive_source}")
    print("=" * 60)


def cmd_launch(args: argparse.Namespace):
    app = AppRegistry.find_app(args.app)
    if not app:
        print(f"[✗] Error: App '{args.app}' not found.", file=sys.stderr)
        sys.exit(1)

    binary = app.binary_path or app.symlink_path
    if not Path(binary).is_file():
        print(f"[✗] Error: Executable '{binary}' not found.", file=sys.stderr)
        sys.exit(1)

    print(f"🚀 Launching {app.name}...")
    subprocess.Popen([binary] + args.extra_args, cwd=app.install_dir)


def cmd_gui(args: argparse.Namespace):
    from ..gui.app import main as gui_main
    gui_main(archive_path=args.archive)


def main():
    parser = argparse.ArgumentParser(
        prog="tar-installer",
        description="Extract and automatically install .tar.gz, .tgz, .tar.xz, and .zip applications into your Linux Apps menu.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # install
    p_install = subparsers.add_parser("install", help="Extract and install an application archive")
    p_install.add_argument("archive", help="Path to .tar.gz, .tgz, .tar.xz, or .zip file")
    p_install.add_argument("-n", "--name", help="Custom application name")
    p_install.add_argument("-e", "--exec", help="Relative path to main executable inside archive")
    p_install.add_argument("-c", "--category", help="Desktop category (e.g. Development, Utility, Game, Graphics)")
    p_install.add_argument("-i", "--icon", help="Path to custom icon or relative path inside archive")
    p_install.add_argument("-v", "--version", help="Application version string")
    p_install.add_argument("-s", "--system", action="store_true", help="Install system-wide to /opt (requires root/sudo)")
    p_install.add_argument("-t", "--terminal", action="store_true", help="Run application in a terminal window")
    p_install.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    # list
    subparsers.add_parser("list", help="List all applications installed via Tar App Installer")

    # remove
    p_remove = subparsers.add_parser("remove", aliases=["uninstall"], help="Uninstall an application")
    p_remove.add_argument("app", help="Application name or ID")
    p_remove.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")

    # info
    p_info = subparsers.add_parser("info", help="Show details of an installed application")
    p_info.add_argument("app", help="Application name or ID")

    # launch
    p_launch = subparsers.add_parser("launch", aliases=["run"], help="Launch an installed application")
    p_launch.add_argument("app", help="Application name or ID")
    p_launch.add_argument("extra_args", nargs="*", help="Arguments passed to the application")

    # gui
    p_gui = subparsers.add_parser("gui", help="Open graphical user interface")
    p_gui.add_argument("archive", nargs="?", help="Optional archive path to pre-load in GUI")

    # If first argument looks like an archive file without subcommand, route to install
    if len(sys.argv) > 1 and sys.argv[1] not in ("-h", "--help", "install", "list", "remove", "uninstall", "info", "launch", "run", "gui"):
        potential_file = parse_archive_argument(sys.argv[1])
        if potential_file and is_archive(potential_file):
            sys.argv[1] = str(potential_file)
            sys.argv.insert(1, "install")

    args = parser.parse_args()

    if not args.command:
        # If no arguments given, open GUI if in graphical environment, else print help
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            cmd_gui(argparse.Namespace(archive=None))
            return
        parser.print_help()
        sys.exit(0)

    if args.command == "install":
        cmd_install(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command in ("remove", "uninstall"):
        cmd_remove(args)
    elif args.command == "info":
        cmd_info(args)
    elif args.command in ("launch", "run"):
        cmd_launch(args)
    elif args.command == "gui":
        cmd_gui(args)


if __name__ == "__main__":
    main()
