"""Jarvis file checker: finds the files Jarvis needs that are missing (or different) and restores them from the GitHub repository.

    python filecheck.py                 check and report
    python filecheck.py --repair        download the missing files (asks first)
    python filecheck.py --repair --all  also replace files that differ from the repository (the old copy is kept in data/file-backups)
    python filecheck.py --update        show what changed in the repository since your last update and install it (asks first)
    python filecheck.py --update --all  also replace files you changed yourself (the old copy is kept in data/file-backups)
    python filecheck.py --ref v1.2      use a tag or commit instead of the main branch
    python filecheck.py --offline       compare with the manifest.json in this folder only

Uses only Python's standard library, so it also works when the rest of Jarvis is broken or not installed yet.
The list of files comes from manifest.json in the repository (made by tools/make_manifest.py). Every download is checked against the
SHA-256 in that list before it is written, and Jarvis' own data (data/, .venv, tokens) is never touched.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

REPO = os.environ.get("JARVIS_REPO", "LoicTheGuyThatGits/Jarvis_File_Checker")
REF = os.environ.get("JARVIS_REPO_REF", "main")
RAW_BASE = "https://raw.githubusercontent.com"          # tests point this at a local server
MAX_FILE_BYTES, TIMEOUT = 8_000_000, 25
TEXT_EXT = {".py", ".js", ".html", ".css", ".md", ".txt", ".bat", ".json", ".yml", ".yaml", ".cfg", ".ini", ".svg", ".xml", ".gitignore", ".gitattributes"}
NEVER = ("data", ".venv", "model", ".git", "workspace", "piper")           # never listed, never written
ALLOWED_TOP = {"app", "web", "tools", ".github"}                            # folders a manifest may write into (plus plain files in the root)
PENDING: dict = {"at": 0.0, "paths": [], "all": False}
STATE_NAME = "filecheck-state.json"
CONFIRM_SECONDS = 180


class CheckError(Exception):
    pass


def normalize(data: bytes, rel: str) -> bytes:
    """Line endings do not count: a file saved with Windows endings has the same fingerprint as the one in the repository."""
    if PurePosixPath(rel).suffix.lower() in TEXT_EXT or PurePosixPath(rel).name in (".gitignore", ".gitattributes", "LICENSE"):
        return data.replace(b"\r\n", b"\n")
    return data


def fingerprint(data: bytes, rel: str) -> str:
    return hashlib.sha256(normalize(data, rel)).hexdigest()


def safe_rel(rel: str) -> str:
    """A manifest path that may be written: relative, forward slashes, no tricks, not Jarvis' own data."""
    if not isinstance(rel, str) or not rel or len(rel) > 200 or "\\" in rel or "\x00" in rel:
        raise CheckError("bad path in the manifest: " + repr(rel)[:80])
    p = PurePosixPath(rel)
    if p.is_absolute() or any(part in ("", ".", "..") or part.endswith((" ", ".")) or ":" in part for part in p.parts):
        raise CheckError("unsafe path in the manifest: " + rel)
    if p.parts[0].lower() in NEVER:
        raise CheckError("the manifest may not touch " + p.parts[0] + ": " + rel)
    if len(p.parts) > 1 and p.parts[0] not in ALLOWED_TOP:
        raise CheckError("the manifest may not write into the folder " + p.parts[0] + ": " + rel)
    return rel


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Jarvis-file-checker"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = r.read(MAX_FILE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise CheckError("not found in the repository (HTTP %d)" % exc.code if exc.code == 404 else "GitHub answered with an error (HTTP %d)" % exc.code)
    except Exception as exc:
        raise CheckError("could not reach GitHub: " + str(exc)[:100])
    if len(data) > MAX_FILE_BYTES:
        raise CheckError("file too big")
    return data


def raw_url(rel: str, ref: str, repo: str | None = None) -> str:
    return f"{RAW_BASE}/{repo or REPO}/{urllib.parse.quote(ref, safe='')}/{urllib.parse.quote(rel)}"



def parse_manifest(raw: bytes) -> dict:
    try:
        m = json.loads(raw.decode("utf-8"))
        files = m["files"]
        assert isinstance(files, list)
    except Exception:
        raise CheckError("the manifest is not readable")
    seen, out = set(), []
    for f in files:
        rel = safe_rel(f.get("path"))
        sha = f.get("sha256")
        if rel in seen or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise CheckError("the manifest has a bad entry: " + rel)
        seen.add(rel)
        out.append({"path": rel, "sha256": sha, "size": int(f.get("size") or 0)})
    return {"files": out, "generated": m.get("generated", ""), "ref": m.get("ref", "")}


