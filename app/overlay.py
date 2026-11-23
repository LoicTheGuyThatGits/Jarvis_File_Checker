"""The Autopilot overlay: shows on the screen what Autopilot is about to do, with a Stop button.

Two small windows drawn above everything else:
  - a see-through, click-through layer that outlines the control Autopilot is about to click, with a label ("Click: Save");
    clicks go straight through it to the app underneath;
  - a status bar ("Autopilot · step 3 of 40 · Clicking Save") with a Stop button, kept away from where Autopilot clicks.
Both are left out of screenshots (Windows 10 2004 or newer), so the AI model and the OCR never see them; on older Windows they
are hidden for the instant a screenshot is taken. Both are named "Jarvis …", so the screen map passes over them.

    OVERLAY.begin(text, on_stop)   show the status bar (on_stop is called when Stop is clicked)
    OVERLAY.status(text)           change its text
    OVERLAY.target(action)         outline what a computer action will touch (x, y and "box" in screen pixels)
    OVERLAY.clear()                remove the outline
    OVERLAY.end()                  hide everything
    with OVERLAY.out_of_picture(): take a screenshot without the overlay in it

Every call is safe anywhere: without Windows or tkinter the overlay is simply not shown (OVERLAY.error says why). The windows
live in their own thread; other threads only put requests in a queue. The layout (where things go) is plain functions, tested
without a screen.
"""
from __future__ import annotations

import contextlib
import os
import queue
import threading
import time

ACCENT, LABEL_BG, BAR_BG, KEY = "#29d3ff", "#0b3b4a", "#10161c", "#010203"
VERBS = {"click": "Click", "double_click": "Double-click", "right_click": "Right-click", "scroll": "Scroll", "type_text": "Type",
         "press_key": "Press", "hotkey": "Keys", "focus_window": "Switch to", "window_state": "Window", "open_app": "Open",
         "open_url": "Open", "open_folder": "Open", "list_folder": "Look in", "read_file": "Read", "write_file": "Write", "wait": "Wait",
         "zoom": "Look closer", "web_open": "Open in the browser", "web_click": "Click on the page", "web_type": "Type on the page",
         "web_select": "Choose on the page", "web_key": "Press on the page", "web_scroll": "Scroll the page", "web_back": "Go back",
         "web_read": "Read the page", "web_tab": "Switch tab"}


# ---------------- layout (no screen needed) ----------------
def describe(action: dict) -> str:
    """'Click: the Save button', 'Type: “hello”', 'Keys: ctrl+s' – the words shown for an action."""
    kind = action.get("type", "")
    verb = VERBS.get(kind, kind.replace("_", " ").capitalize() or "Step")
    if kind in ("type_text", "web_type"):
        text = str(action.get("text", ""))
        what = "“" + (text[:40] + "…" if len(text) > 40 else text) + "”"
    elif kind in ("press_key", "web_key"):
        what = str(action.get("key", ""))
    elif kind == "hotkey":
        what = "+".join(action.get("keys") or [])
    elif kind == "wait":
        what = f"{action.get('seconds', 0):g} s"
    elif kind == "window_state":
        what = f"{action.get('state', '')} {action.get('target', '')}".strip()
    else:
        what = str(action.get("target") or action.get("name") or action.get("url") or action.get("path") or "")
    what = " ".join(what.split())
    return f"{verb}: {what[:70]}" if what else verb


def target_box(action: dict) -> tuple[int, int, int, int] | None:
    """(left, top, width, height) of what the action touches, in screen pixels, or None when it touches no one place."""
    if action.get("type") not in ("click", "double_click", "right_click", "scroll"):
        return None
    box = action.get("box")
    if isinstance(box, (list, tuple)) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box) and box[2] > 0 and box[3] > 0:
        return tuple(int(v) for v in box)
    x, y = action.get("x"), action.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return (int(x) - 18, int(y) - 18, 36, 36)
    return None


def overlaps(a: tuple, b: tuple, margin: int = 0) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax - margin < bx + bw and bx < ax + aw + margin and ay - margin < by + bh and by < ay + ah + margin


def bar_spot(work: tuple[int, int, int, int], size: tuple[int, int], avoid: tuple | None = None, gap: int = 14) -> tuple[int, int]:
    """Where the status bar goes: bottom centre of the work area, else top centre, else the bottom-right corner,
    whichever does not cover what Autopilot is about to touch. work = (left, top, right, bottom)."""
    left, top, right, bottom = work
    w, h = size
    cx = left + (right - left - w) // 2
    spots = [(cx, bottom - h - gap), (cx, top + gap), (right - w - gap, bottom - h - gap), (left + gap, top + gap)]
    for x, y in spots:
        if avoid is None or not overlaps((x, y, w, h), avoid, 16):
            return x, y
    return spots[0]


