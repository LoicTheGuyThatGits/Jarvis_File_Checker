"""Jarvis as an app: a tray icon, a tabless app window, a global hotkey and start-with-Windows.

Start it with start-jarvis-app.bat (which sets the AI provider first). It starts the Jarvis server in the
background, opens Jarvis in its own window (Edge or Chrome app mode) and then lives in the system tray.
Closing the window leaves Jarvis running; press the hotkey (Ctrl+Alt+J) or double-click the tray icon to bring it back.

  python jarvis_tray.py              start, open the window
  python jarvis_tray.py --hidden     start in the tray only (used when Windows starts)
  python jarvis_tray.py --detach     same, but hand over to a hidden background copy and return at once
  python jarvis_tray.py --shortcut   put a Jarvis shortcut with its icon on the desktop
  python jarvis_tray.py --autostart on|off|status
"""
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

APP = Path(__file__).resolve().parent          # ROOT/app
ROOT = APP.parent                               # the Jarvis folder
DATA = ROOT / "data"
HOST = "127.0.0.1"
PORT = int(os.environ.get("JARVIS_PORT", "8765"))
URL = f"http://{HOST}:{PORT}"
IS_WINDOWS = sys.platform == "win32"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "Jarvis"
HOTKEY = os.environ.get("JARVIS_HOTKEY", "ctrl+alt+j")
LOG = DATA / "jarvis.log"

sys.path.insert(0, str(APP))
import jarvis_window  # noqa: E402


# ---------------------------------------------------------------- pure helpers (testable anywhere)
def port_open(timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_server(seconds: float = 40.0) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if port_open():
            return True
        time.sleep(0.25)
    return False


def parse_hotkey(text: str):
    """'ctrl+alt+j' -> (modifier flags, virtual key code), or None when it cannot be understood."""
    mods = {"ctrl": 0x0002, "control": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008}
    flags, key = 0, None
    for part in [p.strip().lower() for p in text.split("+") if p.strip()]:
        if part in mods:
            flags |= mods[part]
        elif len(part) == 1 and part.isalnum():
            key = ord(part.upper())
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            key = 0x6F + int(part[1:])
        else:
            return None
    return (flags, key) if flags and key else None


def load_prefs(root: Path = ROOT) -> dict:
    import json
    try:
        data = json.loads((root / "data" / "tray.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_prefs(prefs: dict, root: Path = ROOT) -> None:
    import json
    folder = root / "data"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "tray.json").write_text(json.dumps(prefs, indent=2), encoding="utf-8")


def find_browser(env=None, exists=os.path.exists):
    """Path of Edge (preferred, it ships with Windows) or Chrome, or None."""
    env = env if env is not None else os.environ
    bases = [env.get("ProgramFiles(x86)"), env.get("ProgramFiles"), env.get("LOCALAPPDATA")]
    names = [("Microsoft", "Edge", "Application", "msedge.exe"), ("Google", "Chrome", "Application", "chrome.exe")]
    for parts in names:
        for base in bases:
            if base:
                path = os.path.join(base, *parts)
                if exists(path):
                    return path
    return None


def profile_dir(root: Path = ROOT) -> Path:
    """The app window's own browser profile, in data/. Moves the one older versions kept next to the program."""
    new, old = root / "data" / "app-profile", root / "app-profile"
    if old.exists() and not new.exists():
        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)
        except OSError:
            return old                                  # in use right now; keep using it
    return new


def app_command(browser: str, url: str = URL, root: Path = ROOT, env=None) -> list[str]:
    env = env if env is not None else os.environ
    cmd = [browser, f"--app={url}", "--no-first-run", "--no-default-browser-check", "--autoplay-policy=no-user-gesture-required"]
    if (env.get("JARVIS_APP_PROFILE") or "own").lower() != "default":
        # Its own profile keeps Jarvis separate from your normal browsing and makes the flags above reliable.
        cmd += [f"--user-data-dir={profile_dir(root)}"]
    return cmd


ICON_ICO = ROOT / "web" / "icons" / "jarvis.ico"
ICON_PNG = ROOT / "web" / "icons" / "jarvis.png"


def shortcut_script(root: Path = ROOT) -> str:
    """PowerShell that creates Desktop\\Jarvis.lnk (target: the app launcher, icon: jarvis.ico)."""
    q = lambda p: str(p).replace("'", "''")
    return (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Jarvis.lnk'));"
        f"$s.TargetPath='{q(root / 'start-jarvis-app.bat')}';$s.WorkingDirectory='{q(root)}';"
        f"$s.IconLocation='{q(root / 'web' / 'icons' / 'jarvis.ico')},0';$s.WindowStyle=7;$s.Description='Jarvis';$s.Save();"
        "Write-Output (Join-Path $d 'Jarvis.lnk')"
    )


def create_shortcut() -> str | None:
    if not IS_WINDOWS:
        return None
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", shortcut_script()], capture_output=True, text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return out.stdout.strip() or None if out.returncode == 0 else None


def autostart_value(root: Path = ROOT) -> str:
    return f'cmd /c start "" /min "{root / "start-jarvis-app.bat"}" hidden'


def autostart_get() -> bool:
    if not IS_WINDOWS:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_NAME)
            return True
    except OSError:
        return False


