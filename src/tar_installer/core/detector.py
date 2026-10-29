"""Smart application detection engine for extracted Linux packages."""
from __future__ import annotations

import configparser
import os
import re
from pathlib import Path
from .models import CandidateExecutable, CandidateIcon, DetectedApp


def clean_app_name(raw_name: str) -> str:
    """Cleans an archive or directory name into a human-friendly application title."""
    s = raw_name
    # Strip archive extensions
    for ext in (".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar", ".zip"):
        if s.lower().endswith(ext):
            s = s[: -len(ext)]

    # Strip arch / OS tags and version strings
    patterns = [
        r"[-_](linux|ubuntu|debian|windows|darwin|macos|x86[-_]64|amd64|x64|x86|i386|i686|arm64|aarch64|portable|bin|appimage|tar|gz|zip)\b",
        r"[-_]v?\d+(\.\d+)*(-[a-zA-Z0-9.]+)?\b",
    ]
    for p in patterns:
        s = re.sub(p, "", s, flags=re.IGNORECASE)

    # Convert dashes / underscores to spaces and title case if all lowercase
    clean = re.sub(r"[-_]+", " ", s).strip()
    if clean.islower() or clean.isupper():
        return clean.title()
    return clean if clean else raw_name


def clean_slug(name: str) -> str:
    """Converts an app name into a filesystem & desktop file safe slug."""
    s = re.sub(r"[^a-zA-Z0-9-_]+", "-", name.lower()).strip("-")
    return s if s else "custom-app"


def extract_version(text: str) -> str:
    """Attempts to parse a semantic version string from text or filename."""
    match = re.search(r"\bv?(\d+\.\d+(\.\d+)?(-[a-zA-Z0-9.]+)?)\b", text)
    if match:
        return match.group(1)
    return "1.0.0"


def is_elf_binary(path: Path) -> bool:
    """Checks if a file is an ELF binary."""
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def is_shell_script(path: Path) -> bool:
    """Checks if a file starts with a script shebang."""
    try:
        with open(path, "rb") as f:
            header = f.read(2)
            return header == b"#!"
    except OSError:
        return False


def get_png_dimensions(path: Path) -> tuple[int, int]:
    """Reads width and height from PNG header without external libraries."""
    try:
        with open(path, "rb") as f:
            data = f.read(24)
            if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
                w = int.from_bytes(data[16:20], byteorder="big")
                h = int.from_bytes(data[20:24], byteorder="big")
                return w, h
    except OSError:
        pass
    return 0, 0


