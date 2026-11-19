"""Compare local models on the same questions (the same as Settings > AI model > Compare models).

    python tools/model_bench.py                              the model you use now, on the 20 built-in questions
    python tools/model_bench.py --models jarvis,llama3.2:3b  several models
    python tools/model_bench.py --mine                       your last 10 messages from the training log instead
    python tools/model_bench.py --both --smart               both sets, plus Smart commands (40 examples per model)

Ollama must be installed. The answers, checks and timings are written to data/bench/ and shown in Settings, where you
can pick the best answer to each question without seeing which model wrote it.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compare local models on the same questions.")
    ap.add_argument("--models", default="", help="comma-separated Ollama model names (default: the local model in use)")
    ap.add_argument("--mine", action="store_true", help="your own last 10 messages instead of the built-in questions")
    ap.add_argument("--both", action="store_true", help="the built-in questions and your own")
    ap.add_argument("--smart", action="store_true", help="also score Smart commands on 40 examples per model")
    args = ap.parse_args(argv)
    spec = importlib.util.spec_from_file_location("jarvis_server", ROOT / "app" / "server.py")
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    import bench
    models = [m.strip() for m in args.models.split(",") if m.strip()] or [server.ai_settings(provider="local")["model"]]
    which = "both" if args.both else "mine" if args.mine else "built-in"
    questions = server.bench_questions(which)
    if not questions:
        print("There are no questions: your training log is empty. Use the built-in questions (leave out --mine).")
        return 1
    b = server.bench_obj()
    print(b.start(models, questions, server.local_chat_instructions() + server.language_instruction(), 40 if args.smart else 0))
    last = ""
    while b.state()["running"]:
        st = b.state()
        line = f"  {st['step']} ({st['done']}/{st['total']})"
        if line != last:
            print(line)
            last = line
        time.sleep(1)
    st = b.state()
    if st.get("error"):
        print("Stopped: " + st["error"])
    print()
    print(bench.report(st["run"]))
    print(f"\nSaved in data/bench/{st['run']['id']}.json. Open Jarvis > Settings > AI model > Compare models to read the answers and pick the best ones.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