def autostart_set(on: bool) -> bool:
    if not IS_WINDOWS:
        return False
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, autostart_value())
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass
    return autostart_get() == on


# ---------------------------------------------------------------- the app
class App:
    def __init__(self, hidden: bool):
        self.hidden = hidden
        self.server = None          # the server process, only when this app started it
        self.icon = None
        self.quitting = threading.Event()
        self.keep_awake = bool(load_prefs().get("keep_awake"))
        self.restarts: list[float] = []

    # -- server
    def python_for_server(self) -> str:
        exe = Path(sys.executable)
        if exe.name.lower() == "pythonw.exe" and (exe.with_name("python.exe")).exists():
            return str(exe.with_name("python.exe"))   # pythonw has no console, which the server's printing needs
        return str(exe)

    def running_server_is_current(self) -> bool:
        """True when the server on our port is this folder's server.py, unchanged since it started."""
        import json
        import urllib.request
        try:
            with urllib.request.urlopen(f"{URL}/api/health", timeout=3) as response:
                info = json.loads(response.read().decode("utf-8"))
        except Exception:
            return False                               # an older version without /api/health, or not Jarvis at all
        try:
            return Path(info.get("server", "")).resolve() == (APP / "server.py").resolve() and int(info.get("stamp", -1)) == int((APP / "server.py").stat().st_mtime)
        except (OSError, ValueError):
            return False

    def stop_stale_server(self) -> bool:
        """Stop an out-of-date Jarvis server that still holds the port (for example from before an update)."""
        try:
            import psutil
        except ImportError:
            return False
        stopped = False
        for conn in psutil.net_connections(kind="tcp"):
            if conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port == PORT and conn.pid:
                try:
                    proc = psutil.Process(conn.pid)
                    if "server.py" in " ".join(proc.cmdline()).lower():
                        log(f"stopping an out-of-date Jarvis server (pid {conn.pid})")
                        proc.terminate()
                        proc.wait(5)
                        stopped = True
                except Exception as exc:
                    log(f"could not stop pid {conn.pid}: {exc}")
        return stopped

    def start_server(self) -> None:
        if port_open():
            if self.running_server_is_current():
                return                                 # already running, for example from start-jarvis.bat
            if not self.stop_stale_server():
                log("port is in use by something that is not this Jarvis")
                self.notify_blocking(f"Something is already using port {PORT}, and it is not up to date with this Jarvis folder. Quit Jarvis everywhere (tray icon > Quit Jarvis, or end python.exe in Task Manager) and start it again.")
                return
            time.sleep(0.5)
        env = {**os.environ, "JARVIS_NO_BROWSER": "1", "JARVIS_APP_WINDOW": "1", "PYTHONIOENCODING": "utf-8"}
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        DATA.mkdir(parents=True, exist_ok=True)
        log = open(LOG, "ab")
        log.write(f"\n--- starting {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n".encode())
        log.flush()
        self.server = subprocess.Popen([self.python_for_server(), str(APP / "server.py")], cwd=str(ROOT), env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL, creationflags=flags)

    def stop_server(self) -> None:
        proc, self.server = self.server, None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()

    def restart_server(self) -> None:
        self.stop_server()
        if port_open():
            self.notify("Jarvis was started somewhere else, so it was left running.")
            return
        self.start_server()
        self.notify("Jarvis restarted." if wait_for_server() else "Jarvis did not start. See jarvis.log.")

    # -- window
    def open_window(self) -> None:
        if not wait_for_server(15):
            self.notify("The Jarvis server is not running. See jarvis.log.")
            return
        hwnd = jarvis_window.find_window()
        if hwnd:
            jarvis_window.focus(hwnd)
            jarvis_window.set_icon(hwnd, ICON_ICO)
            return
        browser = find_browser()
        if not browser:
            import webbrowser
            webbrowser.open(URL)
            return
        subprocess.Popen(app_command(browser), close_fds=True)
        threading.Thread(target=self.apply_window_icon, daemon=True).start()

    def apply_window_icon(self) -> None:
        for _ in range(60):                    # the window appears a moment after the browser starts
            hwnd = jarvis_window.find_window()
            if hwnd:
                time.sleep(0.5)
                jarvis_window.set_icon(hwnd, ICON_ICO)
                return
            time.sleep(0.5)

    def toggle_window(self) -> None:
        hwnd = jarvis_window.find_window()
        if hwnd and jarvis_window.is_foreground(hwnd) and not jarvis_window.is_minimized(hwnd):
            jarvis_window.minimize(hwnd)
        else:
            self.open_window()

    # -- hotkey (Windows)
    def hotkey_loop(self) -> None:
        parsed = parse_hotkey(HOTKEY)
        if not IS_WINDOWS or not parsed:
            return
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, 1, parsed[0] | 0x4000, parsed[1]):   # 0x4000 = no auto-repeat
            self.notify(f"{HOTKEY} is already used by another program. Set JARVIS_HOTKEY to another combination.")
            return
        msg = wintypes.MSG()
        while not self.quitting.is_set():
            if user32.PeekMessageW(ctypes.byref(msg), None, 0x0312, 0x0312, 1):
                self.toggle_window()
            else:
                time.sleep(0.05)
        user32.UnregisterHotKey(None, 1)

    # -- tray
    def notify(self, text: str) -> None:
        try:
            if self.icon:
                self.icon.notify(text, "Jarvis")
                return
        except Exception:
            pass
        print(text)

    def make_image(self):
        from PIL import Image, ImageDraw
        if ICON_PNG.is_file():
            return Image.open(ICON_PNG).convert("RGBA")
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((2, 2, 61, 61), fill=(5, 20, 32, 255), outline=(94, 231, 255, 255), width=4)
        d.ellipse((17, 17, 46, 46), outline=(94, 231, 255, 255), width=3)
        d.ellipse((26, 26, 37, 37), fill=(190, 250, 255, 255))
        return img

    def quit(self, icon=None, item=None) -> None:
        self.quitting.set()
        self.stop_server()
        if self.icon:
            self.icon.stop()

    def run_tray(self) -> None:
        try:
            import pystray
        except ImportError:
            self.notify_blocking("The tray icon needs the pystray package. Run install-jarvis.bat again, or: .venv\\Scripts\\pip install pystray")
            self.run_without_tray()
            return
        menu = pystray.Menu(
            pystray.MenuItem("Open Jarvis", lambda i, it: self.open_window(), default=True),
            pystray.MenuItem("Restart Jarvis", lambda i, it: threading.Thread(target=self.restart_server, daemon=True).start()),
            pystray.MenuItem("Add desktop shortcut", lambda i, it: threading.Thread(target=lambda: self.notify(("Shortcut added to the desktop: Jarvis" if create_shortcut() else "Could not create the shortcut.")), daemon=True).start()),
            pystray.MenuItem("Keep PC awake", lambda i, it: self.set_keep_awake(not self.keep_awake), checked=lambda it: self.keep_awake),
            pystray.MenuItem("Start with Windows", lambda i, it: autostart_set(not autostart_get()), checked=lambda it: autostart_get()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Jarvis", self.quit),
        )
        self.icon = pystray.Icon("Jarvis", self.make_image(), "Jarvis", menu)
        self.icon.run(setup=self.after_icon)

    # -- keep the PC from going to sleep (the screen may still turn off and lock)
    def set_keep_awake(self, on: bool) -> None:
        self.keep_awake = bool(on)
        prefs = load_prefs()
        prefs["keep_awake"] = self.keep_awake
        save_prefs(prefs)
        log("keep awake " + ("on: Windows will not go to sleep by itself" if on else "off"))
        self.notify("Jarvis will keep this PC awake while it is running." if on else "Jarvis no longer keeps this PC awake.")

    def awake_loop(self) -> None:
        if not IS_WINDOWS:
            return
        import ctypes
        kernel32 = ctypes.windll.kernel32
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001      # no ES_DISPLAY_REQUIRED: the screen may still turn off
        active = False
        while not self.quitting.is_set():
            if self.keep_awake and not active:
                kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
                active = True
            elif not self.keep_awake and active:
                kernel32.SetThreadExecutionState(ES_CONTINUOUS)
                active = False
            self.quitting.wait(2)
        kernel32.SetThreadExecutionState(ES_CONTINUOUS)

    # -- restart the server if it ever stops by itself
    def watchdog_once(self) -> bool:
        proc = self.server
        if not proc or proc.poll() is None or self.quitting.is_set():
            return False
        now = time.time()
        self.restarts = [t for t in self.restarts if now - t < 600]
        log(f"the Jarvis server stopped (exit code {proc.returncode})")
        if len(self.restarts) >= 5:
            self.server = None
            self.notify("The Jarvis server keeps stopping. See data/jarvis.log.")
            return False
        self.restarts.append(now)
        self.server = None
        self.start_server()
        log("the Jarvis server was restarted")
        return True

    def watchdog_loop(self) -> None:
        while not self.quitting.wait(15):
            try:
                self.watchdog_once()
            except Exception as exc:
                log(f"watchdog error: {exc}")

    def after_icon(self, icon) -> None:
        icon.visible = True
        jarvis_window.log_hook = log
        threading.Thread(target=self.awake_loop, daemon=True).start()
        threading.Thread(target=self.watchdog_loop, daemon=True).start()
        threading.Thread(target=self.hotkey_loop, daemon=True).start()
        if not self.hidden:
            threading.Thread(target=self.open_window, daemon=True).start()
        else:
            threading.Thread(target=lambda: (wait_for_server(), self.notify(f"Jarvis is ready. Press {HOTKEY.replace('+', ' + ').title()} to open it.")), daemon=True).start()

    def run_without_tray(self) -> None:
        threading.Thread(target=self.hotkey_loop, daemon=True).start()
        if not self.hidden:
            self.open_window()
        try:
            while not self.quitting.is_set():
                time.sleep(1)
        finally:
            self.stop_server()

    @staticmethod
    def notify_blocking(text: str) -> None:
        if IS_WINDOWS:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, text, "Jarvis", 0x40)
        else:
            print(text)

    def run(self) -> None:
        self.start_server()
        self.run_tray()