def detect_app(extract_dir: str | Path, source_archive_name: str = "") -> DetectedApp:
    """Analyzes an extracted directory and detects application metadata."""
    base_path = Path(extract_dir).resolve()

    # 1. Determine inner root (if archive had a single top-level directory)
    entries = [p for p in base_path.iterdir() if p.name not in (".", "..")]
    if len(entries) == 1 and entries[0].is_dir():
        root_dir = entries[0]
        inner_root_rel = entries[0].name
    else:
        root_dir = base_path
        inner_root_rel = ""

    # 2. Check for existing .desktop file
    desktop_files = list(root_dir.rglob("*.desktop"))
    desktop_files.sort(key=lambda p: len(p.relative_to(root_dir).parts))
    existing_desktop = desktop_files[0] if desktop_files else None

    # Initial name / slug / version guess
    base_name_guess = source_archive_name or root_dir.name
    app_name = clean_app_name(base_name_guess)
    app_slug = clean_slug(app_name)
    app_version = extract_version(source_archive_name or root_dir.name)
    app_comment = f"{app_name} Application"
    app_categories = ["Utility"]
    app_terminal = False
    preferred_exec_name = None
    preferred_icon_name = None
    preferred_icon_stem = None

    if existing_desktop and existing_desktop.is_file():
        try:
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(existing_desktop, encoding="utf-8")
            if parser.has_section("Desktop Entry"):
                sec = parser["Desktop Entry"]
                if "Name" in sec:
                    app_name = sec["Name"].strip()
                    app_slug = clean_slug(app_name)
                if "Comment" in sec:
                    app_comment = sec["Comment"].strip()
                elif "GenericName" in sec:
                    app_comment = sec["GenericName"].strip()
                if "Categories" in sec:
                    cats = [c.strip() for c in sec["Categories"].split(";") if c.strip()]
                    if cats:
                        app_categories = cats
                if "Terminal" in sec:
                    app_terminal = sec.getboolean("Terminal", fallback=False)
                if "Exec" in sec:
                    raw_exec = sec["Exec"].split()[0].strip("\"'")
                    preferred_exec_name = Path(raw_exec).name
                if "Icon" in sec:
                    raw_icon = sec["Icon"].strip("\"'")
                    preferred_icon_name = Path(raw_icon).name
                    preferred_icon_stem = Path(raw_icon).stem
        except Exception:
            pass

    # 3. Scan for executable candidates
    candidate_execs: list[CandidateExecutable] = []
    ignored_patterns = (
        r"\.so(\.\d+)*$",
        r"\.a$",
        r"\.dylib$",
        r"\.dll$",
        r"\.exe$",
        r"\.pyc$",
        r"\.h$",
        r"\.c$",
        r"\.cpp$",
        r"\.txt$",
        r"\.md$",
        r"\.json$",
        r"\.xml$",
        r"\.desktop$",
        r"\.png$",
        r"\.svg$",
    )

    for p in root_dir.rglob("*"):
        if not p.is_file():
            continue

        rel = p.relative_to(base_path)
        name = p.name
        name_lower = name.lower()

        # Skip ignored extensions
        if any(re.search(pat, name_lower) for pat in ignored_patterns):
            continue

        is_elf = is_elf_binary(p)
        is_script = is_shell_script(p)
        is_x = os.access(p, os.X_OK)

        if not (is_elf or is_script or is_x):
            continue

        score = 0
        depth = len(p.relative_to(root_dir).parts)
        score -= depth * 5

        # ELF binaries are high priority
        if is_elf:
            score += 40

        # Scripts
        if is_script:
            score += 20

        # Name heuristic
        stem_lower = p.stem.lower()
        if preferred_exec_name and (name == preferred_exec_name or p.stem == preferred_exec_name):
            score += 120

        if stem_lower == app_slug or stem_lower == clean_slug(app_name):
            score += 70
        elif app_slug in stem_lower:
            score += 35

        # Common launchers
        if stem_lower in ("start", "run", "launch", "app", "main"):
            score += 25

        # In root directory or bin/
        rel_parts = p.relative_to(root_dir).parts
        if len(rel_parts) == 1:
            score += 30
        elif len(rel_parts) == 2 and rel_parts[0] in ("bin", "usr"):
            score += 25

        # Negative score for helpers / sandboxes / installers
        if any(kw in stem_lower for kw in ("sandbox", "crashpad", "uninstall", "update", "helper", "daemon", "node")):
            score -= 100

        candidate_execs.append(
            CandidateExecutable(
                rel_path=str(rel),
                name=name,
                score=score,
                is_elf=is_elf,
                is_script=is_script,
            )
        )

    # Sort executables by score descending
    candidate_execs.sort(key=lambda x: x.score, reverse=True)
    selected_exec = candidate_execs[0].rel_path if candidate_execs else None

    # 4. Scan for icon candidates
    candidate_icons: list[CandidateIcon] = []
    for p in root_dir.rglob("*"):
        if not p.is_file():
            continue

        ext = p.suffix.lower()
        if ext not in (".svg", ".png", ".xpm", ".ico"):
            continue

        rel = p.relative_to(base_path)
        name = p.name
        stem_lower = p.stem.lower()
        score = 0
        w, h = 0, 0

        if ext == ".svg":
            score += 75
            w, h = 512, 512
        elif ext == ".png":
            w, h = get_png_dimensions(p)
            if w == 0:
                dim_match = re.search(r"(\d+)", stem_lower)
                if dim_match:
                    val = int(dim_match.group(1))
                    if val in (16, 24, 32, 48, 64, 128, 256, 512, 1024):
                        w, h = val, val
            if w >= 512:
                score += 65
            elif w >= 256:
                score += 55
            elif w >= 128:
                score += 45
            elif w >= 64:
                score += 30
            elif w >= 48:
                score += 20
            elif w >= 32:
                score += 15
            else:
                score += 5
        elif ext == ".ico":
            score += 5  # Lowest priority; Linux prefers PNG/SVG
        elif ext == ".xpm":
            score += 10

        # Exact match with preferred icon from .desktop
        if preferred_icon_name and (name == preferred_icon_name or p.stem == preferred_icon_name or (preferred_icon_stem and p.stem == preferred_icon_stem)):
            score += 150

        # Name matches app_slug or standard icon terms
        if stem_lower == app_slug or stem_lower == clean_slug(app_name):
            score += 60
        elif stem_lower in ("icon", "logo", "app"):
            score += 45
        elif re.search(r"(^|[-_])(logo|icon|app)([-_0-9]|$)", stem_lower):
            score += 35
        elif app_slug in stem_lower:
            score += 30

        # Penalty for monochrome / inverted / tray / dark mode icons
        if any(k in stem_lower for k in ("white", "black", "dark", "light", "mono", "symbolic", "tray", "badge", "indicator", "status")):
            score -= 40

        # Bonus for standard icon directories
        if any(part in ("icons", "pixmaps", "assets", "img", "images", "res", "resources") for part in p.parts):
            score += 20
        if any(part in ("hicolor", "apps", "512x512", "256x256", "128x128", "scalable") for part in p.parts):
            score += 20

        candidate_icons.append(
            CandidateIcon(
                rel_path=str(rel),
                format=ext.lstrip("."),
                width=w,
                height=h,
                score=score,
            )
        )

    candidate_icons.sort(key=lambda x: x.score, reverse=True)
    selected_icon = candidate_icons[0].rel_path if candidate_icons else None

    return DetectedApp(
        name=app_name,
        slug=app_slug,
        version=app_version,
        comment=app_comment,
        categories=app_categories,
        terminal=app_terminal,
        inner_root=inner_root_rel,
        candidates_exec=candidate_execs,
        selected_exec=selected_exec,
        candidates_icon=candidate_icons,
        selected_icon=selected_icon,
        existing_desktop_path=str(existing_desktop.relative_to(base_path)) if existing_desktop else None,
    )
