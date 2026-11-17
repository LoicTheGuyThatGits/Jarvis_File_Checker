"""Project folders: the folders Autopilot may read and write files in directly ("work on my website in C:\\Users\\me\\site").

Only folders you added in Settings > AI model > Computer control count. Inside them Autopilot can list folders, read text
files and write text files; every file it overwrites is first copied to data/file-backups/projects/<time>/. It cannot
write programs or scripts that Windows would run by double-clicking (.exe, .bat, .ps1 and the like), and it cannot
reach anything outside those folders (no "..", no links pointing elsewhere).
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

BLOCKED_WRITE = {".exe", ".dll", ".msi", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".wsf", ".scr", ".lnk", ".reg", ".com", ".pif", ".hta", ".jar", ".sys"}
READ_LIMIT = 60_000
WRITE_LIMIT = 300_000
SIGHTS = ("auto", "picture", "text")
DEFAULTS = {"folders": [], "sight": "auto", "max_steps": 40, "ocr": True}


def load_config(path: Path) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    cfg = dict(DEFAULTS)
    if isinstance(raw, dict):
        cfg["folders"] = [str(f) for f in raw.get("folders", []) if isinstance(f, str)][:20]
        cfg["sight"] = raw.get("sight") if raw.get("sight") in SIGHTS else "auto"
        try:
            cfg["max_steps"] = max(10, min(150, int(raw.get("max_steps", 40))))
        except (TypeError, ValueError):
            pass
        cfg["ocr"] = raw.get("ocr") is not False
    return cfg


def save_config(path: Path, update: dict) -> dict:
    cfg = load_config(path)
    if "folders" in update:
        folders = []
        for f in update["folders"]:
            p = Path(os.path.expandvars(os.path.expanduser(str(f).strip().strip('"'))))
            if not p.is_absolute() or not p.is_dir():
                raise ValueError(f"“{f}” is not a folder on this PC.")
            if len(p.resolve().parts) <= 2 or p.resolve() == Path.home().resolve():
                raise ValueError(f"“{p}” is too broad. Choose the folder of one project, not a whole drive or your user folder.")
            if str(p.resolve()) not in folders:
                folders.append(str(p.resolve()))
        cfg["folders"] = folders[:20]
    if update.get("sight") in SIGHTS:
        cfg["sight"] = update["sight"]
    if "max_steps" in update:
        cfg["max_steps"] = max(10, min(150, int(update["max_steps"])))
    if "ocr" in update:
        cfg["ocr"] = update["ocr"] is not False
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def inside(target: str, folders: list[str]) -> Path | None:
    """The real path, when it lies inside one of the project folders; else None."""
    if not target or not folders:
        return None
    raw = Path(os.path.expandvars(os.path.expanduser(str(target).strip().strip('"'))))
    candidates = [raw] if raw.is_absolute() else [Path(f) / raw for f in folders]
    for c in candidates:
        try:
            real = c.resolve()
        except OSError:
            continue
        for f in folders:
            root = Path(f).resolve()
            if real == root or root in real.parents:
                return real
    return None


def list_folder(target: str, folders: list[str], limit: int = 200) -> str:
    p = inside(target or ".", folders) if target else Path(folders[0]).resolve() if folders else None
    if p is None:
        raise ValueError("That is not inside a project folder.")
    if not p.is_dir():
        raise ValueError(f"{p} is not a folder.")
    entries = []
    for e in sorted(os.scandir(p), key=lambda e: (not e.is_dir(), e.name.lower())):
        if e.name in (".git", "node_modules", "__pycache__", ".venv", "Library", "Temp", "obj", "bin") and e.is_dir():
            entries.append(f"[{e.name}/ (skipped)]")
            continue
        entries.append(e.name + "/" if e.is_dir() else f"{e.name} ({e.stat().st_size} bytes)")
        if len(entries) >= limit:
            entries.append("… (more not shown)")
            break
    return f"Folder {p}:\n" + ("\n".join(entries) or "(empty)")


def read_file(target: str, folders: list[str]) -> str:
    p = inside(target, folders)
    if p is None:
        raise ValueError("That file is not inside a project folder.")
    if not p.is_file():
        raise ValueError(f"There is no file {p}.")
    data = p.read_bytes()
    if b"\x00" in data[:4000]:
        raise ValueError(f"{p.name} is not a text file.")
    text = data[:READ_LIMIT].decode("utf-8", errors="replace")
    return f"File {p} ({len(data)} bytes){' — only the start is shown' if len(data) > READ_LIMIT else ''}:\n{text}"


def write_file(target: str, text: str, folders: list[str], backup_root: Path) -> str:
    p = inside(target, folders)
    if p is None:
        raise ValueError("Autopilot may only write inside your project folders.")
    if p.suffix.lower() in BLOCKED_WRITE:
        raise ValueError(f"Autopilot does not write {p.suffix} files (programs and scripts Windows can run directly).")
    if not isinstance(text, str) or len(text.encode("utf-8")) > WRITE_LIMIT:
        raise ValueError("Nothing to write, or more than 300 KB.")
    existed = p.exists()
    if existed:
        if p.is_dir():
            raise ValueError(f"{p} is a folder.")
        backup = Path(backup_root) / time.strftime("%Y%m%d-%H%M%S") / p.name
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, backup)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="")
    return f"Wrote {p} ({len(text)} characters)" + (" — the old version is kept in data\\file-backups\\projects" if existed else " (a new file)")


def describe(folders: list[str]) -> str:
    if not folders:
        return ""
    return ("Project folders you may work in directly (list_folder, read_file, write_file; paths may be relative to them):\n" + "\n".join(f"- {f}" for f in folders))
