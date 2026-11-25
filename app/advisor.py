"""The PC advisor: looks at this PC (graphics card, memory, processor, disk, what is installed) and says which local model is
best for each job, how fast it will be, and what this PC can and cannot run.

How it decides:
- A model is fast only when all of it fits in the graphics card's memory (VRAM). What other programs already use there
  is left out, and a model needs a little more than its download size (its working memory for the conversation).
- Writing speed is limited by how fast the card reads its memory: about (memory speed / model size) words a second.
  Jarvis knows the memory speed of common cards; after "Measure real speed" it uses what it measured on this PC instead.
- When a model does not fit, Ollama puts the rest on the processor, which is many times slower; when even the system
  memory is too small, it cannot run at all.
- For each job it picks the best model that fits and is fast enough (chat must feel instant; code may be a bit slower),
  preferring what is already installed.

    report(hw, installed, measured, current, extras) -> {"pc", "roles", "models", "features", "advice", "text"}
hw: {"gpu": {"name", "vram_gb", "used_gb"} | None, "ollama_vram_gb", "ram_gb", "ram_free_gb", "cpu", "cores", "disk_free_gb", "battery"}
installed: [{"name", "size_gb", "caps": [...]}]      measured: {name: {"tps", "load_s", "gpu", "at"}}
current: {"chat", "autopilot", "code"}                extras: {"playwright", "pynput", "piper", "whisper", "ollama_version"}
"""
from __future__ import annotations

import re

# models worth suggesting (Ollama library, sizes of the default download); quality 1-5 per job
CATALOG = [
    {"name": "qwen3.5:2b", "size": 2.7, "vision": True, "q": {"chat": 2, "vision": 2, "code": 1}},
    {"name": "qwen3.5:4b", "size": 3.4, "vision": True, "q": {"chat": 3, "vision": 3, "code": 3}},
    {"name": "qwen3.5:9b", "size": 6.6, "vision": True, "q": {"chat": 4, "vision": 4, "code": 4}},
    {"name": "qwen3.5:27b", "size": 17.0, "vision": True, "q": {"chat": 5, "vision": 5, "code": 5}},
    {"name": "qwen3.5:35b", "size": 22.0, "active": 3 / 35, "vision": True, "q": {"chat": 5, "vision": 5, "code": 5}},
    {"name": "qwen3-vl:2b-instruct", "size": 1.9, "vision": True, "q": {"autopilot": 2, "vision": 2}},
    {"name": "qwen3-vl:4b-instruct", "size": 3.3, "vision": True, "q": {"autopilot": 3, "vision": 3}},
    {"name": "qwen3-vl:8b-instruct", "size": 6.2, "vision": True, "q": {"autopilot": 4, "vision": 4}},
    {"name": "qwen3-vl:30b-a3b-instruct", "size": 20.0, "active": 3 / 30, "vision": True, "q": {"autopilot": 5, "vision": 5}},
]
ROLES = {
    "chat": {"label": "Chat", "min_tps": 20, "why": "answers you in chat and by voice; it should feel instant"},
    "vision": {"label": "Pictures", "min_tps": 12, "why": "looks at photos and screenshots you send"},
    "autopilot": {"label": "Autopilot", "min_tps": 12, "why": "sees the screen and works the mouse and keyboard; needs to point precisely"},
    "code": {"label": "Jarvis Code", "min_tps": 12, "why": "writes and fixes code; a bigger model makes fewer mistakes"},
}
# memory speed (GB/s) of common graphics cards; laptop chips are slower than desktop ones of the same name
GPU_BW = [
    (r"4090.*laptop", 576), (r"4090", 1008), (r"4080.*laptop", 432), (r"4080", 717), (r"4070 ti", 504), (r"4070.*laptop", 256), (r"4070", 504),
    (r"4060 ti", 288), (r"4060.*laptop", 256), (r"4060", 272), (r"4050", 192), (r"5090", 1792), (r"5080", 960), (r"5070 ti", 896), (r"5070", 672),
    (r"5060 ti", 448), (r"5060", 448), (r"3090", 936), (r"3080 ti", 912), (r"3080.*laptop", 448), (r"3080", 760), (r"3070.*laptop", 448), (r"3070", 448),
    (r"3060.*laptop", 336), (r"3060", 360), (r"3050", 224), (r"2080", 448), (r"2070", 448), (r"2060", 336), (r"1660", 192), (r"1650", 128),
    (r"rx 7900", 960), (r"rx 7800", 624), (r"rx 7700", 432), (r"rx 7600", 288), (r"rx 6800", 512), (r"rx 6700", 384), (r"rx 6600", 224), (r"arc a770", 560), (r"arc a750", 512),
]
CPU_BW = 40.0           # system memory speed (GB/s) of a typical recent PC; what a model gets when it runs on the processor
EFFICIENCY = 0.6        # real speed reaches about this share of the memory limit
VRAM_MARGIN = 0.3       # GB kept free so the card does not run out while you use other programs