def load_manifest(root: Path, ref: str, offline: bool = False) -> tuple[dict, str]:
    """(manifest, where it came from). The repository is the truth; the manifest.json in this folder is the fallback."""
    if not offline:
        try:
            return parse_manifest(http_get(raw_url("manifest.json", ref))), "the GitHub repository"
        except CheckError as exc:
            problem = str(exc)
        else:
            problem = ""
    else:
        problem = "offline mode"
    local = Path(root) / "manifest.json"
    if local.is_file():
        return parse_manifest(local.read_bytes()), f"the manifest.json in this folder ({problem})"
    raise CheckError(f"I could not get the list of files ({problem}) and there is no manifest.json in this folder.")


def check(root: Path, manifest: dict) -> dict:
    root = Path(root)
    missing, changed, ok = [], [], 0
    for f in manifest["files"]:
        p = root / f["path"]
        if not p.is_file():
            missing.append(f["path"])
            continue
        try:
            same = fingerprint(p.read_bytes(), f["path"]) == f["sha256"]
        except OSError:
            same = False
        if same:
            ok += 1
        else:
            changed.append(f["path"])
    return {"missing": missing, "changed": changed, "ok": ok, "total": len(manifest["files"])}


def load_state(root: Path) -> dict:
    try:
        st = json.loads((Path(root) / "data" / STATE_NAME).read_text(encoding="utf-8"))
        if isinstance(st, dict) and isinstance(st.get("applied"), dict):
            return st
    except (OSError, ValueError):
        pass
    return {"applied": {}}


def save_state(root: Path, state: dict) -> None:
    path = Path(root) / "data" / STATE_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def record_applied(root: Path, manifest: dict, paths: list[str]) -> None:
    """Remember which repository version each of these files now matches, so a later change in the repository can be told apart from your own edits."""
    by_path = {f["path"]: f["sha256"] for f in manifest["files"]}
    state = load_state(root)
    for rel in paths:
        if rel in by_path:
            state["applied"][rel] = by_path[rel]
    save_state(root, state)


def classify(root: Path, manifest: dict) -> dict:
    """Sorts every file: ok / missing / updates (the repository changed, your copy is untouched) / local (you changed it, the repository did not) /
    conflicts (both changed) / unknown (differs, and there is no record of where it came from)."""
    root = Path(root)
    state = load_state(root)
    applied = state["applied"]
    out = {"ok": 0, "missing": [], "updates": [], "local": [], "conflicts": [], "unknown": [], "total": len(manifest["files"])}
    matched = []
    for f in manifest["files"]:
        rel, remote = f["path"], f["sha256"]
        p = root / rel
        if not p.is_file():
            out["missing"].append(rel)
            continue
        try:
            here = fingerprint(p.read_bytes(), rel)
        except OSError:
            out["unknown"].append(rel)
            continue
        old = applied.get(rel)
        if here == remote:
            out["ok"] += 1
            if old != remote:
                matched.append(rel)
        elif old is None:
            out["unknown"].append(rel)
        elif here == old:
            out["updates"].append(rel)
        elif remote == old:
            out["local"].append(rel)
        else:
            out["conflicts"].append(rel)
    if matched:
        record_applied(root, manifest, matched)
    return out


def describe_update(plan: dict, source: str = "") -> str:
    lines = []
    def block(title: str, items: list[str]) -> None:
        if items:
            lines.append(f"{title} ({len(items)}):")
            lines.extend("  • " + p for p in items[:20])
            if len(items) > 20:
                lines.append(f"  • …and {len(items) - 20} more")
    block("New or missing files", plan["missing"])
    block("Updated in the repository", plan["updates"])
    block("Changed in both places, not touched unless you ask", plan["conflicts"])
    block("Different from the repository (no record of why)", plan["unknown"])
    if plan["local"]:
        lines.append(f"{len(plan['local'])} file{'s' if len(plan['local']) != 1 else ''} you changed yourself are left alone.")
    if not plan["missing"] and not plan["updates"]:
        lines.insert(0, f"Jarvis is up to date ({plan['ok']} of {plan['total']} files match the repository" + (f", {source}" if source else "") + ").")
    else:
        lines.insert(0, "An update is available" + (f" ({source})" if source else "") + ":")
    return "\n".join(lines)


