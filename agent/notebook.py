"""notebook.py — THE ONLY FILE THAT WRITES HISTORY.

Same rule as memory.py owning memory/ and llm.py owning the model. Until now
JARVIS had no history at all: every question was one isolated call, and the
moment the answer reached the page it was gone. You could not look up what you
asked last week, and you could not say "and of those, which are PARINOX?"
because there was no "those".

WHY IT LIVES IN THE REPOSITORY, NOT IN state_dir(). data.py draws that line
already: state_dir() is the runtime's own scratch, "nothing personal goes in
it, and none of it is versioned". History is the opposite of that on both
counts. It goes next to memory/, which is the folder you sync — so sharing
your history with your other machine is copying a folder, and needs no server,
no account and no change to what this program will talk to.

That also means it is personal, in the strongest sense this project has yet
produced: an answer about your accounts payable quotes your accounts payable.
.gitignore excludes history/*.jsonl for the same reason it excludes
memory/*.md. Delete that line if you would rather version them.

WHY JSONL. Append-only, so a crash halfway through writing one turn cannot
corrupt the ones already there — the reader skips the broken line and carries
on. Greppable with the tools you already have. And it merges in git without a
fight, which matters if you really do sync it between two machines.

Run it directly to see what is recorded:  python -m agent.notebook
"""

from __future__ import annotations

import json
import sys
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):  # allow `python agent/notebook.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod

# A turn is a question and its answer. A thread is turns that belong together —
# it is what makes a follow-up mean anything.
THREAD_TURNS = 6          # how many earlier turns a follow-up can see
ANSWER_IN_PROMPT = 1200   # chars of an earlier answer carried into the next
MAX_TURNS_KEPT = 5000     # per month file; beyond this the oldest are dropped


@dataclass
class Turn:
    """One question and its answer, with everything needed to audit it later."""

    id: str
    thread: str
    when: float
    kind: str
    question: str
    answer: str
    citations: list[dict] = field(default_factory=list)
    considered: list[str] = field(default_factory=list)
    recalled: list[str] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    model: str = ""
    seconds: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id, "thread": self.thread, "when": self.when,
            "kind": self.kind, "question": self.question, "answer": self.answer,
            "citations": self.citations, "considered": self.considered,
            "recalled": self.recalled, "usage": self.usage,
            "model": self.model, "seconds": self.seconds,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Turn":
        return cls(
            id=str(raw.get("id") or ""),
            thread=str(raw.get("thread") or ""),
            when=float(raw.get("when") or 0),
            kind=str(raw.get("kind") or "ask"),
            question=str(raw.get("question") or ""),
            answer=str(raw.get("answer") or ""),
            citations=list(raw.get("citations") or []),
            considered=list(raw.get("considered") or []),
            recalled=list(raw.get("recalled") or []),
            usage=dict(raw.get("usage") or {}),
            model=str(raw.get("model") or ""),
            seconds=float(raw.get("seconds") or 0),
        )


# ---------------------------------------------------------------------------
# Where
# ---------------------------------------------------------------------------

def _root() -> Path:
    path = data_mod.ROOT / "history"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _file_for(when: float) -> Path:
    """One file per month. Small enough to read, few enough to list."""
    return _root() / (time.strftime("%Y-%m", time.localtime(when)) + ".jsonl")


def files() -> list[Path]:
    """Every month file, newest first."""
    try:
        return sorted(_root().glob("*.jsonl"), reverse=True)
    except OSError:
        return []


def new_thread() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def record(answer, thread: str = "") -> Turn:
    """Store one answer. Returns the Turn, so the caller can send back its id.

    Never raises for a disk problem: a history that cannot be written is a
    lost note, not a lost answer, and the person already has the answer.
    """
    payload = answer.to_dict() if hasattr(answer, "to_dict") else dict(answer)
    now = time.time()
    turn = Turn(
        id=uuid.uuid4().hex[:12],
        thread=thread or new_thread(),
        when=now,
        kind=str(payload.get("kind") or "ask"),
        question=str(payload.get("question") or ""),
        answer=str(payload.get("answer") or payload.get("text") or ""),
        citations=list(payload.get("citations") or []),
        considered=list(payload.get("considered") or []),
        recalled=list(payload.get("recalled") or []),
        usage=dict(payload.get("usage") or {}),
        model=str((payload.get("usage") or {}).get("model") or ""),
        seconds=float(payload.get("seconds") or 0),
    )
    try:
        line = json.dumps(turn.to_dict(), ensure_ascii=False)
        path = _file_for(now)

        # If the last write was cut off mid-line — killed process, full disk —
        # the file does not end in a newline, and appending would weld this
        # record onto the broken one and lose BOTH. Close the line first.
        # Without this the format's whole claim is false: a crash would cost
        # not just the turn being written but the next one too.
        needs_newline = False
        try:
            if path.exists() and path.stat().st_size:
                with path.open("rb") as probe:
                    probe.seek(-1, 2)
                    needs_newline = probe.read(1) != b"\n"
        except OSError:
            needs_newline = False

        with path.open("a", encoding="utf-8") as handle:
            handle.write(("\n" if needs_newline else "") + line + "\n")
    except (OSError, TypeError, ValueError) as exc:
        print(f"  history not written: {exc}", file=sys.stderr)
    return turn


