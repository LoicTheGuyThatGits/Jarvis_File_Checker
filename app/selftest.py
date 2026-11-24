"""Self-check: tries each part of Jarvis that depends on this PC and says what works.

    run(checks, timeout)   checks = [(name, function)]; each function returns (status, detail) with status "ok" | "warn" | "fail" | "skip",
                           or (status, detail, fix) where fix = {"label", "do"}: a button the page offers to put it right
    report(results, info)  the text to read or send on

A check that raises fails with the error; a check that takes too long fails with "took too long". Nothing is changed
on the PC: the checks only read, measure and build things in memory.
"""
from __future__ import annotations

import threading
import time

MARK = {"ok": "✓", "warn": "⚠", "fail": "✗", "skip": "–"}


def run_one(fn, timeout: float) -> tuple[str, str, float, dict | None]:
    box: dict = {}

    def work():
        try:
            box["result"] = fn()
        except Exception as exc:
            box["error"] = f"{type(exc).__name__}: {exc}"
    started = time.monotonic()
    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout)
    took = time.monotonic() - started
    if t.is_alive():
        return "fail", f"took too long (over {timeout:.0f} s)", took, None
    if "error" in box:
        return "fail", box["error"][:300], took, None
    result = tuple(box.get("result") or ("fail", "no answer"))
    status, detail = result[0], result[1]
    fix = result[2] if len(result) > 2 and isinstance(result[2], dict) and result[2].get("do") else None
    return (status if status in MARK else "fail"), str(detail)[:400], took, fix


def run(checks: list, timeout: float = 45.0, progress=None) -> list[dict]:
    results = []
    for n, (name, fn) in enumerate(checks, 1):
        status, detail, took, fix = run_one(fn, timeout)
        results.append({"name": name, "status": status, "detail": detail, "seconds": round(took, 1), **({"fix": fix} if fix else {})})
        if progress:
            progress(n, len(checks), name)
    return results


def report(results: list[dict], info: dict) -> str:
    counts = {k: sum(1 for r in results if r["status"] == k) for k in MARK}
    head = [f"Jarvis self-check, {info.get('when', '')}",
            f"Folder: {info.get('folder', '?')} · Windows: {info.get('windows', '?')} · Python {info.get('python', '?')}",
            f"{counts['ok']} working, {counts['warn']} with a warning, {counts['fail']} not working, {counts['skip']} skipped.", ""]
    lines = [f"{MARK[r['status']]} {r['name']}: {r['detail']}" + (f" ({r['seconds']} s)" if r["seconds"] >= 2 else "") + (f" → {r['fix']['label']}" if r.get("fix") else "") for r in results]
    return "\n".join(head + lines)
