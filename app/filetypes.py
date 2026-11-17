"""Find files of a given type: "search for .pdf files in Documents", "find all .mp3 files on the D drive".

Only file names, sizes and dates are read; no file is opened. System folders (Windows, Program Files, AppData, the recycle
bin...) are skipped, and every search has a time limit so a whole-disk search cannot hang Jarvis.

    parse(text)                          ({"exts": [...], "where": "Documents" | None}) or None when it is not such a request
    roots_for(where, home, drives)       the folders to search, and how to name them in the answer
    search(roots, exts, ...)             {"files": [...newest first], "count", "bytes", "truncated", "folders"}
    report(result, exts, label)          the answer text
"""
from __future__ import annotations

import os
import re
import string
import time
from datetime import datetime
from pathlib import Path

ALIASES = {
    "pdf": ["pdf"], "word": ["docx", "doc"], "excel": ["xlsx", "xls", "csv"], "powerpoint": ["pptx", "ppt"], "text": ["txt"],
    "image": ["jpg", "jpeg", "png", "gif", "webp", "bmp", "heic"], "photo": ["jpg", "jpeg", "png", "heic"], "picture": ["jpg", "jpeg", "png", "gif", "webp", "bmp", "heic"],
    "video": ["mp4", "mov", "mkv", "avi", "webm", "wmv"], "music": ["mp3", "wav", "flac", "m4a", "ogg", "aac"], "audio": ["mp3", "wav", "flac", "m4a", "ogg", "aac"],
    "song": ["mp3", "wav", "flac", "m4a", "ogg", "aac"], "python": ["py"], "zip": ["zip", "rar", "7z"], "archive": ["zip", "rar", "7z", "tar", "gz"],
    "installer": ["exe", "msi"], "program": ["exe", "msi"], "spreadsheet": ["xlsx", "xls", "csv", "ods"], "presentation": ["pptx", "ppt", "odp"],
    "document": ["pdf", "docx", "doc", "odt", "txt", "rtf"],
}
FR_ALIASES = {"image": "image", "images": "image", "photo": "photo", "photos": "photo", "vidéo": "video", "vidéos": "video", "video": "video", "videos": "video",
              "musique": "music", "musiques": "music", "chanson": "song", "chansons": "song", "texte": "text", "textes": "text", "document": "document", "documents": "document"}
SKIP_DIRS = {"windows", "program files", "program files (x86)", "programdata", "appdata", "$recycle.bin", "system volume information", "recovery", "$windows.~bt",
             "$windows.~ws", "msocache", "perflogs", "node_modules", "__pycache__", ".git", ".venv", "venv", "site-packages", "winsxs", ".gradle", ".cache"}
KNOWN = {"desktop": "Desktop", "bureau": "Desktop", "documents": "Documents", "my documents": "Documents", "mes documents": "Documents", "downloads": "Downloads",
         "téléchargements": "Downloads", "telechargements": "Downloads", "pictures": "Pictures", "photos": "Pictures", "images": "Pictures", "videos": "Videos",
         "vidéos": "Videos", "music": "Music", "musique": "Music", "onedrive": "OneDrive"}
EVERYWHERE = re.compile(r"(?:the\s+(?:whole\s+|entire\s+)?|my\s+(?:whole\s+|entire\s+)?|this\s+)?(?:computer|pc|laptop|machine)|everywhere|all\s+(?:my\s+|the\s+)?drives|"
                        r"(?:tout\s+)?(?:l['’]|mon\s+)?ordi(?:nateur)?|partout|tous\s+les\s+disques", re.I)
EXT = r"\.?[a-z0-9]{1,10}"
CLEAN_START = r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?"
MAX_KEEP = 2000


def _exts(words: str) -> list[str] | None:
    """'.pdf', 'pdf and .docx', '.jpg, .png or .gif', 'word', 'photos' -> extensions, or None when they are not file types."""
    parts = [p for p in re.split(r"\s*(?:,|\band\b|\bor\b|\bet\b|\bou\b|/|\+)\s*", words.strip().lower()) if p]
    out: list[str] = []
    for p in parts:
        p = re.sub(r"^(?:all|any|every|my|the|les|des|mes|tous\s+les|toutes\s+les)\s+", "", p).strip()
        if re.fullmatch(r"\.[a-z0-9]{1,10}", p):
            out.append(p[1:])
        elif FR_ALIASES.get(p) or (p.rstrip("s") in ALIASES):
            out += ALIASES[FR_ALIASES.get(p) or p.rstrip("s")]
        elif re.fullmatch(r"[a-z0-9]{2,5}", p) and not p.isdigit() and p not in ("big", "old", "new", "all", "any", "the", "my", "large", "small"):
            out.append(p)
        else:
            return None
    seen: list[str] = []
    for e in out:
        if e not in seen:
            seen.append(e)
    return seen or None


