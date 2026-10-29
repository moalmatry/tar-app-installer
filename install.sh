#!/usr/bin/env bash
#
# Tar App Installer - Automated Installer Script
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

echo "=========================================================="
echo "          Tar App Installer for Linux - Installer         "
echo "=========================================================="
echo ""

# 1. Check Dependencies
echo "[1/5] Checking system dependencies..."
if ! command -v python3 &>/dev/null; then
    echo "Error: Python 3 is required."
    exit 1
fi

if ! command -v poetry &>/dev/null; then
    echo "Error: Poetry is required. Install via: sudo apt install python3-poetry or pipx install poetry."
    exit 1
fi

# Ensure PyGObject is installed on system
if ! python3 -c "import gi" &>/dev/null; then
    echo "Installing python3-gi dependency..."
    sudo apt-get update -qq && sudo apt-get install -y -qq python3-gi python3-gi-cairo gir1.2-gtk-3.0
fi

# 2. Build Poetry environment
echo "[2/5] Building Poetry environment..."
cd "$SCRIPT_DIR"
poetry install

VENV_PATH="$(poetry env info -p)"
if [ -z "$VENV_PATH" ] || [ ! -d "$VENV_PATH" ]; then
    echo "Error: Failed to locate Poetry virtual environment."
    exit 1
fi

# Enable system-site-packages for PyGObject (GTK3) access
if [ -f "$VENV_PATH/pyvenv.cfg" ]; then
    sed -i 's/include-system-site-packages = false/include-system-site-packages = true/' "$VENV_PATH/pyvenv.cfg"
fi

# 3. Setup Global Binaries in /usr/local/bin
echo "[3/5] Setting up global executables in /usr/local/bin..."
sudo ln -sf "$VENV_PATH/bin/tar-installer" /usr/local/bin/tar-installer
sudo ln -sf "$VENV_PATH/bin/tar-installer-gui" /usr/local/bin/tar-installer-gui
sudo ln -sf "$VENV_PATH/bin/tar-installer" /usr/local/bin/tar-app-installer
sudo ln -sf "$VENV_PATH/bin/tar-installer-gui" /usr/local/bin/tar-app-installer-gui
sudo chmod +x /usr/local/bin/tar-installer /usr/local/bin/tar-installer-gui /usr/local/bin/tar-app-installer /usr/local/bin/tar-app-installer-gui

# Also ensure user bin has them
mkdir -p "$HOME/.local/bin"
ln -sf "$VENV_PATH/bin/tar-installer" "$HOME/.local/bin/tar-installer"
ln -sf "$VENV_PATH/bin/tar-installer-gui" "$HOME/.local/bin/tar-installer-gui"
ln -sf "$VENV_PATH/bin/tar-installer" "$HOME/.local/bin/tar-app-installer"
ln -sf "$VENV_PATH/bin/tar-installer-gui" "$HOME/.local/bin/tar-app-installer-gui"

# 4. Install Desktop Launcher and Icon
echo "[4/5] Installing desktop launcher and app icon..."
sudo mkdir -p /usr/local/share/applications /usr/local/share/icons/hicolor/scalable/apps
sudo cp "$SCRIPT_DIR/data/tar-installer.desktop" /usr/local/share/applications/
sudo cp "$SCRIPT_DIR/data/icons/hicolor/scalable/apps/tar-installer.svg" /usr/local/share/icons/hicolor/scalable/apps/

# Also copy to user local
mkdir -p "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/scalable/apps"
cp "$SCRIPT_DIR/data/tar-installer.desktop" "$HOME/.local/share/applications/"
cp "$SCRIPT_DIR/data/icons/hicolor/scalable/apps/tar-installer.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/"

# 5. Update Caches
echo "[5/5] Updating desktop and icon databases..."
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    sudo update-desktop-database /usr/local/share/applications 2>/dev/null || true
fi

if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -q -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    sudo gtk-update-icon-cache -q -t /usr/local/share/icons/hicolor 2>/dev/null || true
fi

echo ""
echo "=========================================================="
echo "    ✓ Tar App Installer successfully installed! 🎉       "
echo "=========================================================="
echo ""
echo "You can now:"
echo "  • Open GUI:     Launch 'Tar App Installer' from your Start Menu"
echo "                  or run: tar-installer-gui"
echo ""
echo "  • Open via CLI: tar-installer install /path/to/archive.tar.gz"
echo "  • List apps:    tar-installer list"
echo "  • Right-Click:  Right-click any .tar.gz in Files -> Open With -> Tar App Installer"
echo ""
