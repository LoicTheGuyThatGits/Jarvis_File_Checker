"""The model test bench: the same questions to several local models, side by side.

For each model it measures how long an answer takes and how fast it writes, runs automatic checks (Jarvis's manner: no
exclamation marks or emoji, short enough; the right fact; French answered in French; a PC request answered with the right
action; code in a fenced block), and keeps every answer so you can pick the best one yourself, without seeing which model
wrote which ("blind"). Optionally it also scores Smart commands (does the model pick the right tool?) on part of the labelled
examples. Results are saved in data/bench/.

    Bench(folder, ask, smart=None)     ask(model, system, user) -> (text, seconds, completion tokens or None)
        .start(models, questions, system, smart_limit=0)   runs in the background
        .state() .stop() .pick(run_id, index, model) .latest()
    load_questions(path)               the built-in questions (tools/bench_questions.json)
    own_questions(folder, limit)       your latest distinct messages from the training log
    checks(question, answer)           [(name, passed)]
"""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
from pathlib import Path

EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")
FRENCH = {"le", "la", "les", "des", "est", "et", "un", "une", "du", "que", "qui", "pour", "pas", "dans", "sur", "avec", "vous", "je", "il", "ce", "sont", "au", "en", "à"}
ENGLISH = {"the", "and", "is", "are", "of", "to", "in", "that", "it", "for", "with", "you", "this", "on", "be", "your", "a", "an"}
MAX_QUESTIONS, MAX_MODELS = 40, 4


def words(text: str) -> list[str]:
    return re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", (text or "").lower())


def is_french(text: str) -> bool:
    w = words(re.sub(r"```.*?```", " ", text or "", flags=re.S))
    return sum(x in FRENCH for x in w) > sum(x in ENGLISH for x in w)