def parse(text: str) -> dict | None:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(CLEAN_START, "", t, flags=re.I)
    t = re.sub(r"\s*(?:please|for me|s['’]il te pla[iî]t|stp|svp)?\s*[.!?]*$", "", t, flags=re.I).strip()
    if not t or len(t) > 220:
        return None
    m = (re.fullmatch(r"(?:search|look|scan)\s+(?:for|through\s+\S+\s+for)\s+(?:all\s+(?:the\s+)?|any\s+|every\s+)?(.+?)\s+files?(?:\s+(?:in|on|inside|under|across|within|from)\s+(.+))?", t, re.I)
         or re.fullmatch(r"(?:find|list|show(?:\s+me)?|get|locate|where\s+are)\s+(?:all\s+(?:the\s+|of\s+my\s+)?|any\s+|every\s+|the\s+|my\s+)?(.+?)\s+files?(?:\s+(?:in|on|inside|under|across|within|from)\s+(.+))?", t, re.I)
         or re.fullmatch(r"(?:search|look\s+through|scan)\s+(.+?)\s+for\s+(?:all\s+(?:the\s+)?|any\s+)?(.+?)\s+files?", t, re.I)
         or re.fullmatch(r"(?:cherche|trouve|liste|montre)(?:[- ]moi)?\s+(?:tous\s+)?(?:les|des|mes)\s+fichiers\s+(.+?)(?:\s+(?:dans|sur|en)\s+(.+))?", t, re.I))
    if not m:
        return None
    if re.search(r"\b(?:internet|web|online|google|youtube|en\s+ligne)\b", t, re.I):
        return None                                                     # a web search, not one on this PC
    first, second = m.group(1), m.group(2)
    if re.match(r"(?:search|look\s+through|scan)\s+.+\s+for\s+", t, re.I) and not re.match(r"(?:search|look|scan)\s+for\b", t, re.I):
        first, second = second, first                                   # "search Documents for .pdf files"
    exts = _exts(first)
    if not exts:
        return None
    if not any("." in p for p in re.split(r"\s+", first)) and len(exts) == 1 and first.strip().lower() == exts[0] and not re.search(r"\bfichiers\b", t, re.I):
        # "find pdf files" is fine; "find big files" / "find my files" was refused above; a bare word must look like a real extension
        if exts[0] in ("new", "old", "home", "work", "school", "your", "those", "these", "some", "other", "recent"):
            return None
    where = (second or "").strip(" \"'“”") or None
    if where:
        where = re.sub(r"\s+(?:folder|directory|dossier|répertoire|repertoire)$", "", re.sub(r"^(?:the|my|le|la|les|mon|ma|mes|l['’])\s*", "", where, flags=re.I), flags=re.I).strip() or None
    return {"exts": exts, "where": where}


def fixed_drives() -> list[Path]:
    if os.name != "nt":
        return [Path("/")]
    found = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        try:
            if root.exists():
                found.append(root)
        except OSError:
            pass
    return found


