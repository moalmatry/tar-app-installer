# Tar App Installer for Linux 📦🚀

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-brightgreen.svg)](https://www.python.org/)
[![Platform: Linux](https://img.shields.io/badge/platform-Linux-orange.svg)](https://www.kernel.org/)
[![Interface: GTK 3](https://img.shields.io/badge/GUI-GTK%203-blueviolet.svg)](https://www.gtk.org/)
[![Poetry Managed](https://img.shields.io/badge/packaging-poetry-cyan.svg)](https://python-poetry.org/)

**Tar App Installer** is a native, modern Linux application and CLI tool that automatically extracts `.tar.gz`, `.tgz`, `.tar.xz`, `.tar.bz2`, and `.zip` archives, detects the main executable and icon, installs the files into your system, and seamlessly adds the application to your **Start Menu / App Launcher** and `$PATH`.

---

## 💡 The Problem It Solves

When you download portable Linux software as a `.tar.gz` archive (such as Blender, Postman, Discord, Godot, Tor Browser, Obsidian, Android Studio, or custom tools), Linux does not provide an automatic installer:

1. You manually extract the archive to `Downloads/`.
2. There is **no launcher in your Start Menu**.
3. If you move or delete your `Downloads` folder, the app breaks.
4. You cannot launch it from terminal without typing the full path.
5. You have to manually write FreeDesktop `.desktop` files, set permissions, hunt for icon files, and configure categories.

**Tar App Installer automates the entire workflow in seconds.** Either right-click any `.tar.gz` file, use the sleek GTK3 graphical interface, or run a single command in your terminal.

---

## 🌟 Key Features

* **⚡ 1-Click Desktop & Menu Integration:**
  * Extracts the archive safely to permanent application storage (`~/.local/share/tar-apps/<app>` or `/opt/<app>`).
  * Generates a fully compliant FreeDesktop `.desktop` launcher in `~/.local/share/applications/` so it immediately appears in your Zorin OS / GNOME / KDE start menu.
  * Creates an instant command-line symlink in `~/.local/bin/` so you can launch it from any terminal.
* **🧠 Smart Detection Engine:**
  * **Executable Identification:** Uses ELF binary parsing, shebang detection, and heuristic scoring to locate the real application entry point while filtering out helper libraries (`lib*.so`, crashpad, sandbox).
  * **Icon Discovery:** Scans for embedded `.svg` vectors and high-resolution `.png` icons. If no icon exists, generates a modern vector lettermark icon automatically.
  * **Existing Metadata Support:** If the archive already includes an internal `.desktop` file, its Name, Comment, and Categories are automatically parsed and adapted.
* **🖥️ Native GTK 3 Interface (`tar-installer-gui`):**
  * Built to match the aesthetics of Zorin OS and modern GNOME desktops.
  * Drag-and-drop or file picker for instant archive inspection.
  * Visual metadata editor: tweak app name, version, category, or executable before installing.
  * **Installed Apps Manager:** View all installed apps, disk size, launch them, open their folders in Files, or completely uninstall them with 1-click.
* **💻 Powerful Command-Line Tool (`tar-installer`):**
  * Single command installation: `tar-installer install app.tar.gz`
  * List all installed apps: `tar-installer list`
  * Complete uninstallation: `tar-installer remove app-name`
  * Launch or inspect installed packages: `tar-installer launch app-name`
* **🛡️ Security & Integrity:**
  * Path traversal / Zip-Slip protection on all extractions.
  * Installs into user space (`~/.local/share/tar-apps`) without needing root or `sudo` permissions (system-wide `/opt` mode is also available).
* **📁 File Manager Integration:**
  * Associates with archive MIME types so you can right-click any `.tar.gz` in Nautilus / Files and choose **"Open With -> Tar App Installer"**.

---

## 📦 Supported Archive Formats

| Format | Extensions |
| :--- | :--- |
| **Gzip Tarball** | `.tar.gz`, `.tgz` |
| **XZ Tarball** | `.tar.xz`, `.txz` |
| **Bzip2 Tarball** | `.tar.bz2`, `.tbz2` |
| **Standard Tar** | `.tar` |
| **Zip Archive** | `.zip` |

---

## 🚀 Quick Installation

### Prerequisites
* Python 3.10+
* Poetry package manager (`sudo apt install python3-poetry` or `pipx install poetry`)
* PyGObject (`sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0`)

### Run Installer Script
```bash
git clone https://github.com/moalmatry/tar-app-installer.git
cd tar-app-installer
./install.sh
```

The installer will:
1. Build the Poetry environment and dependencies.
2. Enable GTK 3 system bindings.
3. Symlink global commands `tar-installer` and `tar-installer-gui`.
4. Install the desktop launcher and custom SVG icon.
5. Register MIME type associations for `.tar.gz` files in your file manager.

---

## 🖥️ Graphical Interface (GUI)

Launch **Tar App Installer** from your Start Menu, right-click any archive in your Files app, or run:

```bash
tar-installer-gui
```

### Install with Pre-Loaded Archive:
```bash
tar-installer-gui /path/to/software.tar.gz
```

---

## 💻 Command-Line Interface (CLI)

### Install an Application Archive
```bash
tar-installer install postman-linux-x64.tar.gz
```

#### Non-Interactive (Auto-Accept Defaults)
```bash
tar-installer install -y blender-4.2.0-linux-x64.tar.xz
```

#### Custom Options
```bash
tar-installer install app.tar.gz \
  --name "My Custom App" \
  --category "Development" \
  --version "2.1.0"
```

### List Installed Applications
```bash
tar-installer list
```

**Example Output:**
```text
===========================================================================
NAME                 VERSION    SIZE       COMMAND              INSTALLED
===========================================================================
Blender              4.2.0      1.2 GB     blender              2026-10-11
Postman              10.24.1    320.5 MB   postman              2026-10-11
Godot Engine         4.3.0      115.2 MB   godot-engine         2026-10-11
===========================================================================
Total installed: 3 app(s)
```

### View Application Details
```bash
tar-installer info postman
```

### Launch an Application
```bash
tar-installer launch postman
```

### Cleanly Uninstall an Application
```bash
tar-installer remove postman
```
*(Removes the application directory, desktop launcher, icon, and binary symlink).*

---

## 🛠️ Uninstallation

To cleanly remove Tar App Installer itself from your system:
```bash
cd tar-app-installer
./uninstall.sh
```

---

## 📜 License

MIT License. Copyright (c) 2026 Mohamed Almatry.