_LOCK = None


def single_instance() -> bool:
    """False when another Jarvis tray app is already running (it holds a local lock port next to the server's)."""
    global _LOCK
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((HOST, PORT + 1))
    except OSError:
        sock.close()
        return False
    _LOCK = sock                                       # held until this process ends
    return True


def log(text: str) -> None:
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        with open(LOG, "ab") as handle:
            handle.write(f"[tray {time.strftime('%H:%M:%S')}] {text}\n".encode("utf-8", "replace"))
    except OSError:
        pass


def main(argv: list[str]) -> int:
    if "--autostart" in argv:
        i = argv.index("--autostart")
        mode = argv[i + 1] if i + 1 < len(argv) else "status"
        if mode in ("on", "off"):
            ok = autostart_set(mode == "on")
            print(f"Jarvis will {'now' if mode == 'on' else 'no longer'} start with Windows." if ok else "Could not change the startup setting.")
            return 0 if ok else 1
        print("on" if autostart_get() else "off")
        return 0
    if "--shortcut" in argv:
        path = create_shortcut()
        print(f"Created {path}" if path else "Could not create the shortcut.")
        return 0 if path else 1
    if "--detach" in argv:
        # Hand over to a copy with no console window, so double-clicking a .bat leaves nothing open behind it.
        rest = [a for a in argv if a != "--detach"]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *rest], cwd=str(ROOT), creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    hidden = "--hidden" in argv or "hidden" in argv
    log(f"launched (hidden={hidden}, python={sys.executable})")
    if not single_instance():
        log("another Jarvis tray app is already running")
        if not hidden and wait_for_server(5):
            App(False).open_window()           # a second launch just brings the window forward
        return 0
    App(hidden).run()
    log("tray app ended")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except BaseException:
        import traceback
        detail = traceback.format_exc()
        log("crashed:\n" + detail)
        App.notify_blocking("Jarvis could not start the tray app:\n\n" + detail[-900:] + "\nThe full message is in jarvis.log.")
        sys.exit(1)
