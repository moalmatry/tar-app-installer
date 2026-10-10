"""Core modules for Tar App Installer."""
from .models import CandidateExecutable, CandidateIcon, DetectedApp, InstallConfig, InstalledApp
from .archive import is_archive, extract_archive, ArchiveError
from .detector import detect_app, clean_app_name, clean_slug
from .installer import AppInstaller
from .registry import AppRegistry

__all__ = [
    "CandidateExecutable",
    "CandidateIcon",
    "DetectedApp",
    "InstallConfig",
    "InstalledApp",
    "is_archive",
    "extract_archive",
    "ArchiveError",
    "detect_app",
    "clean_app_name",
    "clean_slug",
    "AppInstaller",
    "AppRegistry",
]