def json_action(text: str) -> str | None:
    """The action type in a reply that is a JSON object, if any."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except ValueError:
        return None
    action = obj.get("action") if isinstance(obj, dict) else None
    return str(action.get("type")) if isinstance(action, dict) and action.get("type") else None


def checks(q: dict, answer: str) -> list[tuple[str, bool]]:
    out: list[tuple[str, bool]] = []
    text = answer or ""
    prose = re.sub(r"```.*?```", " ", text, flags=re.S)
    if not q.get("code") and not q.get("action"):
        out.append(("no exclamation marks or emoji", "!" not in prose.replace("!=", "") and not EMOJI.search(prose)))
        limit = int(q.get("max_words") or 120)
        out.append((f"at most {limit} words", len(words(prose)) <= limit))
    if q.get("expect"):
        wanted = q["expect"] if isinstance(q["expect"], list) else [q["expect"]]
        out.append(("right answer (" + " / ".join(wanted) + ")", any(w.lower() in text.lower() for w in wanted)))
    if q.get("lang") == "fr":
        out.append(("answers in French", is_french(text)))
    if q.get("action"):
        out.append((f"asks for the {q['action']} action", json_action(text) == q["action"]))
    if q.get("code"):
        out.append((f"code in a ```{q['code']} block", bool(re.search(rf"```\s*{re.escape(q['code'])}\b", text, re.I))))
    return out


def load_questions(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [dict(q, source="built-in") for q in data.get("questions", []) if isinstance(q, dict) and q.get("text")]


def own_questions(folder: Path, limit: int = 10) -> list[dict]:
    """Your latest distinct chat messages (from the training log, which stays on this PC)."""
    seen, out = set(), []
    for path in sorted(Path(folder).glob("exchanges-*.jsonl"), reverse=True):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("kind") != "chat":
                continue
            users = [m.get("content") for m in entry.get("messages") or [] if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str)]
            if not users:
                continue
            text = " ".join(users[-1].split())[:600]
            if 3 <= len(text) and text.lower() not in seen:
                seen.add(text.lower())
                out.append({"text": text, "source": "mine"})
                if len(out) >= limit:
                    return out
    return out


class Bench:
    def __init__(self, folder: Path, ask, smart=None):
        self.folder = Path(folder)
        self.ask = ask
        self.smart = smart                     # smart(model, limit) -> {"right_tool_pct", "false_alarm_pct", "seconds_per_call"}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self._state = {"running": False, "done": 0, "total": 0, "step": "", "error": "", "run": None}

    def state(self) -> dict:
        with self.lock:
            st = dict(self._state)
        if not st["running"] and st["run"] is None:
            st["run"] = self.latest()
        return st

    def _set(self, **kw) -> None:
        with self.lock:
            self._state.update(kw)

    def stop(self) -> None:
        self.stop_event.set()

    def start(self, models: list[str], questions: list[dict], system: str, smart_limit: int = 0) -> str:
        models = [m for m in dict.fromkeys(str(m).strip() for m in models) if m][:MAX_MODELS]
        questions = questions[:MAX_QUESTIONS]
        if len(models) < 1:
            raise ValueError("Pick at least one model.")
        if not questions:
            raise ValueError("There are no questions to ask.")
        with self.lock:
            if self._state["running"]:
                raise ValueError("A comparison is already running.")
            self._state = {"running": True, "done": 0, "total": len(models) * (len(questions) + (1 if smart_limit else 0)), "step": "starting", "error": "", "run": None}
        self.stop_event.clear()
        threading.Thread(target=self._run, args=(models, questions, system, smart_limit), daemon=True).start()
        return f"Comparing {len(models)} model{'s' if len(models) != 1 else ''} on {len(questions)} questions."

    def _run(self, models: list[str], questions: list[dict], system: str, smart_limit: int) -> None:
        run = {"id": time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2), "at": time.strftime("%Y-%m-%d %H:%M"), "models": models,
               "questions": [{"text": q["text"], "source": q.get("source", "built-in"), "answers": {}, "pick": None} for q in questions], "summary": {}, "stopped": False}
        done = 0
        try:
            for model in models:
                self._set(step=f"{model}: loading")
                try:
                    self.ask(model, "", "Reply with the single word OK.")         # loads the model, so the first answer is timed fairly
                except Exception as exc:
                    for item in run["questions"]:
                        item["answers"][model] = {"text": "", "seconds": None, "tokens": None, "checks": [], "error": str(exc)[:200]}
                    done += len(questions) + (1 if smart_limit and self.smart else 0)
                    self._set(done=done)
                    continue
                for i, q in enumerate(questions):
                    if self.stop_event.is_set():
                        run["stopped"] = True
                        raise StopIteration
                    self._set(step=f"{model}: question {i + 1} of {len(questions)}")
                    try:
                        text, seconds, tokens = self.ask(model, system, q["text"])
                        entry = {"text": text[:6000], "seconds": round(seconds, 2), "tokens": tokens, "checks": [[n, ok] for n, ok in checks(q, text)], "error": ""}
                    except Exception as exc:
                        entry = {"text": "", "seconds": None, "tokens": None, "checks": [], "error": str(exc)[:200]}
                    run["questions"][i]["answers"][model] = entry
                    done += 1
                    self._set(done=done)
                if smart_limit and self.smart:
                    if self.stop_event.is_set():
                        run["stopped"] = True
                        raise StopIteration
                    self._set(step=f"{model}: Smart commands ({smart_limit} examples)")
                    try:
                        run.setdefault("smart", {})[model] = self.smart(model, smart_limit)
                    except Exception as exc:
                        run.setdefault("smart", {})[model] = {"error": str(exc)[:200]}
                    done += 1
                    self._set(done=done)
        except StopIteration:
            pass
        except Exception as exc:
            self._set(error=str(exc)[:300])
        run["summary"] = summarize(run)
        self.save(run)
        self._set(running=False, step="stopped" if run["stopped"] else "done", run=run)

    # ---- results ----
    def save(self, run: dict) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / f"{run['id']}.json").write_text(json.dumps(run, indent=1, ensure_ascii=False), encoding="utf-8")

    def latest(self) -> dict | None:
        files = sorted(self.folder.glob("*.json")) if self.folder.is_dir() else []
        for path in reversed(files):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
        return None

    def pick(self, run_id: str, index: int, model: str) -> dict:
        if not re.fullmatch(r"[\w-]{6,40}", run_id or ""):
            raise ValueError("Unknown comparison.")
        path = self.folder / f"{run_id}.json"
        with self.lock:
            try:
                run = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise ValueError("That comparison is no longer there.") from None
            if not 0 <= index < len(run["questions"]) or (model and model not in run["models"]):
                raise ValueError("Unknown answer.")
            run["questions"][index]["pick"] = model or None
            run["summary"] = summarize(run)
            path.write_text(json.dumps(run, indent=1, ensure_ascii=False), encoding="utf-8")
            if self._state.get("run") and self._state["run"].get("id") == run_id:
                self._state["run"] = run
        return run


def summarize(run: dict) -> dict:
    out = {}
    for model in run["models"]:
        answers = [q["answers"].get(model) for q in run["questions"] if q["answers"].get(model)]
        timed = [a for a in answers if a.get("seconds") is not None and not a.get("error")]
        secs = sum(a["seconds"] for a in timed)
        toks = sum(a["tokens"] or 0 for a in timed if a.get("tokens"))
        tok_secs = sum(a["seconds"] for a in timed if a.get("tokens"))
        results = [ok for a in answers for _, ok in a.get("checks", [])]
        smart = (run.get("smart") or {}).get(model)
        out[model] = {"answered": len(timed), "errors": sum(1 for a in answers if a.get("error")),
                      "avg_seconds": round(secs / len(timed), 2) if timed else None,
                      "tokens_per_second": round(toks / tok_secs, 1) if toks and tok_secs else None,
                      "checks_passed": sum(results), "checks_total": len(results),
                      "checks_pct": round(100 * sum(results) / len(results)) if results else None,
                      "picks": sum(1 for q in run["questions"] if q.get("pick") == model),
                      "smart": smart}
    return out


def report(run: dict) -> str:
    """The summary as text (for the command line)."""
    lines = [f"Model comparison {run['at']} ({len(run['questions'])} questions)" + (" (stopped early)" if run.get("stopped") else ""), ""]
    lines.append(f"{'model':<24}{'s/answer':>10}{'tok/s':>8}{'checks':>10}{'picks':>7}{'smart':>9}")
    for model, s in run["summary"].items():
        smart = s.get("smart") or {}
        lines.append(f"{model:<24}{str(s['avg_seconds'] or '-'):>10}{str(s['tokens_per_second'] or '-'):>8}"
                     f"{(str(s['checks_pct']) + '%') if s['checks_pct'] is not None else '-':>10}{s['picks']:>7}"
                     f"{(str(smart.get('right_tool_pct')) + '%') if smart.get('right_tool_pct') is not None else '-':>9}")
    failed = [(q["text"][:60], m, n) for q in run["questions"] for m, a in q["answers"].items() for n, ok in a.get("checks", []) if not ok]
    if failed:
        lines += ["", "Checks not passed:"] + [f"  {m}: {n}  ({t})" for t, m, n in failed[:40]]
    return "\n".join(lines)
