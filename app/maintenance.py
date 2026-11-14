"""PC health check: disk space, memory, uptime, temp files, startup programs and heavy programs, in plain words.

"how's my PC?" only reads things. "clean up my temp files" first says how much it would delete and waits for "yes, clean them".
Only files in your temp folder that are more than 3 days old are ever deleted, and files in use are left alone.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

TEMP_AGE_DAYS, WALK_LIMIT, WALK_SECONDS, CONFIRM_SECONDS = 3, 40000, 6.0, 120
PENDING: dict = {"at": 0.0}


def backup_age(last) -> str:
    if not last:
        return "never"
    d = (time.time() - last) / 86400
    return "today" if d < 1 else "yesterday" if d < 2 else f"{int(d)} days ago"


def gb(n: float) -> str:
    return f"{n / 1e9:.1f} GB" if n >= 1e8 else f"{n / 1e6:.0f} MB"


def temp_scan(root: Path | None = None, now: float | None = None) -> dict:
    """Size of the temp folder and of the part older than TEMP_AGE_DAYS (the part that may be deleted)."""
    root = Path(root or tempfile.gettempdir())
    now = time.time() if now is None else now
    total = old = files = old_files = 0
    stop = time.time() + WALK_SECONDS
    partial = False
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            if files >= WALK_LIMIT or time.time() > stop:
                partial = True
                break
            p = os.path.join(dirpath, name)
            try:
                if os.path.islink(p):
                    continue
                st = os.stat(p)
            except OSError:
                continue
            files += 1
            total += st.st_size
            if now - max(st.st_mtime, st.st_atime) > TEMP_AGE_DAYS * 86400:
                old += st.st_size
                old_files += 1
        if partial:
            break
    return {"total": total, "old": old, "files": files, "old_files": old_files, "partial": partial}


def temp_clean(root: Path | None = None, now: float | None = None) -> dict:
    root = Path(root or tempfile.gettempdir()).resolve()
    now = time.time() if now is None else now
    freed = removed = failed = 0
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            p = Path(dirpath) / name
            try:
                if p.is_symlink() or not str(p.resolve()).startswith(str(root)):
                    continue
                st = p.stat()
                if now - max(st.st_mtime, st.st_atime) <= TEMP_AGE_DAYS * 86400:
                    continue
                p.unlink()
                freed += st.st_size
                removed += 1
            except OSError:
                failed += 1                          # in use or protected: leave it
    return {"freed": freed, "removed": removed, "failed": failed}


def startup_programs() -> list[str]:
    names: list[str] = []
    try:
        import winreg
        for hive, sub in ((winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"), (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run")):
            try:
                with winreg.OpenKey(hive, sub) as key:
                    for i in range(200):
                        try:
                            names.append(winreg.EnumValue(key, i)[0])
                        except OSError:
                            break
            except OSError:
                pass
    except ImportError:
        pass
    return names


def heavy_programs(limit: int = 4) -> list[tuple[str, float]]:
    try:
        import psutil
    except ImportError:
        return []
    totals: dict[str, float] = {}
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            mem = p.info["memory_info"].rss
            totals[p.info["name"] or "?"] = totals.get(p.info["name"] or "?", 0) + mem
        except Exception:
            continue
    skip = {"System", "Registry", "Memory Compression", "System Idle Process"}
    return sorted(((n, v) for n, v in totals.items() if n not in skip), key=lambda x: -x[1])[:limit]


def last_update() -> str | None:
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "(Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 1).InstalledOn.ToString('yyyy-MM-dd')"],
                             capture_output=True, text=True, timeout=25, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
        return out if re.fullmatch(r"\d{4}-\d{2}-\d{2}", out) else None
    except Exception:
        return None


def folder_size(path: Path, limit_seconds: float = 4.0) -> int | None:
    if not path.is_dir():
        return None
    total, stop = 0, time.time() + limit_seconds
    for dirpath, _d, names in os.walk(path):
        for n in names:
            try:
                total += os.path.getsize(os.path.join(dirpath, n))
            except OSError:
                pass
        if time.time() > stop:
            return None
    return total


def collect(snapshot: dict | None = None, extra_folders: dict | None = None, backup: dict | None = None) -> dict:
    snapshot = snapshot or {}
    drive = os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
    try:
        du = shutil.disk_usage(drive)
        disk = {"drive": drive, "free": du.free, "total": du.total}
    except OSError:
        disk = None
    return {"disk": disk, "ram": snapshot.get("ram"), "uptime_s": snapshot.get("uptime_s"), "temp": temp_scan(), "startup": startup_programs(),
            "heavy": heavy_programs(), "update": last_update(), "folders": {k: folder_size(Path(v)) for k, v in (extra_folders or {}).items()},
            **({"backup": backup} if backup is not None else {})}


def report(info: dict) -> str:
    lines, tips = ["PC health check:"], []
    d = info.get("disk")
    if d:
        pct = round(100 * d["free"] / max(d["total"], 1))
        lines.append(f"• Disk {d['drive']}: {gb(d['free'])} free of {gb(d['total'])} ({pct}% free)")
        if pct < 15:
            tips.append("The disk is nearly full. Delete big downloads or old Ollama models you no longer use.")
    r = info.get("ram")
    if r:
        lines.append(f"• Memory: {r['used_gb']} of {r['total_gb']} GB in use ({r['percent']}%)")
        if r["percent"] >= 85:
            tips.append("Memory is almost full. Close programs you are not using, or pick a smaller Ollama model.")
    up = info.get("uptime_s")
    if up is not None:
        days = up / 86400
        lines.append(f"• On for {days:.1f} days" if days >= 1 else f"• On for {up // 3600} hours {up % 3600 // 60} minutes")
        if days >= 7:
            tips.append("It has not been restarted for over a week. A restart clears slowdowns and finishes updates.")
    t = info.get("temp")
    if t:
        lines.append(f"• Temp files: {gb(t['total'])}{'+' if t['partial'] else ''} ({gb(t['old'])} older than {TEMP_AGE_DAYS} days could be removed)")
        if t["old"] >= 5e8:
            tips.append("Say “clean up my temp files” and I will remove the old ones after you confirm.")
    s = info.get("startup") or []
    if s:
        lines.append(f"• {len(s)} program{'s' if len(s) != 1 else ''} start with Windows: " + ", ".join(s[:8]) + ("…" if len(s) > 8 else ""))
        if len(s) > 12:
            tips.append("Many programs start with Windows, which slows the start. Turn some off in Task Manager > Startup apps.")
    h = info.get("heavy") or []
    if h:
        lines.append("• Using the most memory: " + ", ".join(f"{n} ({gb(v)})" for n, v in h))
    if info.get("update"):
        lines.append(f"• Last Windows update installed: {info['update']}")
    if "backup" in info:
        last = info["backup"].get("last")
        days = (time.time() - last) / 86400 if last else None
        lines.append("• Last data backup: " + (backup_age(last)))
        if days is None or days > 14:
            tips.append("Your settings, notes and tokens have " + ("never been backed up" if days is None else "not been backed up for over two weeks") + ". Use Settings > Daily > Backup.")
    for name, size in (info.get("folders") or {}).items():
        if size is not None:
            lines.append(f"• {name}: {gb(size)}")
    lines += ["", *(["Suggestions:"] + ["• " + x for x in tips] if tips else ["Everything looks healthy, sir."])]
    return "\n".join(lines).strip()


HEALTH = re.compile(r"(?:how(?:'s| is)(?: my)?\s+(?:pc|computer|laptop|machine)(?:\s+(?:doing|running|holding up))?|(?:run|do|give me|show me)\s+(?:a\s+)?(?:pc\s+|computer\s+|system\s+)?(?:health\s?check|maintenance\s+report|health\s+report|checkup|check-up)|(?:check|scan|test)\s+(?:my\s+)?(?:pc|computer|laptop|system)(?:\s+health)?|(?:is|are)\s+(?:my\s+)?(?:pc|computer|laptop)\s+(?:ok|okay|healthy|fine|alright)|(?:pc|computer|system)\s+(?:health|maintenance)(?:\s+(?:check|report))?|how\s+much\s+(?:disk\s+space|disk|storage|space)\s+(?:do\s+i\s+have|is\s+left)(?:\s+left)?|(?:maintenance|health)\s+(?:check|report))", re.I)
CLEAN = re.compile(r"(?:clean\s*(?:up)?|clear|delete|remove|empty|free\s+up)\s+(?:out\s+)?(?:my\s+|the\s+|all\s+)?(?:old\s+)?(?:temp(?:orary)?\s+files?|temp\s+folder|junk(?:\s+files?)?|temp|cache\s+files?)|free\s+up\s+(?:some\s+)?(?:disk\s+)?space", re.I)
YES = re.compile(r"(?:yes|yeah|yep|ok|okay|sure|go ahead|confirm|do it)[,.! ]*(?:please[,.! ]*)?(?:clean(?:\s+(?:them|it|up|the temp files))?|delete(?:\s+them)?|go ahead|do it)?|clean\s+them|delete\s+them|confirm\s+cleanup", re.I)


def command(text: str, snapshot_fn, remote: bool = False, folders: dict | None = None, now: float | None = None, backup: dict | None = None) -> str | None:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?", "", t, flags=re.I)
    t = re.sub(r"\s*(?:please|for me|now)?\s*[.!?]*$", "", t, flags=re.I).strip()
    if not t or len(t) > 120:
        return None
    now = time.time() if now is None else now
    if PENDING["at"] and now - PENDING["at"] <= CONFIRM_SECONDS and YES.fullmatch(t):
        PENDING["at"] = 0.0
        if remote:
            return "For safety I only delete files when you ask at the PC itself, sir."
        res = temp_clean(now=now)
        return f"Done, sir: removed {res['removed']} old temp files and freed {gb(res['freed'])}." + (f" {res['failed']} were in use and left alone." if res["failed"] else "")
    if CLEAN.fullmatch(t):
        if remote:
            return "I only delete files when you ask at the PC itself, sir. I can tell you the size with “how's my PC?”."
        scan = temp_scan(now=now)
        if scan["old"] < 20e6:
            PENDING["at"] = 0.0
            return f"Your temp folder holds {gb(scan['total'])} and almost none of it is old enough to remove, sir."
        PENDING["at"] = now
        return f"I can delete {scan['old_files']} temp files older than {TEMP_AGE_DAYS} days, about {gb(scan['old'])}{' (at least)' if scan['partial'] else ''}. Files in use are skipped. Say “yes, clean them” within two minutes to go ahead."
    if HEALTH.fullmatch(t):
        return report(collect(snapshot_fn(), folders, backup))
    return None
