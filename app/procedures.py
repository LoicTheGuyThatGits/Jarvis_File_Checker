"""What Autopilot learned: the steps of tasks it finished, so a similar task later starts with a known way.

Kept in data/autopilot-learned.json: the task in your words, the steps that worked, when, and how often it was reused.
Only finished tasks are kept; you can delete any of them in Settings > Computer control.

    remember(path, task, steps)   after a finished task
    hint(path, task)              the text added to the model's instructions for a similar task, or ""
"""
from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

import recall

MAX_ITEMS = 60
MAX_STEPS = 30
SIMILAR = 0.4


def load(path: Path) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [d for d in data if isinstance(d, dict) and isinstance(d.get("task"), str) and isinstance(d.get("steps"), list)] if isinstance(data, list) else []


def save(path: Path, items: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[-MAX_ITEMS:], indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def remember(path: Path, task: str, steps: list[str]) -> dict | None:
    steps = [s[:200] for s in steps if s][:MAX_STEPS]
    task = " ".join((task or "").split())[:300]
    if not steps or not task:
        return None
    items = load(path)
    same = next((i for i in items if recall.similar(i["task"], task) >= 0.8), None)
    if same:
        if len(steps) <= len(same["steps"]) or same.get("uses", 0) == 0:      # a shorter way, or the first one was never reused: keep the new one
            same.update(task=task, steps=steps, at=time.time())
        same["uses"] = same.get("uses", 0)
        save(path, items)
        return same
    item = {"id": secrets.token_hex(4), "task": task, "steps": steps, "at": time.time(), "uses": 0}
    items.append(item)
    save(path, items)
    return item


def best(path: Path, task: str) -> dict | None:
    scored = [(recall.similar(i["task"], task), i) for i in load(path)]
    scored = [x for x in scored if x[0] >= SIMILAR]
    return max(scored, key=lambda x: (x[0], x[1].get("at", 0)))[1] if scored else None


def hint(path: Path, task: str) -> str:
    item = best(path, task)
    if not item:
        return ""
    items = load(path)
    for i in items:
        if i["id"] == item["id"]:
            i["uses"] = i.get("uses", 0) + 1
    save(path, items)
    return (f"A similar task was finished before (“{item['task']}”) with these steps. Use them as a guide, but follow what the screen shows now "
            "(windows, positions and numbers will differ):\n" + "\n".join(f"{n + 1}. {s}" for n, s in enumerate(item["steps"])))


def delete(path: Path, item_id: str) -> bool:
    items = load(path)
    keep = [i for i in items if i["id"] != item_id]
    save(path, keep)
    return len(keep) != len(items)
