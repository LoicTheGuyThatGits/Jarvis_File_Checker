"""The open windows: list them, bring one to the front, minimise, maximise or restore it.

The Windows calls live in WinBackend (ctypes, no extra package). Everything else works on plain lists so it can be tested
anywhere:  find(windows, "the word document")  ->  the window that phrase means.
"""
from __future__ import annotations

import ctypes
import os
import re
import time

SKIP_TITLES = {"Program Manager", "Windows Input Experience", "Microsoft Text Input Application", "Settings", "NVIDIA GeForce Overlay", "Windows Shell Experience Host",
               "Jarvis overlay", "Jarvis Autopilot"}
APP_WORDS = {"word": "WINWORD", "excel": "EXCEL", "powerpoint": "POWERPNT", "outlook": "OUTLOOK", "chrome": "chrome", "google chrome": "chrome", "edge": "msedge",
             "firefox": "firefox", "notepad": "notepad", "explorer": "explorer", "file explorer": "explorer", "vs code": "Code", "vscode": "Code",
             "visual studio code": "Code", "visual studio": "devenv", "spotify": "Spotify", "discord": "Discord", "teams": "ms-teams", "terminal": "WindowsTerminal",
             "unity": "Unity", "paint": "mspaint", "calculator": "CalculatorApp", "steam": "steam", "obs": "obs64", "blender": "blender", "photoshop": "Photoshop"}


class WinBackend:
    def __init__(self):
        if os.name != "nt":
            raise OSError("Windows only")
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32

    def _process_name(self, hwnd) -> str:
        pid = ctypes.c_ulong()
        self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = self.kernel32.OpenProcess(0x1000, False, pid.value)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ""
        try:
            size = ctypes.c_ulong(512)
            buf = ctypes.create_unicode_buffer(512)
            if self.kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return os.path.splitext(os.path.basename(buf.value))[0]
            return ""
        finally:
            self.kernel32.CloseHandle(handle)

    def windows(self) -> list[dict]:
        out = []
        proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def each(hwnd, _):
            if not self.user32.IsWindowVisible(hwnd) or self.user32.GetWindow(hwnd, 4):        # GW_OWNER: skip owned pop-ups
                return True
            if self.user32.GetWindowLongW(hwnd, -20) & 0x80:                                   # WS_EX_TOOLWINDOW: not a real window (overlays, palettes)
                return True
            length = self.user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            self.user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            if not title or title in SKIP_TITLES:
                return True
            out.append({"id": int(hwnd), "title": title, "app": self._process_name(hwnd), "minimized": bool(self.user32.IsIconic(hwnd))})
            return True
        self.user32.EnumWindows(proto(each), 0)
        return out

    def show(self, wid: int, how: str) -> None:
        hwnd = ctypes.c_void_p(wid)
        if how == "front":
            if self.user32.IsIconic(hwnd):
                self.user32.ShowWindow(hwnd, 9)                # SW_RESTORE
            # Windows only lets the active app bring another window forward: borrow the input of the current front window
            front = self.user32.GetForegroundWindow()
            this_thread = self.kernel32.GetCurrentThreadId()
            front_thread = self.user32.GetWindowThreadProcessId(front, None)
            self.user32.AttachThreadInput(this_thread, front_thread, True)
            self.user32.keybd_event(0x12, 0, 0, 0); self.user32.keybd_event(0x12, 0, 2, 0)       # a tap of Alt unlocks SetForegroundWindow
            self.user32.SetForegroundWindow(hwnd)
            self.user32.BringWindowToTop(hwnd)
            self.user32.AttachThreadInput(this_thread, front_thread, False)
        else:
            self.user32.ShowWindow(hwnd, {"minimize": 6, "maximize": 3, "restore": 9}[how])

    def foreground(self) -> int:
        return int(self.user32.GetForegroundWindow() or 0)


def find(windows: list[dict], phrase: str, skip: str = "Jarvis") -> list[dict]:
    """The windows a phrase like "the word document", "chrome", "report.docx" or "the Unity window" means, best first."""
    p = re.sub(r"\s+", " ", (phrase or "").strip().lower())
    p = re.sub(r"^(?:the|my|a|that|this)\s+", "", p)
    p = re.sub(r"\s+(?:window|app|application|program|document|tab)$", "", p).strip(" \"'“”")
    if not p:
        return []
    proc = APP_WORDS.get(p, "").lower()
    scored = []
    for w in windows:
        title, app = w["title"].lower(), (w.get("app") or "").lower()
        if skip and skip.lower() in title and "jarvis" not in p:
            continue
        if title == p:
            score = 100
        elif proc and app == proc:
            score = 90
        elif app == p:
            score = 85
        elif re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", title):
            score = 70
        elif len(p) >= 4 and p in title:
            score = 50
        elif len(p) >= 4 and p in app:
            score = 45
        else:
            continue
        scored.append((score, w))
    if not scored:
        return []
    top = max(s for s, _ in scored)
    return [w for s, w in sorted(scored, key=lambda t: -t[0]) if s == top]


def describe(windows: list[dict], front: int = 0, limit: int = 25) -> str:
    if not windows:
        return "No windows are open."
    lines = []
    for n, w in enumerate(windows[:limit], 1):
        tag = " (in front)" if w["id"] == front else " (minimised)" if w.get("minimized") else ""
        lines.append(f"W{n}. “{w['title'][:90]}” — {w.get('app') or '?'}{tag}")
    return "Open windows (you may bring one to the front with {\"type\":\"focus_window\",\"window\":N}):\n" + "\n".join(lines)
