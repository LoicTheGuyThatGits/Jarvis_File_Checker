"""Find, show, hide and focus the Jarvis app window (Windows only; every function is a harmless no-op elsewhere)."""
import os
import sys
import time

IS_WINDOWS = sys.platform == "win32"
log_hook = None   # set by the tray app: called with a sentence whenever this module simulates a key press
SW_MINIMIZE, SW_RESTORE, SW_SHOW = 6, 9, 5
BROWSER_CLASSES = ("Chrome_WidgetWin_1",)   # Edge and Chrome windows; this keeps the console window (also titled Jarvis) out


def _user32():
    import ctypes
    return ctypes.windll.user32


def find_window():
    """Handle of the visible Jarvis app window, or None."""
    if not IS_WINDOWS:
        return None
    import ctypes
    from ctypes import wintypes
    user32 = _user32()
    found = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        if not title.value.startswith("Jarvis"):
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value in BROWSER_CLASSES:
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
