"""Find, show, hide and focus the Jarvis app window (Windows only; every function is a harmless no-op elsewhere)."""
import os
import sys
import time

IS_WINDOWS = sys.platform == "win32"
log_hook = None   # set by the tray app: called with a sentence whenever this module simulates a key press
SW_MINIMIZE, SW_RESTORE, SW_SHOW = 6, 9, 5
BROWSER_CLASSES = ("Chrome_WidgetWin_1",)   # Edge and Chrome windows; this keeps the console window (also titled Jarvis) out
APP_BROWSERS = ("msedge.exe", "chrome.exe")  # the programs the tray opens the app window with (see jarvis_tray.find_browser)


def is_app_title(title: str) -> bool:
    """The app window shows the page title alone: "Jarvis" (or "⏰ …" while an alarm rings). A normal browser window
    or tab whose page happens to start with "Jarvis" (say a Spotify developer app named Jarvis) is not it."""
    title = (title or "").strip()
    return title == "Jarvis" or title.startswith("⏰")


def is_app_program(exe_path: str) -> bool:
    return (exe_path or "").replace("\\", "/").rsplit("/", 1)[-1].lower() in APP_BROWSERS


def _exe_of(hwnd) -> str:
    """Full path of the program that owns a window ("" when Windows will not say)."""
    import ctypes
    from ctypes import wintypes
    pid = wintypes.DWORD()
    _user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid.value)          # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf, size = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
        return buf.value if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)) else ""
    finally:
        kernel32.CloseHandle(handle)


def _user32():
    import ctypes
    return ctypes.windll.user32


def find_window(match=None, visible_only=True):
    """Handle of the visible Jarvis app window, or None. match(title) picks another Jarvis window (the quick-ask box)."""
    if not IS_WINDOWS:
        return None
    match = match or is_app_title
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    found = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(hwnd, _lparam):
        if visible_only and not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        if not match(title.value):
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value in BROWSER_CLASSES:
            try:
                exe = _exe_of(hwnd)
            except Exception:
                exe = ""
            if not exe or is_app_program(exe):            # Opera, Brave, Vivaldi… use the same window class: skip them
                found.append(hwnd)
        return True

    user32.EnumWindows(callback_type(each), 0)
    return found[0] if found else None


def is_minimized(hwnd) -> bool:
    return bool(IS_WINDOWS and hwnd and _user32().IsIconic(hwnd))


def is_foreground(hwnd) -> bool:
    return bool(IS_WINDOWS and hwnd and _user32().GetForegroundWindow() == hwnd)


def minimize(hwnd=None) -> bool:
    hwnd = hwnd or find_window()
    if not hwnd:
        return False
    _user32().ShowWindow(hwnd, SW_MINIMIZE)
    return True


def focus(hwnd=None) -> bool:
    """Bring the window to the front, restoring it first when minimized."""
    hwnd = hwnd or find_window()
    if not hwnd:
        return False
    user32 = _user32()
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    else:
        user32.ShowWindow(hwnd, SW_SHOW)
    # Windows only lets the foreground process steal focus; a tap on Alt lets this one through.
    if log_hook:
        log_hook("brought the Jarvis window to the front (a simulated Alt key press, which can wake the screen)")
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)
    return True


def hide(hwnd) -> bool:
    """Put a window away without closing it (it comes back at once with focus())."""
    if not IS_WINDOWS or not hwnd:
        return False
    _user32().ShowWindow(hwnd, 0)                                          # SW_HIDE
    return True


def keep_on_top(hwnd) -> bool:
    if not IS_WINDOWS or not hwnd:
        return False
    import ctypes
    user32 = _user32()
    user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    return bool(user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040))   # HWND_TOPMOST; SWP_NOSIZE|NOMOVE|SHOWWINDOW


def place(hwnd, x: int, y: int, width: int, height: int) -> bool:
    if not IS_WINDOWS or not hwnd:
        return False
    import ctypes
    user32 = _user32()
    user32.MoveWindow.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    return bool(user32.MoveWindow(hwnd, int(x), int(y), int(width), int(height), 1))


def screen_size() -> tuple[int, int]:
    if not IS_WINDOWS:
        return (1920, 1080)
    user32 = _user32()
    return (user32.GetSystemMetrics(0) or 1920, user32.GetSystemMetrics(1) or 1080)


def set_icon(hwnd, ico_path) -> bool:
    """Give the window (and its taskbar button) the Jarvis icon instead of the browser's."""
    if not IS_WINDOWS or not hwnd or not os.path.isfile(str(ico_path)):
        return False
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.LoadImageW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.SendMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_size_t, ctypes.c_void_p]
    done = False
    for kind, size in ((0, 16), (1, 48)):                                  # ICON_SMALL, ICON_BIG
        icon = user32.LoadImageW(None, str(ico_path), 1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
        if icon:
            user32.SendMessageW(hwnd, 0x0080, kind, icon)                   # WM_SETICON
            done = True
    return done


def hide_for_computer_task():
    """Minimise the app window while Jarvis drives the screen. Returns a token for restore_after_computer_task."""
    if os.environ.get("JARVIS_APP_WINDOW") != "1":
        return None
    hwnd = find_window()
    if not hwnd or is_minimized(hwnd):
        return None
    minimize(hwnd)
    time.sleep(0.6)   # let the minimise animation finish before the next screenshot
    return hwnd


def restore_after_computer_task(token) -> None:
    if token:
        try:
            focus(token if _user32().IsWindow(token) else None)
        except Exception:
            pass
