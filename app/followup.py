"""Follow-up help for small local models.

A short message like "translate that", "the second one" or "and in French?" means nothing without the conversation before it,
and small models often lose that thread. Before such a message goes to the model, this adds a short note saying what it refers to.
Nothing here calls a model: it only looks at the last few messages, so it adds no waiting time.
"""
from __future__ import annotations

import re

ORDINALS = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5, "5th": 5,
            "sixth": 6, "6th": 6, "seventh": 7, "7th": 7, "eighth": 8, "8th": 8, "ninth": 9, "9th": 9, "tenth": 10, "10th": 10}
NOUNS = r"(?:one|option|result|item|answer|choice|suggestion|idea|point|step|link|file|song|track|email|mail|message|task|event|note|line|entry|book|movie|film|place|restaurant)s?"
ORDINAL_RE = re.compile(
    r"\b(?:the\s+)?(?P<w>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th|last|final)\b(?:\s+" + NOUNS + r")?"
    r"|\b(?:number|no\.?|#|option|item|result|choice|step)\s*(?P<n>\d{1,2})\b", re.I)
PRONOUN_RE = re.compile(r"\b(?:it|its|that|this|those|these|them|they|that one|this one|the same|the other one|the other|another one|the previous one|the last one)\b", re.I)
ELLIPSIS_START = re.compile(r"^(?:and|but|also|so|then|what about|how about|why|why not|how come|really|more|less|again|another|shorter|longer|simpler|easier|briefer|"
                            r"in (?:french|english|german|spanish|italian|portuguese|arabic|russian|chinese|japanese|detail)|with|without|without the|more detail|go on|continue|explain|"
                            r"translate|summari[sz]e|rewrite|redo|expand|elaborate|simplify|shorten|what do you mean|what does (?:that|it) mean|can you (?:explain|expand|elaborate))\b", re.I)
SELF_CONTAINED = re.compile(r"\b(?:open|close|launch|start|play|pause|volume|mute|lock|screenshot|timer|alarm|remind|weather|search|google|look up|what is the time|what time)\b", re.I)
LIST_ITEM = re.compile(r"^\s*(?:(\d{1,2})[.)]|[-•*–])\s+(.+?)\s*$")


def list_items(text: str) -> list[str]:
    items = []
    for line in (text or "").splitlines():
        m = LIST_ITEM.match(line)
        if m:
            items.append(re.sub(r"[*_`]+", "", m.group(2)).strip())
    return items


def _clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def reference(text: str, last_assistant: str) -> str | None:
    """'the second one' -> the second item of the list in Jarvis' last answer; None when it does not refer to a list."""
    items = list_items(last_assistant)
    if not items:
        return None
    m = ORDINAL_RE.search(text)
    if not m:
        return None
    word = (m.group("w") or "").lower()
    if m.group("n"):
        index = int(m.group("n")) - 1
    elif word in ("last", "final"):
        index = len(items) - 1
    else:
        index = ORDINALS[word] - 1
    if 0 <= index < len(items):
        return _clip(items[index], 200)
    return None


def hint(text: str, history: list[dict]) -> str | None:
    """The message with a note on what it refers to, or None when it needs none. `history` holds the messages before it."""
    text = (text or "").strip()
    words = text.split()
    if not text or len(words) > 14 or not history:
        return None
    last_assistant = next((m["content"] for m in reversed(history) if m["role"] == "assistant" and m["content"].strip()), "")
    if not last_assistant:
        return None
    previous_user = next((m["content"] for m in reversed(history) if m["role"] == "user" and m["content"].strip() != text), "")
    item = reference(text, last_assistant)
    if item:
        return f"{text}\n\n(Note for you: “{ORDINAL_RE.search(text).group(0).strip()}” means this item from your last answer: “{item}”.)"
    if len(words) > 10 and not ELLIPSIS_START.match(text):
        return None
    if SELF_CONTAINED.search(text) and not PRONOUN_RE.search(text):
        return None
    if PRONOUN_RE.search(text) or ELLIPSIS_START.match(text):
        context = f"(Note for you: this is a follow-up. "
        if previous_user:
            context += f"The user's earlier message was: “{_clip(previous_user, 220)}”. "
        context += f"Your last answer was: “{_clip(last_assistant, 420)}”. Answer the follow-up about that, and do not ask what “it” or “that” means unless it is truly unclear.)"
        return f"{text}\n\n{context}"
    return None
