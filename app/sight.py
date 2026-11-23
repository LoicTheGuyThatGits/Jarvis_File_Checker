"""How Autopilot sees the screen.

    grab(all_screens)                 the screen (or every screen) as a picture, and where its top-left corner is
    shrink(image)                     the size sent to the AI model
    zoom_region(x, y, area, factor)   the part of the screen to look at closer
    draw_marks(image, elements, ...)  numbered boxes on the controls Windows reports, so the model can say “click 14”
    fingerprint / changed             whether a step changed anything on the screen

Positions: Windows' own coordinates (the main screen starts at 0,0; a screen to its left has negative x). A capture has an
origin (where its top-left corner is) and a size in real pixels; the picture sent to the model is a smaller copy.
"""
from __future__ import annotations

import os
from PIL import Image, ImageChops, ImageDraw, ImageFont

SHOWN = (1440, 900)
MARK_LIMIT = 120
COLOURS = ("#ff2bd6", "#00c2ff", "#ffb000", "#22dd66")


def virtual_screen() -> tuple[int, int, int, int] | None:
    """(left, top, width, height) of all screens together, on Windows."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        m = ctypes.windll.user32.GetSystemMetrics
        return m(76), m(77), m(78), m(79)
    except Exception:
        return None


def grab(all_screens: bool = False) -> tuple[Image.Image, tuple[int, int]]:
    if os.name == "nt":
        try:
            from PIL import ImageGrab
            image = ImageGrab.grab(all_screens=all_screens)
            vs = virtual_screen() if all_screens else None
            return image, ((vs[0], vs[1]) if vs else (0, 0))
        except Exception:
            pass
    import pyautogui
    return pyautogui.screenshot(), (0, 0)


def shrink(image: Image.Image, size: tuple[int, int] = SHOWN) -> Image.Image:
    small = image.copy()
    small.thumbnail(size, reducing_gap=2.0)
    return small


def zoom_region(x: int, y: int, area: tuple[int, int, int, int], factor: float = 2.0) -> tuple[int, int, int, int]:
    """(left, top, width, height): a part of `area` 1/factor its size, centred on x,y as far as it fits."""
    ax, ay, aw, ah = area
    w, h = max(80, round(aw / factor)), max(60, round(ah / factor))
    left = min(max(ax, x - w // 2), ax + aw - w)
    top = min(max(ay, y - h // 2), ay + ah - h)
    return left, top, w, h


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                                     # an older Pillow: the small built-in font
        return ImageFont.load_default()


def draw_marks(image: Image.Image, elements: list[dict], origin: tuple[int, int], real_size: tuple[int, int], limit: int = MARK_LIMIT) -> Image.Image:
    """A copy of the shown picture with a numbered box on each control. Element positions are real screen pixels (centre, w, h)."""
    out = image.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    sx, sy = out.width / max(1, real_size[0]), out.height / max(1, real_size[1])
    font = _font(max(10, round(out.width / 110)))
    placed = 0
    for e in elements:
        if placed >= limit:
            break
        left = (e["x"] - e["w"] / 2 - origin[0]) * sx
        top = (e["y"] - e["h"] / 2 - origin[1]) * sy
        right, bottom = left + e["w"] * sx, top + e["h"] * sy
        if right < 0 or bottom < 0 or left > out.width or top > out.height or e["w"] * sx < 3 or e["h"] * sy < 3:
            continue
        colour = COLOURS[e["n"] % len(COLOURS)]
        draw.rectangle([left, top, right, bottom], outline=colour, width=2)
        label = str(e["n"])
        tw, th = draw.textbbox((0, 0), label, font=font)[2:]
        lx, ly = max(0, left), max(0, top - th - 2) if top - th - 2 >= 0 else max(0, top)
        draw.rectangle([lx, ly, lx + tw + 4, ly + th + 2], fill=colour)
        draw.text((lx + 2, ly), label, fill="black", font=font)
        placed += 1
    return out


def fingerprint(image: Image.Image) -> Image.Image:
    return image.convert("L").resize((320, 200))


def changed(before: Image.Image | None, after: Image.Image | None) -> bool | None:
    """Did anything visible change? None when there is nothing to compare."""
    if before is None or after is None or before.size != after.size:
        return None
    diff = ImageChops.difference(before, after).point(lambda v: 255 if v > 24 else 0)
    return diff.histogram()[255] >= 3
