#!/usr/bin/env bash
#
# Tar App Installer - Uninstaller Script
#
set -e

echo "Uninstalling Tar App Installer..."

sudo rm -f /usr/local/bin/tar-installer /usr/local/bin/tar-installer-gui /usr/local/bin/tar-app-installer /usr/local/bin/tar-app-installer-gui
sudo rm -f /usr/local/share/applications/tar-installer.desktop /usr/local/share/applications/tar-app-installer.desktop
sudo rm -f /usr/local/share/icons/hicolor/scalable/apps/tar-installer.svg

rm -f "$HOME/.local/bin/tar-installer" "$HOME/.local/bin/tar-installer-gui" "$HOME/.local/bin/tar-app-installer" "$HOME/.local/bin/tar-app-installer-gui"
rm -f "$HOME/.local/share/applications/tar-installer.desktop" "$HOME/.local/share/applications/tar-app-installer.desktop"
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/tar-installer.svg"

if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
    sudo update-desktop-database /usr/local/share/applications 2>/dev/null || true
fi

echo "Tar App Installer uninstalled successfully."
