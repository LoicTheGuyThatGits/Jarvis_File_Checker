"""Measures Smart commands: how often does your AI model pick the right tool?

    python tools/router_eval.py            run the 182 labelled examples through your model and print the scores
    python tools/router_eval.py --label    go through your own logged messages and say which tool each one wanted
    python tools/router_eval.py --mine     also score those (your labels stay in data/, on this PC)
    python tools/router_eval.py --limit 30 a quick run on the first 30 examples

Nothing is carried out: the script only looks at which tool the model would choose. It needs the model to be
reachable (Ollama running, or your cloud key set), exactly as for a normal chat.
The scores, and every example it got wrong, are also written to data/router-eval.json.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import tools_registry  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent / "router_examples.json"
TARGET_TOOL, TARGET_FALSE = 85.0, 3.0


def load_server():
    spec = importlib.util.spec_from_file_location("jarvis_server", ROOT / "app" / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_tools(example: dict) -> list[str]:
    tool = example.get("tool")
    return [] if not tool else ([tool] if isinstance(tool, str) else list(tool))


def judge(example: dict, plan) -> tuple[str, bool]:
    """('right' | 'wrong tool' | 'missed' | 'false alarm' | 'right none', arguments fine?)"""
    want, got = expected_tools(example), [s["tool"] for s in (plan or [])]
    if not want:
        return ("right none" if not got else "false alarm"), True
    if not got:
        return "missed", False
    if got != want:
        return "wrong tool", False
    args_ok = True
    if len(want) == 1:
        for key, words in (example.get("args") or {}).items():
            if words.lower() not in str(plan[0]["args"].get(key, "")).lower():
                args_ok = False
    return "right", args_ok


def evaluate(registry, ask_model, examples: list[dict], show=print) -> dict:
    rows, times = [], []
    for i, example in enumerate(examples, 1):
        raw = {"v": None}

        def ask(system, user):
            started = time.time()
            raw["v"] = ask_model(system, user)
            times.append(time.time() - started)
            return raw["v"]

        asked = registry.gate(example["text"])
        error = ""
        try:
            plan = tools_registry.parse(ask(registry.prompt(), example["text"]), registry, example["text"]) if asked else None
        except Exception as exc:                      # the model could not be reached
            plan, error = None, str(exc)[:200]
        verdict, args_ok = judge(example, plan)
        rows.append({"text": example["text"], "want": expected_tools(example), "got": [s["tool"] for s in (plan or [])], "verdict": verdict,
                     "args_ok": args_ok, "asked_model": asked, "model_said": (raw["v"] or "")[:300], "error": error})
        if show:
            show(f"[{i}/{len(examples)}] {verdict:<11} {example['text'][:70]}")
        if error and i >= 3 and all(r["error"] for r in rows):
            raise SystemExit("The model cannot be reached: " + error + "\nStart Jarvis (or Ollama) first, then run this again.")
    pos = [r for r in rows if r["want"]]
    neg = [r for r in rows if not r["want"]]
    right = [r for r in pos if r["verdict"] == "right"]
    pct = lambda a, b: round(100.0 * a / b, 1) if b else 0.0
    by_tool: dict[str, list[int]] = {}
    for r in pos:
        entry = by_tool.setdefault("+".join(r["want"]), [0, 0])
        entry[1] += 1
        entry[0] += r["verdict"] == "right"
    return {
        "examples": len(rows), "with_tool": len(pos), "without_tool": len(neg),
        "right_tool_pct": pct(len(right), len(pos)), "right_arguments_pct": pct(sum(1 for r in right if r["args_ok"]), len(right)),
        "missed_pct": pct(sum(1 for r in pos if r["verdict"] == "missed"), len(pos)),
        "wrong_tool_pct": pct(sum(1 for r in pos if r["verdict"] == "wrong tool"), len(pos)),
        "false_alarm_pct": pct(sum(1 for r in neg if r["verdict"] == "false alarm"), len(neg)),
        "model_calls": len(times), "seconds_per_call": round(sum(times) / len(times), 2) if times else 0.0,
        "by_tool": {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_tool.items())},
        "mistakes": [r for r in rows if r["verdict"] not in ("right", "right none") or not r["args_ok"]],
    }


def summary(result: dict, model: str = "") -> str:
    ok = result["right_tool_pct"] >= TARGET_TOOL and result["false_alarm_pct"] <= TARGET_FALSE
    lines = [
        "", "===== Smart commands: scores =====" + (f"  (model: {model})" if model else ""),
        f"Examples: {result['examples']}  ({result['with_tool']} that want a tool, {result['without_tool']} that do not)",
        f"Right tool:        {result['right_tool_pct']}%   (target: at least {TARGET_TOOL:.0f}%)",
        f"  of those, right details: {result['right_arguments_pct']}%",
        f"  missed (answered as chat): {result['missed_pct']}%    wrong tool: {result['wrong_tool_pct']}%",
        f"False alarms:      {result['false_alarm_pct']}%   (target: at most {TARGET_FALSE:.0f}%)",
        f"Speed:             {result['seconds_per_call']} s per question to the model ({result['model_calls']} questions)",
        "Per tool:          " + ", ".join(f"{k} {v}" for k, v in result["by_tool"].items()),
        "Verdict:           " + ("good enough to switch on." if ok else "not good enough yet: keep it off, or try a stronger model."),
    ]
    return "\n".join(lines)


def logged_messages(folder: Path, registry) -> list[str]:
    """Your own past messages that reached the chat model and look like they might have wanted a tool."""
    seen, out = set(), []
    for path in sorted(folder.glob("exchanges-*.jsonl")):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                users = [m["content"] for m in json.loads(line)["messages"] if m.get("role") == "user" and isinstance(m.get("content"), str)]
            except (ValueError, KeyError, TypeError):
                continue
            if users:
                text = " ".join(users[-1].split())
                if text.lower() not in seen and registry.gate(text):
                    seen.add(text.lower())
                    out.append(text)
    return out


def label(folder: Path, registry, target: Path, ask=input, show=print, limit: int = 50) -> int:
    names = sorted(registry.tools)
    try:
        done = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        done = []
    known = {d["text"].lower() for d in done}
    todo = [t for t in logged_messages(folder, registry) if t.lower() not in known][:limit]
    if not todo:
        show("No new logged messages to label (the training log is empty, off, or all done).")
        return 0
    show("For each message, type the number of the tool you wanted, 0 if you just wanted a chat answer,\ns to skip it, q to stop.\n")
    show("  0  none (just chat)\n" + "\n".join(f"  {i}  {n.replace('_', ' ')}: {registry.tools[n].description}" for i, n in enumerate(names, 1)) + "\n")
    added = 0
    for n, text in enumerate(todo, 1):
        answer = ask(f"[{n}/{len(todo)}] {text}\n> ").strip().lower()
        if answer == "q":
            break
        if answer.isdigit() and 0 <= int(answer) <= len(names):
            done.append({"text": text, "tool": names[int(answer) - 1] if int(answer) else None})
            added += 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
    show(f"\nSaved {added} label{'s' if added != 1 else ''} in {target} ({len(done)} in total). Now run:  python tools/router_eval.py --mine")
    return added


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Measure how well the AI model picks Jarvis's tools.")
    parser.add_argument("--label", action="store_true", help="label your own logged messages")
    parser.add_argument("--mine", action="store_true", help="also score the messages you labelled")
    parser.add_argument("--limit", type=int, default=0, help="only the first N examples")
    parser.add_argument("--quiet", action="store_true", help="only print the scores")
    args = parser.parse_args(argv)
    server = load_server()
    registry = server.router_registry()
    data = ROOT / "data"
    if args.label:
        label(data / "training", registry, data / "router-labels.json")
        return 0
    examples = json.loads(EXAMPLES.read_text(encoding="utf-8"))["examples"]
    if args.limit:
        examples = examples[:: max(1, len(examples) // args.limit)][: args.limit]
    model = server.ai_settings().get("model", "")
    result = evaluate(registry, server.router_ask_model, examples, None if args.quiet else print)
    print(summary(result, model))
    out = {"model": model, "at": time.strftime("%Y-%m-%d %H:%M"), "built_in": result}
    if args.mine:
        try:
            mine = json.loads((data / "router-labels.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            mine = []
        if mine:
            own = evaluate(registry, server.router_ask_model, mine, None if args.quiet else print)
            print(summary(own, model).replace("Smart commands: scores", "Your own messages: scores"))
            out["mine"] = {k: v for k, v in own.items() if k != "mistakes"}      # your messages are not copied into the report
        else:
            print("\nNo labels yet. Run:  python tools/router_eval.py --label")
    data.mkdir(exist_ok=True)
    (data / "router-eval.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nDetails of every mistake: {data / 'router-eval.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