def roots_for(where: str | None, home: Path, drives=fixed_drives) -> tuple[list[Path], str] | tuple[None, str]:
    """The folders to search, and a label for the answer. (None, message) when the place is not found."""
    home = Path(home)
    if not where:
        roots = [home / n for n in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music")]
        roots += [home / "OneDrive" / n for n in ("Desktop", "Documents", "Pictures")]
        return [r for r in roots if r.is_dir()], "your Desktop, Documents, Downloads, Pictures, Videos and Music folders"
    w = where.strip()
    if EVERYWHERE.fullmatch(w):
        return drives(), "the whole computer"
    m = re.fullmatch(r"(?:the\s+|le\s+)?(?:drive\s+|disque\s+|lecteur\s+)?([a-z])(?::\\?|\s+drive)?(?:\s+drive|\s*:)?", w, re.I) if len(w) <= 12 else None
    if m and (":" in w or re.search(r"drive|disque|lecteur", w, re.I)):
        root = Path(f"{m.group(1).upper()}:\\") if os.name == "nt" else Path("/")
        return ([root], f"the {m.group(1).upper()}: drive") if root.exists() else (None, f"There is no {m.group(1).upper()}: drive on this PC")
    expanded = Path(os.path.expandvars(os.path.expanduser(w)))
    if expanded.is_absolute():
        return ([expanded], str(expanded)) if expanded.is_dir() else (None, f"I cannot find the folder {expanded}")
    key = w.lower()
    if key in ("home", "user folder", "my user folder", "dossier utilisateur"):
        return [home], "your user folder"
    if key in KNOWN:
        name = KNOWN[key]
        for candidate in (home / name, home / "OneDrive" / name):
            if candidate.is_dir():
                return [candidate], name
    # a folder by its own name: under the user folder, a known folder, or one level deeper ("my School folder")
    wanted = key.replace("\\", "/").strip("/")
    places = [home] + [home / n for n in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music", "OneDrive")] + [home / "OneDrive" / n for n in ("Desktop", "Documents")]
    hits: list[Path] = []
    for base in places:
        try:
            if "/" in wanted:
                candidate = base / wanted
                if candidate.is_dir():
                    hits.append(candidate)
                continue
            for entry in os.scandir(base):
                if entry.is_dir(follow_symlinks=False) and entry.name.lower() == wanted:
                    hits.append(Path(entry.path))
        except OSError:
            continue
    unique: list[Path] = []
    for h in hits:
        if all(h.resolve() != u.resolve() for u in unique):
            unique.append(h)
    if len(unique) == 1:
        return unique, unique[0].name
    if len(unique) > 1:
        return unique[:5], " and ".join(str(u) for u in unique[:5])
    return None, f"I cannot find a folder called “{where}” in your user folder, Desktop, Documents or Downloads. Give the full path, for example C:\\Users\\you\\School"


def search(roots: list[Path], exts: list[str], seconds: float = 20.0, max_entries: int = 1_500_000, skip_hidden: bool = True) -> dict:
    wanted = tuple("." + e.lower() for e in exts)
    deadline = time.monotonic() + seconds
    files: list[dict] = []
    count = total = folders = entries = 0
    truncated = False
    seen_dirs: set[str] = set()
    stack = [str(r) for r in roots]
    while stack:
        if time.monotonic() >= deadline or entries >= max_entries:
            truncated = True
            break
        folder = stack.pop()
        key = os.path.normcase(folder)
        if key in seen_dirs:
            continue
        seen_dirs.add(key)
        folders += 1
        try:
            with os.scandir(folder) as it:
                for entry in it:
                    entries += 1
                    name = entry.name
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if name.lower() not in SKIP_DIRS and not (skip_hidden and name.startswith((".", "$"))):
                                stack.append(entry.path)
                        elif name.lower().endswith(wanted) and entry.is_file(follow_symlinks=False):
                            info = entry.stat(follow_symlinks=False)
                            count += 1
                            total += info.st_size
                            files.append({"name": name, "path": entry.path, "size": info.st_size, "modified": info.st_mtime})
                            if len(files) > MAX_KEEP:                       # keep only the newest ones in memory
                                files.sort(key=lambda f: -f["modified"])
                                del files[MAX_KEEP // 2:]
                    except OSError:
                        continue
        except OSError:
            continue
    files.sort(key=lambda f: -f["modified"])
    return {"files": files, "count": count, "bytes": total, "truncated": truncated, "folders": folders}


def size_text(n: float) -> str:
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def ext_text(exts: list[str]) -> str:
    names = [f".{e}" for e in exts]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def report(result: dict, exts: list[str], label: str, address: str = "sir", shown: int = 40) -> str:
    kinds = ext_text(exts)
    if not result["count"]:
        extra = " I stopped at the time limit, so a narrower folder may still have some." if result["truncated"] else ""
        return f"I found no {kinds} files in {label}, {address}.{extra}"
    n = result["count"]
    text = f"I found {n:,} {kinds} file{'s' if n != 1 else ''} in {label}, {address}, {size_text(result['bytes'])} in total."
    if n > shown:
        text += f" Here are the {shown} most recently changed."
    if result["truncated"]:
        text += " I stopped at the time limit, so there may be more: name a narrower folder for a complete list."
    return text


def detail(f: dict) -> str:
    return f"{size_text(f['size'])} · changed {datetime.fromtimestamp(f['modified']).strftime('%d %b %Y')}"
