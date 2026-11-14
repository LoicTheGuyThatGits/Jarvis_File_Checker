"""Turn the saved Jarvis exchanges into a fine-tuning file.

Reads data/training/exchanges-*.jsonl and ratings.jsonl, and writes data/training/jarvis-finetune.jsonl
in the chat format that Unsloth, Hugging Face and most fine-tuning tools read:

    {"messages": [{"role": "system", ...}, {"role": "user", ...}, ..., {"role": "assistant", ...}]}

By default only answers marked 👍 are kept. Use --include-unrated to also keep answers with no rating
(answers marked 👎 are always left out), and --no-system to drop the long instructions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FOLDER = Path(__file__).resolve().parent.parent / "data" / "training"


def load_ratings(folder: Path) -> dict[str, str]:
    ratings: dict[str, str] = {}
    try:
        for line in (folder / "ratings.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                ratings[row["id"]] = row["rating"]          # the latest rating of an exchange wins
            except (ValueError, KeyError, TypeError):
                continue
    except OSError:
        pass
    return ratings


def export(folder: Path, include_unrated: bool = False, with_system: bool = True, kinds: tuple = ("chat",)) -> tuple[int, int, Path]:
    ratings = load_ratings(folder)
    kept = seen = 0
    target = folder / "jarvis-finetune.jsonl"
    with open(target, "w", encoding="utf-8") as out:
        for path in sorted(folder.glob("exchanges-*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    rating = ratings.get(row["id"], "none")
                    seen += 1
                    if row.get("kind", "chat") not in kinds or rating == "down" or (rating != "up" and not include_unrated):
                        continue
                    messages = [m for m in row["messages"] if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)]
                    if not messages or messages[-1]["role"] != "user" or not row["reply"].strip():
                        continue
                    if with_system and row.get("system"):
                        messages = [{"role": "system", "content": row["system"]}] + messages
                    out.write(json.dumps({"messages": messages + [{"role": "assistant", "content": row["reply"]}]}, ensure_ascii=False) + "\n")
                    kept += 1
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
    return kept, seen, target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export saved Jarvis exchanges as a fine-tuning file.")
    parser.add_argument("--include-unrated", action="store_true", help="also keep answers that were never rated")
    parser.add_argument("--no-system", action="store_true", help="leave out the system instructions")
    parser.add_argument("--all-kinds", action="store_true", help="also keep web research and document answers (their prompts carry page or document text)")
    args = parser.parse_args()
    kept, seen, target = export(FOLDER, args.include_unrated, not args.no_system, ("chat", "research", "documents") if args.all_kinds else ("chat",))
    print(f"{kept} of {seen} saved exchanges written to {target}")
    if not kept:
        print("Nothing to export yet. Mark good answers with the thumbs-up under them, or run again with --include-unrated.")