def gpu_bandwidth(name: str, vram_gb: float) -> float:
    n = (name or "").lower()
    for pat, bw in GPU_BW:
        if re.search(pat, n):
            return float(bw)
    return 200.0 if vram_gb >= 6 else 120.0


def model_info(m: dict) -> dict:
    """Catalog facts for a model (an installed one not in the catalog: guessed from its size and what Ollama says it can do)."""
    name = m["name"]
    cat = next((c for c in CATALOG if c["name"] == name or name.split(":")[0] + ":" + name.split(":")[-1] == c["name"]), None)
    if cat:
        return {**cat, **({"size": m["size_gb"]} if m.get("size_gb") else {})}
    size = float(m.get("size_gb") or 0)
    caps = set(m.get("caps") or [])
    level = 1 if size < 1.5 else 2 if size < 2.5 else 3 if size < 5.5 else 4 if size < 12 else 5
    low = name.lower()
    if re.search(r"moondream|llava:7b|bakllava", low):
        level = min(level, 2)
    vision = "vision" in caps or bool(re.search(r"llava|moondream|-vl|vision|gemma3|qwen3\.5|minicpm-v", low))
    q = {"chat": level, "code": max(1, level - (0 if re.search(r"coder|qwen|deepseek|codestral|devstral", low) else 1))}
    if vision:
        q["vision"] = level
        if re.search(r"qwen3-vl|qwen2\.5vl|qwen2\.5-vl", low):
            q["autopilot"] = level
        elif re.search(r"gemma3|qwen3\.5|llava|minicpm", low):
            q["autopilot"] = max(1, level - 2)          # can see, but points less precisely than Qwen-VL
    if "embedding" in caps or re.search(r"embed", low):
        q = {}
    return {"name": name, "size": size, "vision": vision, "q": q, "own": low.startswith("jarvis")}


def need_gb(size: float, ctx: int = 8192) -> float:
    """Graphics memory a model needs: its weights, the working memory for a conversation of `ctx` words, and some room."""
    return size + 0.35 + 0.06 * size * (ctx / 8192)


def estimate(info: dict, hw: dict, bw: float) -> dict:
    """How the model would run here: where ("gpu" all on the card, "split" partly on the processor, "cpu", "no") and words/s."""
    gpu = hw.get("gpu")
    size = info["size"]
    active = size * info.get("active", 1.0)                 # mixture-of-experts models read only part of themselves per word
    need = need_gb(size)
    room = usable_vram(hw)
    ram_room = max(0.0, float(hw.get("ram_free_gb") or 0) + float(hw.get("ollama_ram_gb") or 0) - 1.5)
    if gpu and need <= room:
        return {"where": "gpu", "tps": round(EFFICIENCY * bw / active, 1), "need_gb": round(need, 1)}
    if gpu and room > 1 and need - room <= ram_room:
        frac = room / need
        t = active * frac / bw + active * (1 - frac) / CPU_BW
        return {"where": "split", "tps": round(EFFICIENCY / t, 1), "need_gb": round(need, 1), "on_gpu": round(frac, 2)}
    if not gpu and need <= ram_room:
        return {"where": "cpu", "tps": round(EFFICIENCY * CPU_BW / active, 1), "need_gb": round(need, 1)}
    return {"where": "no", "tps": 0.0, "need_gb": round(need, 1)}


def usable_vram(hw: dict) -> float:
    gpu = hw.get("gpu")
    if not gpu:
        return 0.0
    others = max(0.0, float(gpu.get("used_gb") or 0) - float(hw.get("ollama_vram_gb") or 0))   # what other programs use now
    return max(0.0, float(gpu["vram_gb"]) - others - VRAM_MARGIN)


def calibrated_bw(hw: dict, measured: dict, infos: dict) -> tuple[float, str]:
    """The card's real memory speed, from a model measured fully on the card, else the known figure for this card."""
    best = []
    for name, m in (measured or {}).items():
        info = infos.get(name)
        if info and m.get("tps") and (m.get("gpu") or 0) >= 0.95 and info["size"] > 0.5:
            best.append(m["tps"] * info["size"] * info.get("active", 1.0) / EFFICIENCY)
    if best:
        return max(best), "measured"
    gpu = hw.get("gpu")
    return (gpu_bandwidth(gpu["name"], gpu["vram_gb"]) if gpu else CPU_BW), "estimated"


