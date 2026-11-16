"""Screen map: what is on the screen as a list, not only as a picture.

Windows keeps a description of every window for screen readers (UI Automation): each button, link, menu item, tab and text
box, with its name and where it is. Reading that gives Jarvis three things a screenshot alone does not:
  - the AI model can be told exactly which controls exist and where ("12. Button “Save” at 640,412"), so it can pick a
    control by number instead of guessing pixel positions;
  - a model that cannot see pictures at all can still say what is on the screen;
  - "click on Save" works without any model: Jarvis finds the control called Save and clicks it.

    capture(run, skip)           the raw map of the front window (run = a function that runs PowerShell and returns its text)
    normalise(raw, width, height)  cleaned, numbered elements with their centre points
    describe(map, scale)         the text given to the model
    find(map, words, kinds)      the element a phrase like "the save button" means
    click_request(text)          ("click", "save") from "click on the Save button", else None
"""
from __future__ import annotations

import base64
import json
import re
import subprocess

CLICKABLE = ("Button", "Hyperlink", "MenuItem", "TabItem", "CheckBox", "RadioButton", "ComboBox", "ListItem", "TreeItem", "SplitButton", "DataItem", "Edit")
READABLE = ("Text", "Document", "Image")
KIND_WORDS = {"Button": "button", "SplitButton": "button", "Hyperlink": "link", "MenuItem": "menu item", "TabItem": "tab", "CheckBox": "checkbox", "RadioButton": "option",
              "ComboBox": "drop-down", "ListItem": "list item", "TreeItem": "tree item", "DataItem": "row", "Edit": "text box", "Text": "text", "Document": "document", "Image": "image"}
MAX_ELEMENTS = 250

# Runs inside PowerShell. $skip is a regular expression for window titles to pass over (the Jarvis window itself).
SCRIPT = r'''
$ErrorActionPreference = 'Stop'
try { Add-Type -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();' -Name Dpi -Namespace JarvisScreen; [JarvisScreen.Dpi]::SetProcessDPIAware() | Out-Null } catch {}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$AE = [System.Windows.Automation.AutomationElement]
$skip = '__SKIP__'
$win = $null
$visible = New-Object System.Windows.Automation.PropertyCondition($AE::IsOffscreenProperty, $false)
foreach ($w in $AE::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $visible)) {
  try {
    $c = $w.Current
    $r = $c.BoundingRectangle
    if ($r.IsEmpty -or $r.Width -lt 120 -or $r.Height -lt 80) { continue }
    if (-not $c.Name -or $c.Name -eq 'Program Manager') { continue }
    if ($c.ClassName -match '^(Shell_TrayWnd|Shell_SecondaryTrayWnd|Progman|WorkerW|NotifyIconOverflowWindow)$') { continue }
    if ($skip -and $c.Name -match $skip) { continue }
    $win = $w; break
  } catch {}
}
if ($win -eq $null) { $win = $AE::FocusedElement }
$types = @('Button','Hyperlink','MenuItem','TabItem','Edit','CheckBox','RadioButton','ComboBox','ListItem','TreeItem','Text','SplitButton','Document','DataItem','Image')
$cond = New-Object System.Windows.Automation.AndCondition($visible, (New-Object System.Windows.Automation.PropertyCondition($AE::IsControlElementProperty, $true)))
$out = New-Object System.Collections.ArrayList
foreach ($e in $win.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)) {
  if ($out.Count -ge __MAX__) { break }
  try {
    $c = $e.Current
    $t = $c.ControlType.ProgrammaticName -replace '^ControlType\.', ''
    if ($types -notcontains $t) { continue }
    $r = $c.BoundingRectangle
    if ($r.IsEmpty -or $r.Width -lt 4 -or $r.Height -lt 4) { continue }
    $n = [string]$c.Name
    if (-not $n -and $t -ne 'Edit') { continue }
    if ($n.Length -gt 90) { $n = $n.Substring(0, 90) }
    [void]$out.Add(@{ n = $n; t = $t; x = [int]$r.X; y = [int]$r.Y; w = [int]$r.Width; h = [int]$r.Height; on = [bool]$c.IsEnabled })
  } catch {}
}
$wr = $win.Current.BoundingRectangle
$titles = @(Get-Process | Where-Object { $_.MainWindowTitle } | ForEach-Object { $_.MainWindowTitle })
@{ title = [string]$win.Current.Name; x = [int]$wr.X; y = [int]$wr.Y; w = [int]$wr.Width; h = [int]$wr.Height; elements = $out; windows = $titles } | ConvertTo-Json -Depth 4 -Compress
'''


