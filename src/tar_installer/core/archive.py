"""Archive extraction utilities with security safeguards."""
from __future__ import annotations

import os
import tarfile
import zipfile
from pathlib import Path
from typing import Callable


class ArchiveError(Exception):
    """Raised when an archive cannot be read or safely extracted."""
    pass


def is_archive(file_path: str | Path) -> bool:
    """Checks whether the given file path is a supported archive."""
    path = Path(file_path)
    if not path.is_file():
        return False

    name_lower = path.name.lower()
    supported_extensions = (
        ".tar.gz", ".tgz",
        ".tar.bz2", ".tbz2",
        ".tar.xz", ".txz",
        ".tar",
        ".zip",
    )
    if any(name_lower.endswith(ext) for ext in supported_extensions):
        return True

    # Magic byte check
    try:
        with open(path, "rb") as f:
            header = f.read(6)
            if header.startswith(b"\x1f\x8b"):  # gzip
                return True
            if header.startswith(b"BZh"):     # bzip2
                return True
            if header.startswith(b"\xfd7zXZ"): # xz
                return True
            if header.startswith(b"PK\x03\x04"): # zip
                return True
    except OSError:
        pass
    return False


def is_safe_path(target_dir: Path, path: Path) -> bool:
    """Verifies that resolved path is safely inside target_dir (prevent path traversal)."""
    try:
        resolved_target = target_dir.resolve()
        resolved_path = path.resolve()
        return os.path.commonpath([resolved_target, resolved_path]) == str(resolved_target)
    except Exception:
        return False


def extract_archive(
    archive_path: str | Path,
    dest_dir: str | Path,
    progress_callback: Callable[[float, str], None] | None = None,
) -> Path:
    """Safely extracts a supported archive into dest_dir.
    
    Args:
        archive_path: Path to the archive (.tar.gz, .tgz, .tar.xz, .zip, etc.)
        dest_dir: Destination directory.
        progress_callback: Optional callable accepting (fraction: float, filename: str).

    Returns:
        Path to the destination directory.
    """
    src = Path(archive_path).resolve()
    dst = Path(dest_dir).resolve()

    if not src.is_file():
        raise ArchiveError(f"Archive file not found: {src}")

    dst.mkdir(parents=True, exist_ok=True)

    if zipfile.is_zipfile(src):
        _extract_zip(src, dst, progress_callback)
    elif tarfile.is_tarfile(src):
        _extract_tar(src, dst, progress_callback)
    else:
        # Fallback check based on extension
        name = src.name.lower()
        if name.endswith((".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tar")):
            _extract_tar(src, dst, progress_callback)
        elif name.endswith(".zip"):
            _extract_zip(src, dst, progress_callback)
        else:
            raise ArchiveError(f"Unsupported or corrupted archive format: {src.name}")

    return dst


def _extract_tar(
    src: Path,
    dst: Path,
    progress_callback: Callable[[float, str], None] | None = None,
):
    try:
        with tarfile.open(src, "r:*") as tar:
            members = tar.getmembers()
            total = len(members)

            # Security check: check every member for path traversal
            for m in members:
                target_path = dst / m.name
                if not is_safe_path(dst, target_path):
                    raise ArchiveError(f"Path traversal detected in archive entry: {m.name}")

            # Extract members with progress tracking
            for i, m in enumerate(members):
                # Python 3.12+ safe filter if available
                if hasattr(tarfile, "data_filter"):
                    tar.extract(m, path=dst, filter="data")
                else:
                    tar.extract(m, path=dst)

                if progress_callback and total > 0:
                    fraction = (i + 1) / total
                    progress_callback(fraction, m.name)

    except (tarfile.TarError, OSError) as e:
        raise ArchiveError(f"Failed to extract tar archive: {e}") from e


def _extract_zip(
    src: Path,
    dst: Path,
    progress_callback: Callable[[float, str], None] | None = None,
):
    try:
        with zipfile.ZipFile(src, "r") as zf:
            infolist = zf.infolist()
            total = len(infolist)

            # Security check
            for info in infolist:
                target_path = dst / info.filename
                if not is_safe_path(dst, target_path):
                    raise ArchiveError(f"Path traversal detected in zip entry: {info.filename}")

            for i, info in enumerate(infolist):
                zf.extract(info, path=dst)
                if progress_callback and total > 0:
                    fraction = (i + 1) / total
                    progress_callback(fraction, info.filename)

    except (zipfile.BadZipFile, OSError) as e:
        raise ArchiveError(f"Failed to extract zip archive: {e}") from e