def report(hw: dict, installed: list[dict], measured: dict | None = None, current: dict | None = None, extras: dict | None = None) -> dict:
    measured, current, extras = measured or {}, current or {}, extras or {}
    have = {m["name"]: m for m in installed}
    infos = {m["name"]: model_info(m) for m in installed}
    for c in CATALOG:
        infos.setdefault(c["name"], dict(c))
    bw, bw_source = calibrated_bw(hw, measured, infos)
    rows = []
    for name, info in infos.items():
        if not info["q"]:
            continue
        est = estimate(info, hw, bw)
        m = measured.get(name)
        if m and m.get("tps"):
            est = {**est, "tps": round(m["tps"], 1), "measured": True,
                   "where": "gpu" if (m.get("gpu") or 0) >= 0.95 else "split" if (m.get("gpu") or 0) > 0 else est["where"]}
        disk_ok = name in have or info["size"] + 5 <= float(hw.get("disk_free_gb") or 0)
        rows.append({"name": name, "size_gb": round(info["size"], 1), "installed": name in have, "own": info.get("own", False), "vision": info["vision"],
                     "q": info["q"], **est, "disk_ok": disk_ok})
    rows.sort(key=lambda r: (not r["installed"], -max(r["q"].values()), r["size_gb"]))

    roles = []
    for role, meta in ROLES.items():
        best, best_score = None, -999
        for r in rows:
            q = r["q"].get(role)
            if not q or r["where"] == "no" or not r["disk_ok"]:
                continue
            # your own Jarvis model (its manner and commands are trained in) is kept for chat while it runs well; chat also values speed
            score = q * 10 + (3 if r["installed"] else 0) + (8 if r["own"] and role == "chat" else 0)
            if role == "chat":
                score += min(6.0, max(0.0, (r["tps"] - meta["min_tps"]) / 4))
            if r["tps"] < meta["min_tps"]:
                score -= 15 if r["tps"] < meta["min_tps"] / 2 else 6
            if r["where"] == "split":
                score -= 8
            if score > best_score:
                best, best_score = r, score
        cur = current.get(role) or (current.get("chat") if role == "vision" else "")
        cur_row = next((r for r in rows if r["name"] == cur), None)
        note = ""
        if cur_row and cur_row["where"] == "split":
            note = f"{cur} does not fit on the graphics card here: about {int((cur_row.get('on_gpu') or 0) * 100)} % of it runs on it, the rest on the processor, so it is slow."
        elif cur_row and role == "vision" and not cur_row["vision"]:
            note = f"{cur} cannot see pictures."
        elif cur_row and cur_row["tps"] and cur_row["tps"] < meta["min_tps"] / 2:
            note = f"{cur} writes about {cur_row['tps']:.0f} words a second here, which feels slow."
        roles.append({"role": role, "label": meta["label"], "why": meta["why"], "current": cur or "", "note": note,
                      "best": best and {k: best.get(k, False) for k in ("name", "installed", "where", "tps", "size_gb", "own", "measured")},
                      "same": bool(best and cur and (best["name"] == cur or best.get("own") and cur.startswith("jarvis")))})

    features, advice = features_for(hw, extras, bw), []
    gpu = hw.get("gpu")
    room = usable_vram(hw)
    distinct = {r["best"]["name"] for r in roles if r["best"]}
    big = [n for n in distinct if (infos.get(n) or {}).get("size", 0) > room / 2]
    if gpu and len(big) > 1:
        advice.append(f"Only one of these models fits on the graphics card at a time ({room:.1f} GB free for models), so switching from one job to another reloads the model (5 to 10 seconds). "
                      "Using the same model for several jobs avoids that: for example one qwen3.5 model for chat, pictures and code.")
    if hw.get("battery") and not hw["battery"].get("plugged"):
        advice.append("The laptop is on battery: Windows slows the graphics card down, so answers are slower until it is plugged in.")
    if gpu and gpu.get("used_gb") and float(gpu["used_gb"]) - float(hw.get("ollama_vram_gb") or 0) > 1.5:
        advice.append(f"Other programs use {float(gpu['used_gb']) - float(hw.get('ollama_vram_gb') or 0):.1f} GB of the graphics card right now (games, browsers, video). Closing them leaves more room for the models.")
    if float(hw.get("ram_gb") or 0) and float(hw.get("ram_free_gb") or 0) / float(hw["ram_gb"]) < 0.15:
        advice.append(f"Only {hw['ram_free_gb']:.1f} GB of the PC's memory is free: closing browser tabs and apps helps, because a model that does not fit on the card spills into it.")
    if bw_source == "estimated" and gpu:
        advice.append("The speeds are estimates for this graphics card. “Measure real speed” tries your installed models to replace them with real figures.")
    pc = {"gpu": gpu and f"{gpu['name']} ({gpu['vram_gb']:.0f} GB)", "vram_free_gb": round(room, 1), "ram_gb": hw.get("ram_gb"), "cpu": hw.get("cpu"),
          "disk_free_gb": hw.get("disk_free_gb"), "bandwidth": round(bw), "bandwidth_source": bw_source}
    out = {"pc": pc, "roles": roles, "models": rows, "features": features, "advice": advice}
    out["text"] = text_of(out)
    return out