def default_run(script: str, timeout: float = 12) -> str:
    """Runs a PowerShell script given as text (sent base64-encoded, so quotes and accents survive) and returns what it printed."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded], capture_output=True, timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.decode("utf-8", errors="replace")


def capture(run=default_run, skip: str = "Jarvis", width: int = 0, height: int = 0) -> dict | None:
    """The map of the front window, or None when it cannot be read (not Windows, the scan took too long, nothing came back)."""
    script = SCRIPT.replace("__SKIP__", re.sub(r"[^\w .|()-]", "", skip)).replace("__MAX__", str(MAX_ELEMENTS))
    text = run(script)
    start = text.find("{")
    if start < 0:
        return None
    try:
        raw = json.loads(text[start:])
    except ValueError:
        return None
    return normalise(raw, width, height) if isinstance(raw, dict) else None


def normalise(raw: dict, width: int = 0, height: int = 0) -> dict:
    """Numbered elements with centre points, nothing off the screen, no doubles; things you can click come first."""
    items = raw.get("elements") or []
    if isinstance(items, dict):
        items = [items]
    seen, clickable, readable = set(), [], []
    for item in items:
        try:
            kind, name = str(item["t"]), re.sub(r"\s+", " ", str(item.get("n") or "")).strip()
            x, y, w, h = int(item["x"]), int(item["y"]), int(item["w"]), int(item["h"])
        except (KeyError, TypeError, ValueError):
            continue
        cx, cy = x + w // 2, y + h // 2
        if kind not in CLICKABLE + READABLE or w < 4 or h < 4 or cx < 0 or cy < 0 or (width and cx >= width) or (height and cy >= height):
            continue
        key = (kind in CLICKABLE, name.lower(), cx // 8, cy // 8)
        if key in seen:
            continue
        seen.add(key)
        entry = {"name": name, "kind": kind, "x": cx, "y": cy, "w": w, "h": h, "enabled": item.get("on") is not False}
        (clickable if kind in CLICKABLE else readable).append(entry)
    def inside(text: dict) -> bool:                        # a button's own label is not listed twice
        return any(c["name"].lower() == text["name"].lower() and abs(text["x"] - c["x"]) <= c["w"] // 2 + 4 and abs(text["y"] - c["y"]) <= c["h"] // 2 + 4 for c in clickable)
    readable = [e for e in readable if not inside(e)]
    elements = clickable + readable
    for n, e in enumerate(elements, 1):
        e["n"] = n
    windows = raw.get("windows") or []
    if isinstance(windows, str):
        windows = [windows]
    return {"title": str(raw.get("title") or "")[:160], "elements": elements, "windows": [str(w)[:100] for w in windows][:20]}


def describe(screen_map: dict | None, scale_x: float = 1.0, scale_y: float = 1.0, limit: int = 110) -> str:
    """The map as text for the model. Positions are given in the screenshot's own pixels (scale = shown / real)."""
    if not screen_map:
        return ""
    lines = [f"Front window: “{screen_map['title'] or 'unknown'}”."]
    others = [w for w in screen_map.get("windows", []) if w and w != screen_map["title"]]
    if others:
        lines.append("Other open windows: " + "; ".join(f"“{w}”" for w in others[:10]) + ".")
    elements = screen_map.get("elements", [])
    click = [e for e in elements if e["kind"] in CLICKABLE][:limit]
    text = [e for e in elements if e["kind"] in READABLE][: max(0, limit - len(click))]
    if click:
        lines.append("Controls in the front window (number. kind “name” at x,y in the screenshot):")
        lines += [f"{e['n']}. {KIND_WORDS[e['kind']]} “{e['name'] or '(no name)'}” at {round(e['x'] * scale_x)},{round(e['y'] * scale_y)}" + ("" if e["enabled"] else " (greyed out)") for e in click]
    if text:
        lines.append("Text shown in the front window:")
        lines += [f"- {e['name']}" for e in text if e["name"]]
    if not click and not text:
        lines.append("The window gave no list of its controls (some apps and games do not).")
    return "\n".join(lines)


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", (text or "").lower())


