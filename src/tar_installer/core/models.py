"""Data models for Tar App Installer."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class CandidateExecutable:
    """Represents a potential executable detected in an extracted archive."""
    rel_path: str
    name: str
    score: int
    is_elf: bool
    is_script: bool


@dataclass
class CandidateIcon:
    """Represents an icon file found in an extracted archive."""
    rel_path: str
    format: str
    width: int
    height: int
    score: int


@dataclass
class DetectedApp:
    """Results of analyzing an extracted archive."""
    name: str
    slug: str
    version: str
    comment: str
    categories: list[str] = field(default_factory=lambda: ["Utility"])
    terminal: bool = False
    inner_root: str = ""  # Single top directory if exists (e.g. "Postman/")
    candidates_exec: list[CandidateExecutable] = field(default_factory=list)
    selected_exec: str | None = None
    candidates_icon: list[CandidateIcon] = field(default_factory=list)
    selected_icon: str | None = None
    existing_desktop_path: str | None = None


@dataclass
class InstallConfig:
    """User-confirmed or customized configuration for installing an app."""
    app_name: str
    app_slug: str
    version: str = "1.0.0"
    comment: str = ""
    categories: list[str] = field(default_factory=lambda: ["Utility"])
    exec_rel_path: str = ""
    icon_rel_path: str | None = None
    custom_icon_path: str | None = None
    terminal: bool = False
    system_wide: bool = False


@dataclass
class InstalledApp:
    """Record of an app installed on the system."""
    id: str
    name: str
    version: str
    comment: str
    categories: list[str]
    install_dir: str
    binary_path: str
    symlink_path: str
    desktop_file: str
    icon_path: str | None
    installed_at: float
    archive_source: str | None = None
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InstalledApp:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            comment=data.get("comment", ""),
            categories=data.get("categories", ["Utility"]),
            install_dir=data.get("install_dir", ""),
            binary_path=data.get("binary_path", ""),
            symlink_path=data.get("symlink_path", ""),
            desktop_file=data.get("desktop_file", ""),
            icon_path=data.get("icon_path"),
            installed_at=data.get("installed_at", 0.0),
            archive_source=data.get("archive_source"),
            size_bytes=data.get("size_bytes", 0),
        )
