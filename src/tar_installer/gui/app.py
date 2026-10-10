"""GTK 3 Graphical User Interface for Tar App Installer."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gtk, Gdk, GLib, GdkPixbuf

from ..core.archive import extract_archive, is_archive, ArchiveError
from ..core.detector import detect_app, clean_slug
from ..core.installer import AppInstaller, generate_fallback_svg_icon
from ..core.models import DetectedApp, InstallConfig, InstalledApp
from ..core.registry import AppRegistry


CATEGORIES = [
    "Utility",
    "Development",
    "Game",
    "Graphics",
    "AudioVideo",
    "Office",
    "Network",
    "System",
    "Education",
]

CSS_DATA = b"""
window {
    background-color: #f7f9fc;
}
.card {
    background-color: #ffffff;
    border-radius: 12px;
    border: 1px solid #e2e8f0;
    padding: 18px;
    margin-bottom: 12px;
}
.drop-zone {
    border: 2px dashed #cbd5e1;
    border-radius: 14px;
    background-color: #f8fafc;
    padding: 32px 16px;
    transition: all 200ms ease;
}
.drop-zone:hover {
    border-color: #3b82f6;
    background-color: #eff6ff;
}
.btn-primary {
    background: linear-gradient(135deg, #2563eb, #1d4ed8);
    color: white;
    font-weight: bold;
    border-radius: 8px;
    padding: 10px 24px;
    border: none;
}
.btn-primary:hover {
    background: linear-gradient(135deg, #1d4ed8, #1e40af);
}
.app-title {
    font-size: 16px;
    font-weight: 700;
    color: #1e293b;
}
.app-subtext {
    font-size: 12px;
    color: #64748b;
}
.badge {
    background-color: #e2e8f0;
    color: #334155;
    border-radius: 12px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 600;
}
.banner-success {
    background-color: #ecfdf5;
    border: 1px solid #a7f3d0;
    color: #065f46;
    border-radius: 8px;
    padding: 12px;
}
"""


def format_size(bytes_val: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if bytes_val < 1024.0:
            return f"{bytes_val:3.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} PB"


class TarInstallerWindow(Gtk.Window):
    def __init__(self, initial_archive: str | None = None):
        super().__init__(title="Tar App Installer")
        self.set_default_size(580, 680)
        self.set_position(Gtk.WindowPosition.CENTER)

        self._apply_css()

        # State
        self.temp_dir: tempfile.TemporaryDirectory | None = None
        self.current_archive: Path | None = None
        self.detected_app: DetectedApp | None = None
        self.selected_icon_path: str | None = None
        self.last_installed_app: InstalledApp | None = None

        # Build UI
        self._build_header()
        self._build_layout()

        if initial_archive and Path(initial_archive).is_file():
            GLib.idle_add(self._load_archive, Path(initial_archive))

    def _apply_css(self):
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CSS_DATA)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build_header(self):
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title("Tar App Installer")
        header.set_subtitle("Extract & install portable Linux apps")
        self.set_titlebar(header)

        # View Switcher
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(200)

        switcher = Gtk.StackSwitcher()
        switcher.set_stack(self.stack)
        header.set_custom_title(switcher)

    def _build_layout(self):
        self.add(self.stack)

        # Tab 1: Installer View
        install_scrolled = Gtk.ScrolledWindow()
        install_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.box_install_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.box_install_tab.set_margin_top(16)
        self.box_install_tab.set_margin_bottom(16)
        self.box_install_tab.set_margin_start(16)
        self.box_install_tab.set_margin_end(16)
        install_scrolled.add(self.box_install_tab)
        self.stack.add_titled(install_scrolled, "install", "Install Package")

        # Tab 2: Installed Apps View
        installed_scrolled = Gtk.ScrolledWindow()
        installed_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.box_installed_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.box_installed_tab.set_margin_top(16)
        self.box_installed_tab.set_margin_bottom(16)
        self.box_installed_tab.set_margin_start(16)
        self.box_installed_tab.set_margin_end(16)
        installed_scrolled.add(self.box_installed_tab)
        self.stack.add_titled(installed_scrolled, "manage", "Installed Apps")

        # Build tabs contents
        self._build_install_tab_content()
        self._build_manage_tab_content()

    def _build_install_tab_content(self):
        # 1. Drop Zone / File Chooser
        self.card_dropzone = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.card_dropzone.get_style_context().add_class("drop-zone")

        icon_box = Gtk.Image.new_from_icon_name("package-x-generic", Gtk.IconSize.DIALOG)
        self.card_dropzone.pack_start(icon_box, False, False, 0)

        lbl_drop = Gtk.Label(label="<b>Choose a package to install</b>", use_markup=True)
        lbl_drop.get_style_context().add_class("app-title")
        self.card_dropzone.pack_start(lbl_drop, False, False, 0)

        lbl_desc = Gtk.Label(label="Supports .tar.gz, .tgz, .tar.xz, .tar.bz2, and .zip archives")
        lbl_desc.get_style_context().add_class("app-subtext")
        self.card_dropzone.pack_start(lbl_desc, False, False, 0)

        btn_browse = Gtk.Button(label="📁 Browse Archive File...")
        btn_browse.connect("clicked", self._on_browse_clicked)
        btn_browse.set_halign(Gtk.Align.CENTER)
        self.card_dropzone.pack_start(btn_browse, False, False, 4)

        self.box_install_tab.pack_start(self.card_dropzone, False, False, 0)

        # 2. Progress Indicator (Hidden by default)
        self.box_progress = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.lbl_progress = Gtk.Label(label="Processing archive...")
        self.lbl_progress.get_style_context().add_class("app-subtext")
        self.progress_bar = Gtk.ProgressBar()
        self.box_progress.pack_start(self.lbl_progress, False, False, 0)
        self.box_progress.pack_start(self.progress_bar, False, False, 0)
        self.box_progress.set_no_show_all(True)
        self.box_install_tab.pack_start(self.box_progress, False, False, 0)

        # 3. Application Metadata Card (Hidden initially)
        self.card_meta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.card_meta.get_style_context().add_class("card")
        self.card_meta.set_no_show_all(True)
        self.box_install_tab.pack_start(self.card_meta, False, False, 0)

        # Top row: Icon + App Name
        row_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self.img_icon_preview = Gtk.Image()
        self.img_icon_preview.set_size_request(64, 64)
        row_top.pack_start(self.img_icon_preview, False, False, 0)

        col_name = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        lbl_field_name = Gtk.Label(label="Application Name:", xalign=0.0)
        lbl_field_name.get_style_context().add_class("app-subtext")
        self.entry_name = Gtk.Entry()
        self.entry_name.connect("changed", self._on_name_changed)
        col_name.pack_start(lbl_field_name, False, False, 0)
        col_name.pack_start(self.entry_name, False, False, 0)
        row_top.pack_start(col_name, True, True, 0)
        self.card_meta.pack_start(row_top, False, False, 0)

        # Grid of fields
        grid = Gtk.Grid()
        grid.set_column_spacing(16)
        grid.set_row_spacing(10)
        grid.set_margin_top(6)
        self.card_meta.pack_start(grid, False, False, 0)

        # Row 0: Version & Category
        lbl_ver = Gtk.Label(label="Version:", xalign=0.0)
        lbl_ver.get_style_context().add_class("app-subtext")
        self.entry_version = Gtk.Entry()
        grid.attach(lbl_ver, 0, 0, 1, 1)
        grid.attach(self.entry_version, 0, 1, 1, 1)

        lbl_cat = Gtk.Label(label="Category:", xalign=0.0)
        lbl_cat.get_style_context().add_class("app-subtext")
        self.combo_category = Gtk.ComboBoxText()
        for cat in CATEGORIES:
            self.combo_category.append_text(cat)
        self.combo_category.set_active(0)
        grid.attach(lbl_cat, 1, 0, 1, 1)
        grid.attach(self.combo_category, 1, 1, 1, 1)

        # Row 1: Executable selector
        lbl_exec = Gtk.Label(label="Main Executable:", xalign=0.0)
        lbl_exec.get_style_context().add_class("app-subtext")
        self.combo_exec = Gtk.ComboBoxText()
        grid.attach(lbl_exec, 0, 2, 2, 1)
        grid.attach(self.combo_exec, 0, 3, 2, 1)

        # Row 2: Description
        lbl_desc_f = Gtk.Label(label="Comment / Description:", xalign=0.0)
        lbl_desc_f.get_style_context().add_class("app-subtext")
        self.entry_comment = Gtk.Entry()
        grid.attach(lbl_desc_f, 0, 4, 2, 1)
        grid.attach(self.entry_comment, 0, 5, 2, 1)

        # Options Row: Install Scope & Terminal switch
        opts_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        opts_box.set_margin_top(4)

        self.radio_user = Gtk.RadioButton.new_with_label(None, "Current User (~/.local/share)")
        self.radio_system = Gtk.RadioButton.new_with_label_from_widget(self.radio_user, "System-Wide (/opt - root)")
        opts_box.pack_start(self.radio_user, False, False, 0)
        opts_box.pack_start(self.radio_system, False, False, 0)

        self.chk_terminal = Gtk.CheckButton(label="Launch in terminal")
        opts_box.pack_end(self.chk_terminal, False, False, 0)
        self.card_meta.pack_start(opts_box, False, False, 0)

        # Install Action Button
        self.btn_install_action = Gtk.Button(label="🚀 Install Application")
        self.btn_install_action.get_style_context().add_class("btn-primary")
        self.btn_install_action.connect("clicked", self._on_install_clicked)
        self.card_meta.pack_start(self.btn_install_action, False, False, 8)

        # Success Banner Card (Hidden initially)
        self.card_success = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.card_success.get_style_context().add_class("card")
        self.card_success.get_style_context().add_class("banner-success")
        self.card_success.set_no_show_all(True)

        self.lbl_success_title = Gtk.Label(label="<b>✓ Application Installed!</b>", use_markup=True, xalign=0.0)
        self.lbl_success_details = Gtk.Label(label="", xalign=0.0)
        self.lbl_success_details.set_line_wrap(True)

        row_success_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.btn_launch_installed = Gtk.Button(label="🚀 Launch Now")
        self.btn_launch_installed.connect("clicked", lambda _: self._launch_app(self.last_installed_app))
        self.btn_view_installed = Gtk.Button(label="📋 View in Installed Apps")
        self.btn_view_installed.connect("clicked", lambda _: self.stack.set_visible_child_name("manage"))
        row_success_btns.pack_start(self.btn_launch_installed, False, False, 0)
        row_success_btns.pack_start(self.btn_view_installed, False, False, 0)

        self.card_success.pack_start(self.lbl_success_title, False, False, 0)
        self.card_success.pack_start(self.lbl_success_details, False, False, 0)
        self.card_success.pack_start(row_success_btns, False, False, 4)
        self.box_install_tab.pack_start(self.card_success, False, False, 0)

    def _build_manage_tab_content(self):
        # Search & Refresh Bar
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.entry_search = Gtk.SearchEntry()
        self.entry_search.set_placeholder_text("Search installed apps...")
        self.entry_search.connect("search-changed", self._on_search_changed)
        top_bar.pack_start(self.entry_search, True, True, 0)

        btn_refresh = Gtk.Button(label="🔄")
        btn_refresh.set_tooltip_text("Refresh installed list")
        btn_refresh.connect("clicked", lambda _: self._refresh_installed_list())
        top_bar.pack_end(btn_refresh, False, False, 0)
        self.box_installed_tab.pack_start(top_bar, False, False, 0)

        # List of Installed Apps
        self.listbox_apps = Gtk.ListBox()
        self.listbox_apps.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox_apps.get_style_context().add_class("card")
        self.box_installed_tab.pack_start(self.listbox_apps, True, True, 0)

        # Populate initially
        self._refresh_installed_list()

    def _on_browse_clicked(self, _widget):
        dialog = Gtk.FileChooserDialog(
            title="Choose Application Archive",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK,
        )

        filter_archives = Gtk.FileFilter()
        filter_archives.set_name("Application Archives (*.tar.gz, *.tgz, *.tar.xz, *.zip)")
        filter_archives.add_pattern("*.tar.gz")
        filter_archives.add_pattern("*.tgz")
        filter_archives.add_pattern("*.tar.xz")
        filter_archives.add_pattern("*.txz")
        filter_archives.add_pattern("*.tar.bz2")
        filter_archives.add_pattern("*.tbz2")
        filter_archives.add_pattern("*.tar")
        filter_archives.add_pattern("*.zip")
        dialog.add_filter(filter_archives)

        filter_all = Gtk.FileFilter()
        filter_all.set_name("All Files")
        filter_all.add_pattern("*")
        dialog.add_filter(filter_all)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            selected_file = Path(dialog.get_filename())
            dialog.destroy()
            self._load_archive(selected_file)
        else:
            dialog.destroy()

    def _load_archive(self, archive_path: Path):
        self.current_archive = archive_path
        self.card_success.hide()
        self.card_meta.hide()
        self.box_progress.show()
        self.lbl_progress.set_text(f"Extracting & analyzing {archive_path.name}...")
        self.progress_bar.pulse()

        def background_task():
            try:
                temp_dir = tempfile.TemporaryDirectory(prefix="tar_gui_")
                tmp_path = Path(temp_dir.name)

                def on_progress(frac, fname):
                    GLib.idle_add(self._update_progress, frac, f"Extracting {Path(fname).name}...")

                extract_archive(archive_path, tmp_path, progress_callback=on_progress)
                detected = detect_app(tmp_path, source_archive_name=archive_path.name)
                GLib.idle_add(self._on_archive_analyzed, temp_dir, detected)
            except Exception as e:
                GLib.idle_add(self._on_archive_error, str(e))

        threading.Thread(target=background_task, daemon=True).start()

    def _update_progress(self, frac: float, msg: str):
        self.progress_bar.set_fraction(frac)
        self.lbl_progress.set_text(msg)

    def _on_archive_analyzed(self, temp_dir: tempfile.TemporaryDirectory, detected: DetectedApp):
        self.temp_dir = temp_dir
        self.detected_app = detected
        self.box_progress.hide()

        # Populate form
        self.entry_name.set_text(detected.name)
        self.entry_version.set_text(detected.version)
        self.entry_comment.set_text(detected.comment)
        self.chk_terminal.set_active(detected.terminal)

        # Category
        active_cat_idx = 0
        if detected.categories and detected.categories[0] in CATEGORIES:
            active_cat_idx = CATEGORIES.index(detected.categories[0])
        self.combo_category.set_active(active_cat_idx)

        # Executables ComboBox
        self.combo_exec.remove_all()
        selected_idx = 0
        for i, cand in enumerate(detected.candidates_exec):
            label = f"{cand.name}  ({cand.rel_path})"
            self.combo_exec.append_text(label)
            if cand.rel_path == detected.selected_exec:
                selected_idx = i
        if detected.candidates_exec:
            self.combo_exec.set_active(selected_idx)

        # Icon Preview
        self.selected_icon_path = detected.selected_icon
        self._update_icon_display()

        self.card_meta.show()

    def _on_archive_error(self, error_msg: str):
        self.box_progress.hide()
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Archive Extraction Failed",
        )
        dialog.format_secondary_text(error_msg)
        dialog.run()
        dialog.destroy()

    def _on_name_changed(self, _entry):
        if not self.selected_icon_path:
            self._update_icon_display()

    def _update_icon_display(self):
        icon_path = None
        if self.selected_icon_path and self.temp_dir:
            full_path = Path(self.temp_dir.name) / self.selected_icon_path
            if full_path.is_file():
                icon_path = full_path

        if icon_path and icon_path.is_file():
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(icon_path), 64, 64, True)
                self.img_icon_preview.set_from_pixbuf(pixbuf)
                return
            except Exception:
                pass

        # Fallback vector icon
        fallback_tmp = Path(tempfile.gettempdir()) / f"icon_preview_{clean_slug(self.entry_name.get_text())}.svg"
        generate_fallback_svg_icon(self.entry_name.get_text() or "A", fallback_tmp)
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(fallback_tmp), 64, 64, True)
            self.img_icon_preview.set_from_pixbuf(pixbuf)
        except Exception:
            self.img_icon_preview.set_from_icon_name("application-x-executable", Gtk.IconSize.DIALOG)

    def _on_install_clicked(self, _button):
        if not self.detected_app or not self.temp_dir:
            return

        exec_idx = self.combo_exec.get_active()
        if exec_idx < 0 or exec_idx >= len(self.detected_app.candidates_exec):
            return
        chosen_exec = self.detected_app.candidates_exec[exec_idx].rel_path

        app_name = self.entry_name.get_text().strip() or self.detected_app.name
        app_slug = clean_slug(app_name)
        app_version = self.entry_version.get_text().strip() or "1.0.0"
        app_cat = self.combo_category.get_active_text() or "Utility"
        app_comment = self.entry_comment.get_text().strip()
        system_wide = self.radio_system.get_active()
        terminal = self.chk_terminal.get_active()

        config = InstallConfig(
            app_name=app_name,
            app_slug=app_slug,
            version=app_version,
            comment=app_comment,
            categories=[app_cat],
            exec_rel_path=chosen_exec,
            icon_rel_path=self.selected_icon_path,
            terminal=terminal,
            system_wide=system_wide,
        )

        self.btn_install_action.set_sensitive(False)
        self.btn_install_action.set_label("Installing...")

        def install_task():
            try:
                installed, msg = AppInstaller.install(
                    extracted_root=Path(self.temp_dir.name),
                    detected=self.detected_app,
                    config=config,
                    source_archive=self.current_archive,
                )
                GLib.idle_add(self._on_install_success, installed, msg)
            except Exception as e:
                GLib.idle_add(self._on_install_failure, str(e))

        threading.Thread(target=install_task, daemon=True).start()

    def _on_install_success(self, installed: InstalledApp, msg: str):
        self.last_installed_app = installed
        self.btn_install_action.set_sensitive(True)
        self.btn_install_action.set_label("🚀 Install Application")
        self.card_meta.hide()

        self.lbl_success_details.set_markup(
            f"<b>{installed.name}</b> is ready to use!\n\n"
            f"• <b>Start Menu:</b> Added to system app menu\n"
            f"• <b>Terminal Command:</b> <code>{Path(installed.symlink_path).name}</code>\n"
            f"• <b>Location:</b> {installed.install_dir} ({format_size(installed.size_bytes)})"
        )
        self.card_success.show()
        self._refresh_installed_list()

    def _on_install_failure(self, err_msg: str):
        self.btn_install_action.set_sensitive(True)
        self.btn_install_action.set_label("🚀 Install Application")
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Installation Failed",
        )
        dialog.format_secondary_text(err_msg)
        dialog.run()
        dialog.destroy()

    def _refresh_installed_list(self):
        # Clear listbox
        for row in self.listbox_apps.get_children():
            self.listbox_apps.remove(row)

        search_query = self.entry_search.get_text().strip().lower()
        apps = AppRegistry.load_apps()

        filtered = [a for a in apps if not search_query or search_query in a.name.lower() or search_query in a.id.lower()]

        if not filtered:
            lbl_empty = Gtk.Label(label="No installed applications found.")
            lbl_empty.get_style_context().add_class("app-subtext")
            lbl_empty.set_margin_top(24)
            lbl_empty.set_margin_bottom(24)
            row = Gtk.ListBoxRow()
            row.add(lbl_empty)
            self.listbox_apps.add(row)
            self.listbox_apps.show_all()
            return

        for app in filtered:
            row = Gtk.ListBoxRow()
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            row_box.set_margin_top(8)
            row_box.set_margin_bottom(8)
            row_box.set_margin_start(12)
            row_box.set_margin_end(12)

            # Icon
            img = Gtk.Image()
            if app.icon_path and Path(app.icon_path).is_file():
                try:
                    pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(app.icon_path, 40, 40, True)
                    img.set_from_pixbuf(pb)
                except Exception:
                    img.set_from_icon_name("application-x-executable", Gtk.IconSize.LARGE_TOOLBAR)
            else:
                img.set_from_icon_name("application-x-executable", Gtk.IconSize.LARGE_TOOLBAR)
            row_box.pack_start(img, False, False, 0)

            # Info
            info_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            lbl_title = Gtk.Label(label=f"<b>{app.name}</b> <span size='smaller' color='#64748b'>v{app.version}</span>", use_markup=True, xalign=0.0)
            lbl_meta = Gtk.Label(label=f"{format_size(app.size_bytes)} • cmd: {Path(app.symlink_path).name}", xalign=0.0)
            lbl_meta.get_style_context().add_class("app-subtext")
            info_col.pack_start(lbl_title, False, False, 0)
            info_col.pack_start(lbl_meta, False, False, 0)
            row_box.pack_start(info_col, True, True, 0)

            # Buttons
            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

            btn_run = Gtk.Button(label="🚀 Launch")
            btn_run.connect("clicked", lambda _, a=app: self._launch_app(a))
            btn_box.pack_start(btn_run, False, False, 0)

            btn_folder = Gtk.Button(label="📁")
            btn_folder.set_tooltip_text("Open installation folder in Files")
            btn_folder.connect("clicked", lambda _, a=app: self._open_folder(a.install_dir))
            btn_box.pack_start(btn_folder, False, False, 0)

            btn_del = Gtk.Button(label="🗑️")
            btn_del.set_tooltip_text("Uninstall application")
            btn_del.connect("clicked", lambda _, a=app: self._on_uninstall_clicked(a))
            btn_box.pack_start(btn_del, False, False, 0)

            row_box.pack_end(btn_box, False, False, 0)
            row.add(row_box)
            self.listbox_apps.add(row)

        self.listbox_apps.show_all()

    def _on_search_changed(self, _entry):
        self._refresh_installed_list()

    def _launch_app(self, app: InstalledApp | None):
        if not app:
            return
        binary = app.binary_path or app.symlink_path
        if Path(binary).is_file():
            subprocess.Popen([binary], cwd=app.install_dir)

    def _open_folder(self, folder_path: str):
        if Path(folder_path).is_dir():
            subprocess.Popen(["xdg-open", folder_path])

    def _on_uninstall_clicked(self, app: InstalledApp):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Uninstall {app.name}?",
        )
        dialog.format_secondary_text(
            f"This will remove the application directory ({app.install_dir}), "
            "its start menu launcher, and command-line symlink."
        )
        res = dialog.run()
        dialog.destroy()

        if res == Gtk.ResponseType.YES:
            ok, msg = AppRegistry.uninstall(app.id)
            if not ok:
                err_diag = Gtk.MessageDialog(
                    transient_for=self,
                    flags=0,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Uninstall Error",
                )
                err_diag.format_secondary_text(msg)
                err_diag.run()
                err_diag.destroy()
            self._refresh_installed_list()


def main(archive_path: str | None = None):
    app = TarInstallerWindow(initial_archive=archive_path)
    app.connect("destroy", Gtk.main_quit)
    app.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