def find(screen_map: dict | None, phrase: str) -> list[dict]:
    """The clickable elements a phrase means, best first. More than one answer means the phrase is ambiguous."""
    if not screen_map:
        return []
    p = re.sub(r"\s+", " ", phrase or "").strip().lower()
    kind_hint = None
    m = re.search(r"\s+(button|link|tab|menu(?:\s+item)?|checkbox|check\s+box|option|box|field|icon|item)$", p)
    if m:
        kind_hint, p = m.group(1), p[:m.start()].strip()
    p = re.sub(r"^(?:the|a|an|that|this)\s+", "", p).strip(" \"'“”")
    if not p:
        return []
    want = _words(p)
    scored = []
    for e in screen_map.get("elements", []):
        if e["kind"] not in CLICKABLE or not e["enabled"] or not e["name"]:
            continue
        name = e["name"].lower()
        have = _words(name)
        if name == p:
            score = 100
        elif re.sub(r"[^\w ]", "", name).strip() == p:
            score = 95
        elif have[:len(want)] == want:
            score = 80 - min(15, len(have) - len(want))
        elif want and all(w in have for w in want):
            score = 65 - min(15, len(have) - len(want))
        elif len(p) >= 4 and p in name:
            score = 50
        else:
            continue
        hint_kinds = {"button": ("Button", "SplitButton"), "link": ("Hyperlink",), "tab": ("TabItem",), "menu": ("MenuItem",), "menu item": ("MenuItem",), "checkbox": ("CheckBox",),
                      "check box": ("CheckBox",), "option": ("RadioButton", "ListItem", "MenuItem"), "box": ("Edit", "ComboBox", "CheckBox"), "field": ("Edit",), "item": ("ListItem", "MenuItem", "TreeItem")}
        if kind_hint and e["kind"] in hint_kinds.get(re.sub(r"\s+", " ", kind_hint), ()):
            score += 8
        scored.append((score, e))
    if not scored:
        return []
    top = max(s for s, _ in scored)
    return [e for s, e in sorted(scored, key=lambda t: (-t[0], t[1]["n"])) if s >= top - 3]


CLEAN_START = r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?"
KEY_WORDS = r"(?:enter|return|tab|escape|esc|space(?:bar)?|backspace|delete|del|home|end|up|down|left|right|page\s*up|page\s*down|f\d{1,2}|ctrl|control|alt|shift|win(?:dows)?(?:\s+key)?|play|pause|mute|any\s+key|a\s+key|the\s+key)"


def click_request(text: str) -> tuple[str, str] | None:
    """('click' | 'double_click' | 'right_click', 'save button') when the message asks to click something on the screen by name."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(CLEAN_START, "", t, flags=re.I)
    t = re.sub(r"\s*(?:please|for me|now)?\s*[.!?]*$", "", t, flags=re.I).strip()
    if not t or len(t) > 120:
        return None
    m = re.fullmatch(r"(double[- ]?click|right[- ]?click|click|tap|hit|press|push|select|choose)\s+(?:on\s+|onto\s+)?(.+)", t, re.I)
    if not m:
        return None
    verb, target = m.group(1).lower(), m.group(2).strip()
    if re.fullmatch(rf"(?:the\s+)?{KEY_WORDS}(?:\s*(?:\+|and|then)\s*.+)?(?:\s+key)?", target, re.I) or re.search(r"\+", target):
        return None                                           # "press enter", "press ctrl+s": keys, handled elsewhere
    if verb in ("press", "push", "hit", "select", "choose", "tap") and not re.search(r"\b(?:button|link|tab|menu|checkbox|check\s+box|option|icon|item)\b", target, re.I):
        return None                                           # "press on", "select all the text" are too vague without saying what it is
    if re.search(r"\b(?:here|there|this|that|it|anywhere|somewhere|screen|mouse)\b$", target, re.I) or len(_words(target)) > 8:
        return None
    kind = "double_click" if verb.startswith("double") else "right_click" if verb.startswith("right") else "click"
    return kind, target
