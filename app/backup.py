"""Encrypted backup of Jarvis' data folder (settings, memory, notes, planner, study history, tokens) and restore on any computer.

A backup is one file (.jbk) that only your passphrase opens. The passphrase is never stored: not on disk, not in the chat history.
Encryption uses only Python's standard library: the key comes from scrypt (a slow, memory-hard function), the data is encrypted with a
SHAKE-256 keystream, and an HMAC-SHA256 over everything is checked before anything is read, so a wrong passphrase or a damaged file is detected.
Keep the file somewhere safe (a USB stick, OneDrive). It contains your Gmail app password, Telegram and Spotify tokens, all encrypted.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import shutil
import time
import zipfile
from pathlib import Path, PurePosixPath

MAGIC = b"JBK1"
MIN_PASSPHRASE, MAX_TOTAL, MAX_FILE = 8, 400_000_000, 200_000_000
SKIP_DIRS = {"file-backups", "__pycache__"}
SKIP_SUFFIX = (".tmp", ".part", ".lock")
EXT = ".jbk"


class BackupError(ValueError):
    pass


def _keys(passphrase: str, salt: bytes) -> tuple[bytes, bytes]:
    raw = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=2 ** 15, r=8, p=1, dklen=64, maxmem=2 ** 27)
    return raw[:32], raw[32:]


def _xor(data: bytes, stream: bytes) -> bytes:
    return (int.from_bytes(data, "big") ^ int.from_bytes(stream, "big")).to_bytes(len(data), "big") if data else b""


def seal(plain: bytes, passphrase: str) -> bytes:
    salt, nonce = os.urandom(16), os.urandom(16)
    enc, mac = _keys(passphrase, salt)
    cipher = _xor(plain, hashlib.shake_256(enc + nonce).digest(len(plain)))
    body = MAGIC + salt + nonce + cipher
    return body + hmac.new(mac, body, hashlib.sha256).digest()


def unseal(blob: bytes, passphrase: str) -> bytes:
    if len(blob) < 4 + 16 + 16 + 32 or blob[:4] != MAGIC:
        raise BackupError("That is not a Jarvis backup file.")
    salt, nonce, cipher, tag = blob[4:20], blob[20:36], blob[36:-32], blob[-32:]
    enc, mac = _keys(passphrase, salt)
    if not hmac.compare_digest(hmac.new(mac, blob[:-32], hashlib.sha256).digest(), tag):
        raise BackupError("Wrong passphrase, or the file is damaged.")
    return _xor(cipher, hashlib.shake_256(enc + nonce).digest(len(cipher)))


def _wanted(rel: Path) -> bool:
    return not any(part in SKIP_DIRS for part in rel.parts) and not rel.name.endswith(SKIP_SUFFIX)


def make_backup(data_dir: Path, folder: Path, passphrase: str, now: float | None = None) -> dict:
    data_dir, folder = Path(data_dir).resolve(), Path(folder).expanduser()
    if len(passphrase or "") < MIN_PASSPHRASE:
        raise BackupError(f"Use a passphrase of at least {MIN_PASSPHRASE} characters.")
    if not data_dir.is_dir():
        raise BackupError("There is no data folder to back up yet.")
    folder = folder.resolve()
    if folder == data_dir or data_dir in folder.parents:
        raise BackupError("Choose a folder outside Jarvis' data folder.")
    buf, total, count = io.BytesIO(), 0, 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(data_dir.rglob("*")):
            if not p.is_file() or p.is_symlink() or not _wanted(p.relative_to(data_dir)):
                continue
            try:
                size = p.stat().st_size
                if size > MAX_FILE:
                    continue
                total += size
                if total > MAX_TOTAL:
                    raise BackupError("The data folder is too big for one backup (over 400 MB). Remove large documents or training logs first.")
                z.write(p, p.relative_to(data_dir).as_posix())
                count += 1
            except OSError:
                continue
        z.writestr("backup-info.json", json.dumps({"app": "jarvis", "created": time.time() if now is None else now, "files": count}))
    if count == 0:
        raise BackupError("There is nothing in the data folder to back up yet.")
    blob = seal(buf.getvalue(), passphrase)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(time.time() if now is None else now))
        target = folder / f"jarvis-data-{stamp}{EXT}"
        tmp = target.with_name(target.name + ".part")
        tmp.write_bytes(blob)
        tmp.replace(target)
    except OSError as exc:
        raise BackupError("I could not write the backup there: " + str(exc)[:100])
    return {"path": str(target), "files": count, "bytes": len(blob)}


def list_backups(folder: Path) -> list[dict]:
    try:
        found = [p for p in Path(folder).expanduser().iterdir() if p.is_file() and p.suffix == EXT]
    except OSError:
        return []
    out = []
    for p in sorted(found, key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
        st = p.stat()
        out.append({"name": p.name, "bytes": st.st_size, "at": st.st_mtime})
    return out


def _safe_name(name: str) -> str:
    p = PurePosixPath(name)
    if not name or "\\" in name or p.is_absolute() or any(x in ("", ".", "..") or ":" in x for x in p.parts):
        raise BackupError("The backup contains an unsafe file name.")
    return name


def restore_backup(file: Path, passphrase: str, data_dir: Path, safety_root: Path, now: float | None = None) -> dict:
    """Decrypts the file and copies its contents into data_dir. What was there before is copied to safety_root/data-before-restore-<time> first."""
    file, data_dir, safety_root = Path(file).expanduser(), Path(data_dir).resolve(), Path(safety_root).resolve()
    try:
        blob = file.read_bytes()
    except OSError:
        raise BackupError("I could not read that backup file.")
    plain = unseal(blob, passphrase)
    try:
        z = zipfile.ZipFile(io.BytesIO(plain))
        infos = [i for i in z.infolist() if not i.is_dir() and i.filename != "backup-info.json"]
        if sum(i.file_size for i in infos) > MAX_TOTAL * 2:
            raise BackupError("That backup is larger than expected, so I did not open it.")
        for i in infos:
            _safe_name(i.filename)
        if z.testzip() is not None:
            raise BackupError("The backup is damaged.")
    except zipfile.BadZipFile:
        raise BackupError("The backup is damaged.")
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(time.time() if now is None else now))
    kept = ""
    if data_dir.is_dir() and any(data_dir.iterdir()):
        dest = safety_root / f"data-before-restore-{stamp}"
        shutil.copytree(data_dir, dest, ignore=shutil.ignore_patterns("file-backups", "__pycache__"))
        kept = dest.name
    data_dir.mkdir(parents=True, exist_ok=True)
    for i in infos:
        target = (data_dir / i.filename).resolve()
        if data_dir not in target.parents:
            raise BackupError("The backup contains an unsafe file name.")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".part")
        tmp.write_bytes(z.read(i))
        tmp.replace(target)
    return {"restored": len(infos), "kept": kept}


# ---- settings: only the folder name and the time of the last backup are stored (never the passphrase) ----
def load_config(path: Path) -> dict:
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    return cfg if isinstance(cfg, dict) else {}


def save_config(path: Path, cfg: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    tmp.replace(path)


def default_folder() -> str:
    return str(Path.home() / "Documents" / "Jarvis-backups")


def age_text(last: float | None, now: float | None = None) -> str:
    if not last:
        return "never"
    days = ((time.time() if now is None else now) - last) / 86400
    return "today" if days < 1 else "yesterday" if days < 2 else f"{int(days)} days ago"


import re  # noqa: E402

ASK_BACKUP = re.compile(r"(?:(?:back\s?up|backup|save|export|make a backup of|take a backup of)\s+(?:all\s+)?(?:my\s+|the\s+)?(?:jarvis\s+)?(?:data|settings|notes|memory|everything|jarvis)|(?:make|create|do|start|run)\s+(?:me\s+)?(?:a\s+)?(?:new\s+)?back\s?up(?:\s+of\s+(?:my\s+)?(?:jarvis\s+)?(?:data|settings))?|back\s?up(?:\s+now)?|restore\s+(?:my\s+)?(?:data|backup|settings|jarvis data))", re.I)
ASK_LAST = re.compile(r"when\s+(?:was|did)\s+(?:my\s+|the\s+)?(?:last\s+)?(?:data\s+)?back\s?up(?:\s+(?:was\s+)?(?:made|done|taken))?|(?:when\s+was\s+)?(?:my\s+)?last\s+(?:data\s+)?back\s?up|(?:do|did)\s+i\s+have\s+a\s+back\s?up|how\s+old\s+is\s+my\s+(?:last\s+)?back\s?up", re.I)


def command(text: str, config_path: Path, now: float | None = None) -> str | None:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = re.sub(r"^(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?", "", t, flags=re.I)
    t = re.sub(r"\s*(?:please|for me|now)?\s*[.!?]*$", "", t, flags=re.I).strip()
    if not t or len(t) > 100:
        return None
    if ASK_LAST.fullmatch(t):
        last = load_config(config_path).get("last")
        return "You have never backed up your data, sir. Settings > Daily > Backup does it in a minute." if not last else f"Your last backup was {age_text(last, now)} (to {load_config(config_path).get('folder') or default_folder()})."
    if ASK_BACKUP.fullmatch(t):
        return ("Open Settings > Daily > Backup, type a passphrase and press “Back up now”, sir. I do not take the passphrase in chat so that it never ends up in your chat history. "
                "The same section restores a backup on this or another computer.")
    return None