def describe(result: dict, source: str = "") -> str:
    lines = [f"Checked {result['total']} files" + (f" against {source}" if source else "") + f": {result['ok']} fine."]
    if result["missing"]:
        lines.append(f"Missing ({len(result['missing'])}):")
        lines += ["  • " + p for p in result["missing"][:25]] + (["  • …and %d more" % (len(result["missing"]) - 25)] if len(result["missing"]) > 25 else [])
    if result["changed"]:
        lines.append(f"Different from the repository ({len(result['changed'])}); this is normal if you changed them yourself:")
        lines += ["  • " + p for p in result["changed"][:25]] + (["  • …and %d more" % (len(result["changed"]) - 25)] if len(result["changed"]) > 25 else [])
    if not result["missing"] and not result["changed"]:
        lines.append("Nothing is missing.")
    return "\n".join(lines)


def repair(root: Path, manifest: dict, paths: list[str], ref: str) -> dict:
    """Download the given files. Each one must match the manifest fingerprint, or it is not written."""
    root = Path(root).resolve()
    by_path = {f["path"]: f for f in manifest["files"]}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    done, failed, backed_up = [], [], []
    for rel in paths:
        entry = by_path.get(rel)
        try:
            if not entry:
                raise CheckError("not in the manifest")
            safe_rel(rel)
            data = http_get(raw_url(rel, ref))
            if fingerprint(data, rel) != entry["sha256"]:
                raise CheckError("the download does not match the manifest, so I did not write it")
            target = (root / rel).resolve()
            if root not in target.parents:
                raise CheckError("outside the Jarvis folder")
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_file():
                backup = root / "data" / "file-backups" / stamp / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(target.read_bytes())
                backed_up.append(rel)
            tmp = target.with_name(target.name + ".part")
            tmp.write_bytes(data)
            tmp.replace(target)
            done.append(rel)
        except (CheckError, OSError) as exc:
            failed.append((rel, str(exc)))
    if done:
        record_applied(root, manifest, done)
    return {"done": done, "failed": failed, "backed_up": backed_up, "backup_folder": f"data/file-backups/{stamp}" if backed_up else ""}


def describe_repair(res: dict) -> str:
    lines = []
    if res["done"]:
        lines.append(f"Restored {len(res['done'])} file{'s' if len(res['done']) != 1 else ''}.")
    if res["backed_up"]:
        lines.append(f"The {len(res['backed_up'])} old copies are kept in {res['backup_folder']}.")
    for rel, why in res["failed"]:
        lines.append(f"Could not restore {rel}: {why}.")
    if res["done"]:
        lines.append("Restart Jarvis so restored program files are used.")
    return "\n".join(lines) or "Nothing to restore."


def ref_for(root: Path) -> str:
    try:
        cfg = json.loads((Path(root) / "data" / "filecheck.json").read_text(encoding="utf-8"))
        if isinstance(cfg.get("ref"), str) and re.fullmatch(r"[A-Za-z0-9._/-]{1,80}", cfg["ref"]):
            return cfg["ref"]
    except (OSError, ValueError, AttributeError):
        pass
    return REF


# ---------------- chat ----------------
ASK = re.compile(r"(?:check|verify|scan|test|inspect)\s+(?:all\s+)?(?:my\s+|the\s+)?(?:jarvis\s+)?(?:files|install(?:ation)?|program files)(?:\s+(?:are|is)\s+(?:all\s+)?(?:there|here|ok|okay|present|complete))?"
                 r"|(?:is|are)\s+(?:there\s+)?(?:anything|any\s+files?|any\s+file|something|everything|all\s+(?:my\s+)?files?)\s+(?:missing|there|here|ok|okay|present|complete)(?:\s+(?:from|in)\s+(?:jarvis|my\s+jarvis(?:\s+folder)?|the\s+jarvis\s+folder))?"
                 r"|(?:check|look)\s+for\s+missing\s+(?:jarvis\s+)?files|(?:jarvis\s+)?file\s*check(?:er)?|(?:run\s+)?(?:the\s+)?file\s+check(?:er)?", re.I)
ASK_UPDATE = re.compile(r"(?:check\s+(?:for\s+)?(?:an?\s+)?(?:jarvis\s+)?updates?|(?:is|are)\s+there\s+(?:an?\s+|any\s+)?(?:new\s+|jarvis\s+)?updates?(?:\s+(?:for\s+jarvis|available))?|(?:any|new)\s+(?:jarvis\s+)?updates?(?:\s+(?:for\s+jarvis|available))?|update\s+(?:jarvis|yourself|myself|the\s+program|everything)|get\s+the\s+latest(?:\s+(?:version|files))?(?:\s+of\s+jarvis)?|(?:am\s+i|are\s+you)\s+up\s+to\s+date|upgrade\s+(?:jarvis|yourself))", re.I)
YES = re.compile(r"(?:yes|yeah|yep|ok|okay|sure|go ahead|confirm|do it)[,.! ]*(?:please[,.! ]*)?(?:restore(?:\s+(?:them|it|the files|the missing files))?|download(?:\s+them)?|repair(?:\s+them)?|update(?:\s+(?:them|now|jarvis|everything|yourself))?)|restore\s+them|update\s+(?:them|now)|repair\s+them|restore\s+(?:the\s+)?missing\s+files", re.I)


