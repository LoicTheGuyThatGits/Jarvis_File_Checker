"""Your data: what Jarvis keeps on this PC, grouped the way a person thinks of it, and what leaves the PC.

Everything Jarvis remembers is in the data folder next to the program (plus the Jarvis Code projects in the workspace folder,
and the chats saved by the browser itself). This module lists it with sizes, and deletes a group on request. Deleting is
permanent; the server restarts Jarvis afterwards so nothing it had loaded in memory is written back.
"""
from __future__ import annotations

import shutil
from pathlib import Path

# key, name, what it is, paths in the data folder ("ROOT/..." for the program folder)
GROUPS = [
    ("chats", "Chat history", "The searchable history of your chats (app, phone, Telegram, calls), used to pick up where you left off.", ["history"]),
    ("memory", "Memory", "What you asked Jarvis to remember and the facts it learned about you from chats.", ["memory.json"]),
    ("training", "Training log", "Your messages and Jarvis's answers kept for training your own model, ratings, and model comparisons.", ["training", "bench"]),
    ("notes", "Notes and documents", "Your notes, and the documents you added so Jarvis can answer from them.", ["notes.json", "documents"]),
    ("planner", "Planner", "To-do list, calendar, imported calendars, reminders, countdowns, focus sessions, evening recaps and your stops.",
     ["planner.json", "reminders.json", "countdowns.json", "calendar.json", "recap.json", "focus.json", "transport.json"]),
    ("school", "School", "Timetable, homework, grades, exams, flashcards and the study coach's plan.",
     ["timetable.json", "grades.json", "study.json", "coach.json"]),
    ("routines", "Routines and shortcuts", "Your routines and keyboard shortcut choices.", ["routines.json", "routines-state.json", "shortcuts.json"]),
    ("computer", "Computer control", "What autopilot learned and was shown, its settings, screen awareness and Jarvis Code settings.",
     ["autopilot-learned.json", "computer-control.json", "awareness.json", "coder.json"]),
    ("projects", "Jarvis Code projects", "The programs and pages Jarvis Code made with you (the workspace folder).", ["ROOT/workspace"]),
    ("accounts", "Sign-ins and connections", "Telegram bot, Gmail app password, Spotify and Google Classroom sign-ins, connected tools (MCP) and phone pairing. Deleting signs Jarvis out of all of them.",
     ["telegram.json", "mail.json", "spotify.json", "classroom.json", "mcp.json", "phone.json"]),
    ("settings", "Settings", "Your choices: language, how Jarvis addresses you, your town, models, voice, alerts, calls and updates. Deleting starts Jarvis like new, with the setup guide.",
     ["settings.json", "address.txt", "voice.json", "proactive.json", "alerts.json", "network.json", "advisor.json", "calls.json", "backup.json",
      "memory_settings.json", "filecheck.json", "tray.json"]),
    ("logs", "Logs and old copies", "What Jarvis printed while running, crash reports, the last self-check, and old copies of files replaced by updates.",
     ["jarvis.log", "crash.log", "install.log", "selftest.txt", "file-backups"]),
]
KEYS = [g[0] for g in GROUPS]


def _path(root: Path, rel: str) -> Path:
    return Path(root) / rel[5:] if rel.startswith("ROOT/") else Path(root) / "data" / rel


def _size(p: Path) -> tuple[int, int]:
    """(bytes, files)."""
    if p.is_file():
        return p.stat().st_size, 1
    total = count = 0
    if p.is_dir():
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
                    count += 1
            except OSError:
                pass
    return total, count


def inventory(root: Path) -> list[dict]:
    out = []
    for key, name, desc, rels in GROUPS:
        size = files = 0
        for rel in rels:
            b, n = _size(_path(root, rel))
            size += b
            files += n
        out.append({"key": key, "name": name, "description": desc, "bytes": size, "files": files})
    return out


def delete(root: Path, keys: list[str]) -> dict:
    """Removes the groups' files and folders. Returns {"deleted": [keys], "failed": [[path, reason]]}."""
    done, failed = [], []
    for key, _, _, rels in GROUPS:
        if key not in keys:
            continue
        ok = True
        for rel in rels:
            p = _path(root, rel)
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                elif p.exists():
                    try:
                        p.unlink()
                    except PermissionError:
                        if p.suffix not in (".log", ".txt"):
                            raise
                        p.write_bytes(b"")                 # a log still open by the tray app: empty it instead
            except OSError as exc:
                ok = False
                failed.append([rel.replace("ROOT/", ""), str(exc)[:200]])
        if ok:
            done.append(key)
    return {"deleted": done, "failed": failed}