def label_spot(box: tuple, screen_h: int, label_h: int = 26) -> tuple[int, int, str]:
    """Where the label goes: just above the outline, or below it when the outline is at the top of the screen."""
    x, y, w, h = box
    if y - label_h - 10 >= 0:
        return x - 6, y - 10, "sw"
    return x - 6, min(screen_h - label_h, y + h + 10), "nw"


# ---------------- the windows (Windows only) ----------------
class Overlay:
    def __init__(self):
        self.q: queue.Queue = queue.Queue()
        self.thread = None
        self.ready = threading.Event()
        self.ok = False
        self.error = ""
        self.capture_safe = False          # True when Windows leaves both windows out of screenshots
        self.visible = False
        self.on_stop = None
        self.start_lock = threading.Lock()

    # ----- public, thread-safe -----
    def available(self) -> bool:
        with self.start_lock:
            if self.thread is None:
                if os.name != "nt":
                    self.error = "Windows only"
                    self.ready.set()
                    self.thread = False
                else:
                    self.thread = threading.Thread(target=self._run, daemon=True, name="jarvis-overlay")
                    self.thread.start()
        self.ready.wait(5)
        return self.ok

    def begin(self, text: str, on_stop=None) -> None:
        if self.available():
            self.on_stop = on_stop
            self.visible = True
            self.q.put(("begin", text))

    def status(self, text: str) -> None:
        if self.visible:
            self.q.put(("status", text))

    def target(self, action: dict) -> None:
        if self.visible:
            self.q.put(("target", target_box(action), describe(action)))

    def clear(self) -> None:
        if self.visible:
            self.q.put(("clear",))

    def end(self) -> None:
        if self.visible:
            self.visible = False
            self.on_stop = None
            self.q.put(("end",))

    def _wait(self, *cmd) -> None:
        done = threading.Event()
        self.q.put((*cmd, done))
        done.wait(1.0)

    @contextlib.contextmanager
    def out_of_picture(self):
        """Hide the overlay while a screenshot is taken, unless Windows already leaves it out of screenshots."""
        hide = self.visible and self.ok and not self.capture_safe
        if hide:
            self._wait("hide")
        try:
            yield
        finally:
            if hide:
                self._wait("show")

    # ----- the overlay thread -----
    def _run(self) -> None:
        try:
            import tkinter as tk
        except Exception:
            self.error = "tkinter is missing (reinstall Python with “tcl/tk and IDLE” ticked)"
            self.ready.set()
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)        # real pixels, the same ones pyautogui uses
            except Exception:
                try:
                    user32.SetProcessDPIAware()
                except Exception:
                    pass
            root = tk.Tk()
            root.withdraw()
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()

            layer = tk.Toplevel(root)
            layer.title("Jarvis overlay")
            layer.overrideredirect(True)
            layer.configure(bg=KEY)
            layer.attributes("-topmost", True)
            layer.attributes("-transparentcolor", KEY)
            layer.geometry(f"{sw}x{sh}+0+0")
            canvas = tk.Canvas(layer, bg=KEY, highlightthickness=0, width=sw, height=sh)
            canvas.pack(fill="both", expand=True)

            bar = tk.Toplevel(root)
            bar.title("Jarvis Autopilot")
            bar.overrideredirect(True)
            bar.attributes("-topmost", True)
            bar.configure(bg=ACCENT)
            inner = tk.Frame(bar, bg=BAR_BG)
            inner.pack(padx=1, pady=1)
            text = tk.Label(inner, text="", fg="#e8f7fb", bg=BAR_BG, font=("Segoe UI", 10), padx=12, pady=6, anchor="w", width=56)
            text.pack(side="left")
            stop = tk.Button(inner, text="■ Stop", fg="white", bg="#b3261e", activebackground="#d93025", activeforeground="white",
                             relief="flat", font=("Segoe UI", 10, "bold"), padx=10, cursor="hand2", command=lambda: self._stop(text))
            stop.pack(side="right", padx=6, pady=4)
            hint = tk.Label(inner, text="Ctrl+Shift+F10", fg="#7f97a0", bg=BAR_BG, font=("Segoe UI", 8))
            hint.pack(side="right")
        except Exception as exc:
            self.error = f"the overlay could not be made: {exc}"
            self.ready.set()
            return

        def work_area():
            rect = (ctypes.c_long * 4)()
            if user32.SystemParametersInfoW(0x30, 0, rect, 0):     # SPI_GETWORKAREA: the screen without the taskbar
                return tuple(rect)
            return (0, 0, sw, sh)

        def styled(win, click_through: bool) -> bool:
            """Tool window that never takes focus, above everything, left out of screenshots; optionally click-through."""
            win.update_idletasks()
            hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
            ex = user32.GetWindowLongW(hwnd, -20)                      # GWL_EXSTYLE
            ex |= 0x80 | 0x8 | 0x08000000                              # TOOLWINDOW | TOPMOST | NOACTIVATE
            if click_through:
                ex |= 0x80000 | 0x20                                   # LAYERED | TRANSPARENT
            user32.SetWindowLongW(hwnd, -20, ex)
            try:
                return bool(user32.SetWindowDisplayAffinity(hwnd, 0x11))   # WDA_EXCLUDEFROMCAPTURE
            except Exception:
                return False

        state = {"box": None, "shown": False}

        def place_bar(avoid=None):
            bar.update_idletasks()
            x, y = bar_spot(work_area(), (bar.winfo_reqwidth(), bar.winfo_reqheight()), avoid)
            bar.geometry(f"+{x}+{y}")

        def show():
            layer.deiconify()
            bar.deiconify()
            safe = styled(layer, True) & styled(bar, False)
            self.capture_safe = bool(safe)
            place_bar(state["box"])
            state["shown"] = True

        def draw(box, label):
            canvas.delete("all")
            state["box"] = box
            if box is None:
                return
            x, y, w, h = box
            if w <= 36 and h <= 36:                                     # a point, not a control: a ring and a cross
                cx, cy = x + w // 2, y + h // 2
                canvas.create_oval(cx - 18, cy - 18, cx + 18, cy + 18, outline=ACCENT, width=3)
                canvas.create_line(cx - 7, cy, cx + 7, cy, fill=ACCENT, width=2)
                canvas.create_line(cx, cy - 7, cx, cy + 7, fill=ACCENT, width=2)
            else:
                canvas.create_rectangle(x - 5, y - 5, x + w + 5, y + h + 5, outline=ACCENT, width=3)
            lx, ly, anchor = label_spot(box, sh)
            item = canvas.create_text(lx + 8, ly - 4 if anchor == "sw" else ly + 4, text=label, anchor=anchor, fill="white", font=("Segoe UI", 10, "bold"))
            bx = canvas.bbox(item)
            if bx:
                bg = canvas.create_rectangle(bx[0] - 7, bx[1] - 3, bx[2] + 7, bx[3] + 3, fill=LABEL_BG, outline=ACCENT)
                canvas.tag_lower(bg, item)
            place_bar(box)

        def handle(cmd):
            kind = cmd[0]
            if kind == "begin":
                text.config(text=cmd[1][:90])
                stop.config(state="normal")
                draw(None, "")
                show()
            elif kind == "status":
                text.config(text=cmd[1][:90])
            elif kind == "target":
                draw(cmd[1], cmd[2])
            elif kind == "clear":
                draw(None, "")
            elif kind == "end":
                draw(None, "")
                layer.withdraw()
                bar.withdraw()
                state["shown"] = False
            elif kind == "hide":
                layer.withdraw()
                bar.withdraw()
                root.update()
                time.sleep(0.03)                                         # let Windows repaint without them
            elif kind == "show":
                if self.visible:
                    show()
            if len(cmd) > 1 and isinstance(cmd[-1], threading.Event):
                cmd[-1].set()

        def poll():
            while True:
                try:
                    cmd = self.q.get_nowait()
                except queue.Empty:
                    break
                try:
                    handle(cmd)
                except Exception as exc:
                    print(f"[jarvis] overlay: {exc}")
                    if isinstance(cmd[-1], threading.Event):
                        cmd[-1].set()
            root.after(25, poll)

        layer.withdraw()
        bar.withdraw()
        self.ok = True
        self.ready.set()
        root.after(25, poll)
        root.mainloop()

    def _stop(self, label) -> None:
        label.config(text="Stopping: no further actions will run.")
        callback = self.on_stop
        if callback:
            try:
                callback()
            except Exception:
                pass


OVERLAY = Overlay()