def features_for(hw: dict, extras: dict, bw: float) -> list[dict]:
    f = []
    gpu = hw.get("gpu")
    add = lambda name, ok, detail: f.append({"name": name, "ok": ok, "detail": detail})
    if gpu:
        add("Graphics card", True, f"{gpu['name']}, {gpu['vram_gb']:.0f} GB: local AI runs on it" + (" (models up to about " + f"{usable_vram(hw) - 0.8:.0f}" + " GB fit whole)" if usable_vram(hw) > 1.5 else ""))
    else:
        add("Graphics card", False, "no graphics card Ollama can use was found: models run on the processor, so small ones (2B to 4B) are best")
    v = extras.get("ollama_version")
    if v is None:
        add("Ollama", False, "not running or not installed (ollama.com/download)")
    else:
        nums = tuple(int(x) for x in re.findall(r"\d+", v)[:3])
        add("Ollama", nums >= (0, 12, 7), f"version {v}" + ("" if nums >= (0, 12, 7) else ": too old for the Qwen3-VL and Qwen3.5 models, update it"))
    ram = float(hw.get("ram_gb") or 0)
    add("Memory", ram >= 16, f"{ram:.0f} GB" + (": enough" if ram >= 32 else ": fine for models that fit on the card; 32 GB would allow bigger ones partly on the processor" if ram >= 16 else ": tight, close other apps while using AI"))
    disk = float(hw.get("disk_free_gb") or 0)
    add("Disk space", disk >= 20, f"{disk:.0f} GB free" + ("" if disk >= 20 else ": models are 2 to 20 GB each, free some space before downloading"))
    add("Jarvis browser (Playwright)", bool(extras.get("playwright")), "Autopilot uses websites directly and Jarvis Code checks pages" if extras.get("playwright") else "not installed: Settings > Computer control > Install browser control")
    add("Show Autopilot how (pynput)", bool(extras.get("pynput")), "can record what you show it" if extras.get("pynput") else "not installed: Settings > Computer control > Install recording")
    add("Offline voice (Piper)", bool(extras.get("piper")), "Jarvis speaks without the internet" if extras.get("piper") else "not installed: the browser or cloud voice is used")
    if extras.get("whisper") is not None:
        add("Offline dictation (Whisper)", bool(extras.get("whisper")), "speech is understood on this PC" if extras.get("whisper") else "not set up")
    if hw.get("battery") is not None:
        b = hw["battery"]
        add("Power", bool(b.get("plugged")), "plugged in" if b.get("plugged") else f"on battery ({b.get('percent', 0):.0f} %): the graphics card is slowed down")
    return f


def text_of(r: dict) -> str:
    pc = r["pc"]
    lines = [f"This PC: {pc['gpu'] or 'no graphics card for AI'}, {pc['ram_gb']:.0f} GB of memory, {pc['disk_free_gb']:.0f} GB free on the disk. "
             f"Room for models on the graphics card: {pc['vram_free_gb']:.1f} GB."]
    for role in r["roles"]:
        b = role["best"]
        if not b:
            lines.append(f"- {role['label']}: nothing suitable runs here.")
            continue
        where = "all on the graphics card" if b["where"] == "gpu" else "partly on the processor" if b["where"] == "split" else "on the processor"
        speed = f"about {b['tps']:.0f} words a second, {where}"
        if role["same"]:
            lines.append(f"- {role['label']}: {role['current']} is the best choice here ({speed}).")
        else:
            lines.append(f"- {role['label']}: {b['name']}" + ("" if b["installed"] else f" (to download, {b['size_gb']:.1f} GB)") + f": {speed}."
                         + (f" Now: {role['current']}." if role["current"] else "") + (f" {role['note']}" if role["note"] else ""))
    no = [m["name"] for m in r["models"] if m["where"] == "no" and not m["installed"]]
    if no:
        lines.append("Too big for this PC: " + ", ".join(no[:6]) + ".")
    lines += r["advice"][:3]
    return "\n".join(lines)


ASK = re.compile(r"(?:(?:hey\s+)?jarvis[,.:]?\s+)?(?:what|which)\s+(?:ai\s+)?models?\s+(?:can|could|should|would)\s+(?:my|this)\s+(?:pc|computer|laptop)\s+(?:run|use|handle)|"
                 r"(?:what(?:'s|\s+is)\s+the\s+best\s+(?:ai\s+)?model\s+for\s+(?:my|this)\s+(?:pc|computer|laptop))|(?:check|analy[sz]e)\s+(?:my|this)\s+(?:pc|computer|laptop)(?:'s)?\s+(?:for\s+ai|hardware)|"
                 r"what\s+can\s+(?:my|this)\s+(?:pc|computer|laptop)\s+run", re.I)