def forget(turn_id: str) -> bool:
    """Delete one turn. Rewrites the month file without it."""
    for path in files():
        kept, found = [], False
        for turn in _read(path):
            if turn.id == turn_id:
                found = True
            else:
                kept.append(turn)
        if not found:
            continue
        try:
            path.write_text(
                "".join(json.dumps(t.to_dict(), ensure_ascii=False) + "\n" for t in kept),
                encoding="utf-8",
            )
        except OSError:
            return False
        return True
    return False


def forget_thread(thread_id: str) -> int:
    """Delete a whole conversation."""
    gone = 0
    for path in files():
        kept, dropped = [], 0
        for turn in _read(path):
            if turn.thread == thread_id:
                dropped += 1
            else:
                kept.append(turn)
        if not dropped:
            continue
        try:
            path.write_text(
                "".join(json.dumps(t.to_dict(), ensure_ascii=False) + "\n" for t in kept),
                encoding="utf-8",
            )
            gone += dropped
        except OSError:
            pass
    return gone


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def _read(path: Path) -> list[Turn]:
    """Every turn in one file. A broken line is skipped, not fatal.

    This is the whole reason the format is one JSON object per line: a half
    written record costs you that record and nothing else.
    """
    out: list[Turn] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        if isinstance(raw, dict):
            out.append(Turn.from_dict(raw))
    return out


def _fold(text: str) -> str:
    """Lowercase and strip accents, so searching for 'atraso' finds 'atrasô'."""
    lowered = text.lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", lowered)
        if not unicodedata.combining(c)
    )


def turns(limit: int = 50, query: str = "") -> list[Turn]:
    """Recorded turns, newest first, optionally filtered."""
    wanted = [w for w in _fold(query).split() if w]
    found: list[Turn] = []
    for path in files():
        batch = _read(path)
        batch.reverse()                       # newest first inside the month
        for turn in batch:
            if wanted:
                hay = _fold(f"{turn.question} {turn.answer}")
                if not all(word in hay for word in wanted):
                    continue
            found.append(turn)
            if len(found) >= limit:
                return found
    return found


def thread(thread_id: str, limit: int = THREAD_TURNS) -> list[Turn]:
    """The turns of one conversation, oldest first — reading order."""
    if not thread_id:
        return []
    found: list[Turn] = []
    for path in files():                      # newest month first
        for turn in reversed(_read(path)):
            if turn.thread == thread_id:
                found.append(turn)
                if len(found) >= limit:
                    break
        if len(found) >= limit:
            break
    found.reverse()
    return found


def threads(limit: int = 30) -> list[dict[str, object]]:
    """Conversations, newest first: id, first question, how many turns."""
    seen: dict[str, dict[str, object]] = {}
    for turn in turns(limit=limit * 8):
        entry = seen.get(turn.thread)
        if entry is None:
            if len(seen) >= limit:
                continue
            seen[turn.thread] = {
                "thread": turn.thread, "title": turn.question or turn.kind,
                "when": turn.when, "turns": 1, "last": turn.id,
            }
        else:
            entry["turns"] = int(entry["turns"]) + 1
            # turns() is newest first, so the last one seen is the oldest, and
            # the oldest question is what the conversation was actually about.
            entry["title"] = turn.question or entry["title"]
    return list(seen.values())


def conversation_block(thread_id: str) -> str:
    """Earlier turns, shaped for the prompt. Empty when there are none.

    The question goes in whole and the answer truncated: a follow-up depends
    on what was asked far more than on every word of the reply, and the notes
    still have to fit.
    """
    earlier = thread(thread_id)
    if not earlier:
        return ""
    parts = []
    for turn in earlier:
        reply = turn.answer.strip()
        if len(reply) > ANSWER_IN_PROMPT:
            reply = reply[:ANSWER_IN_PROMPT].rstrip() + " […]"
        parts.append(f"Q: {turn.question.strip()}\nA: {reply}")
    return "\n\n".join(parts)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    query = " ".join(sys.argv[1:])
    found = turns(limit=20, query=query)
    print(f"\n  histórico  {_root()}")
    print(f"  arquivos   {len(files())}   turnos mostrados: {len(found)}"
          + (f"   filtro: {query!r}" if query else "") + "\n")
    for turn in found:
        when = time.strftime("%d/%m %H:%M", time.localtime(turn.when))
        cost = turn.usage.get("output_tokens")
        print(f"  {when}  [{turn.kind}] {turn.question[:58]}")
        print(f"           {len(turn.answer)} chars, {len(turn.citations)} citações"
              + (f", {cost} tokens" if cost else "")
              + f"  thread {turn.thread}")
    if not found:
        print("  (nada gravado ainda)")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