def command(text: str, root: Path, remote: bool = False, now: float | None = None, ref: str | None = None) -> str | None:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?", "", t, flags=re.I)
    t = re.sub(r"\s*(?:please|for me|now)?\s*[.!?]*$", "", t, flags=re.I).strip()
    if not t or len(t) > 120:
        return None
    now = time.time() if now is None else now
    ref = ref or ref_for(root)
    if PENDING["at"] and now - PENDING["at"] <= CONFIRM_SECONDS and YES.fullmatch(t):
        paths, PENDING["at"] = list(PENDING["paths"]), 0.0
        if remote:
            return "For safety I only restore files when you ask at the PC itself, sir."
        try:
            manifest, _ = load_manifest(root, ref)
            return describe_repair(repair(root, manifest, paths, ref))
        except CheckError as exc:
            return "I could not restore the files: " + str(exc)
    if ASK_UPDATE.fullmatch(t):
        PENDING["at"] = 0.0
        try:
            manifest, source = load_manifest(root, ref)
        except CheckError as exc:
            return str(exc)
        plan = classify(root, manifest)
        out = describe_update(plan, source)
        todo = plan["missing"] + plan["updates"]
        if todo:
            if remote:
                return out + "\nInstalling has to be asked at the PC itself, sir."
            PENDING.update(at=now, paths=todo, all=False)
            out += "\nSay “yes, update” within three minutes and I will download them (the old copies are kept in data/file-backups). Restart Jarvis afterwards."
        return out
    if ASK.fullmatch(t):
        PENDING["at"] = 0.0
        try:
            manifest, source = load_manifest(root, ref)
        except CheckError as exc:
            return str(exc)
        res = check(root, manifest)
        out = describe(res, source)
        if res["missing"]:
            if remote:
                return out + "\nRestoring has to be asked at the PC itself, sir."
            PENDING.update(at=now, paths=list(res["missing"]), all=False)
            out += "\nSay “yes, restore them” within three minutes and I will download the missing files from the repository (checked against their fingerprints)."
        return out
    return None


# ---------------- command line ----------------
def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent
    ref, offline, do_repair, include_changed, yes, do_update = ref_for(root), False, False, False, False, False
    it = iter(argv)
    for a in it:
        if a == "--ref":
            ref = next(it, ref)
        elif a == "--offline":
            offline = True
        elif a == "--repair":
            do_repair = True
        elif a == "--all":
            include_changed = True
        elif a == "--update":
            do_update = True
        elif a in ("--yes", "-y"):
            yes = True
        else:
            print(__doc__)
            return 2
    try:
        manifest, source = load_manifest(root, ref, offline)
    except CheckError as exc:
        print(exc)
        return 1
    if do_update:
        plan = classify(root, manifest)
        print(describe_update(plan, source))
        todo = plan["missing"] + plan["updates"] + (plan["conflicts"] + plan["unknown"] if include_changed else [])
        if not todo:
            return 0
        if offline:
            print("Offline: nothing can be downloaded.")
            return 1
        if not yes and input(f"\nDownload {len(todo)} file(s) from github.com/{REPO} ({ref})? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Nothing was changed.")
            return 1
        out = repair(root, manifest, todo, ref)
        print(describe_repair(out))
        return 0 if not out["failed"] else 1
    res = check(root, manifest)
    print(describe(res, source))
    todo = res["missing"] + (res["changed"] if include_changed else [])
    if not do_repair or not todo:
        if res["missing"] and not do_repair:
            print("\nTo restore the missing files run:  python filecheck.py --repair")
        return 1 if res["missing"] else 0
    if offline:
        print("Offline: nothing can be downloaded.")
        return 1
    if not yes and input(f"\nDownload {len(todo)} file(s) from github.com/{REPO} ({ref})? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Nothing was changed.")
        return 1
    out = repair(root, manifest, todo, ref)
    print(describe_repair(out))
    return 0 if not out["failed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
