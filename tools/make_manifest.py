"""Writes manifest.json: the list of every file Jarvis needs, with a fingerprint of each.
Run it after changing any file:  python tools/make_manifest.py        (a GitHub Action does it for you on every push)
                                  python tools/make_manifest.py --check   (exit 1 if manifest.json is out of date)
It also refuses to continue when a listed file looks like it contains a secret (a Telegram token, an API key, an app password)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import filecheck  # noqa: E402

TOP_DIRS = ("app", "web", "tools")
ROOT_FILE = re.compile(r"(?:.+\.(?:bat|py|txt|md)|LICENSE|requirements\.txt)$")
SKIP_PARTS = {"__pycache__", ".venv", "data", "model", "android", "node_modules", ".git"}
SKIP_NAME = re.compile(r".*(?:\.pyc|\.part|\.tmp|\.apk|\.zip)$|.*\.bak.*", re.I)
SECRETS = [(re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}"), "a Telegram bot token"), (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "an API key"),
           (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}|\bghp_[A-Za-z0-9]{30,}"), "a GitHub token"), (re.compile(r"\"(?:refresh_token|access_token)\"\s*:\s*\"[^\"]{20,}\""), "a login token")]


def wanted(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in SKIP_PARTS for part in rel.parts) or SKIP_NAME.fullmatch(rel.name) or rel.name == "manifest.json":
        return False
    if len(rel.parts) == 1:
        return bool(ROOT_FILE.fullmatch(rel.name))
    return rel.parts[0] in TOP_DIRS


def build() -> dict:
    files = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file() or not wanted(p):
            continue
        rel = p.relative_to(ROOT).as_posix()
        data = p.read_bytes()
        if filecheck.PurePosixPath(rel).suffix.lower() in filecheck.TEXT_EXT:
            text = data.decode("utf-8", "replace")
            for pattern, what in SECRETS:
                if pattern.search(text):
                    raise SystemExit(f"STOP: {rel} seems to contain {what}. Remove it before publishing.")
        filecheck.safe_rel(rel)
        files.append({"path": rel, "sha256": filecheck.fingerprint(data, rel), "size": len(filecheck.normalize(data, rel))})
    return {"format": 1, "repo": filecheck.REPO, "files": files}


def main() -> int:
    manifest = build()
    path = ROOT / "manifest.json"
    text = json.dumps(manifest, indent=1) + "\n"
    if "--check" in sys.argv:
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            current = {}
        old = {f.get("path"): f for f in current.get("files") or []}
        new = {f["path"]: f for f in manifest["files"]}
        if old != new:                                 # the order does not count (Windows sorts paths without case)
            for rel in sorted(set(old) | set(new)):
                if old.get(rel) != new.get(rel):
                    print("  differs:", rel, "(not in manifest.json)" if rel not in old else "(no such file)" if rel not in new else "")
            print("manifest.json is out of date. Run: python tools/make_manifest.py")
            return 1
        print("manifest.json is up to date (%d files)." % len(manifest["files"]))
        return 0
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    try:
        if json.loads(old).get("files") == manifest["files"]:
            print("manifest.json already up to date (%d files)." % len(manifest["files"]))
            return 0
    except ValueError:
        pass
    path.write_text(text, encoding="utf-8", newline="\n")
    print("manifest.json written: %d files." % len(manifest["files"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
