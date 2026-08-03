"""memory.py — THE ONLY FILE THAT WRITES ANYTHING.

data.py declares the policy — WRITEABLE_ROOTS = (MEMORY_DIR,) — and says it is
enforced here. This is that enforcement. Every write in JARVIS goes through
_path_for(), which builds the filename itself and then proves the result is
inside memory/ before opening it.

That matters more here than anywhere else in the project, because the content
being stored is chosen by the model. A fact is a string that came out of a
language model that just read the user's private notes, so:

  * the model never names a file — the name is derived from a slug we compute,
    so there is no traversal to defend against in the first place
  * a fact is capped, the total is capped, and near-duplicates are dropped, so
    an enthusiastic run cannot fill the disk or bury the useful ones
  * nothing is hidden: everything written is listed in the UI with a delete
    button, and the files are plain markdown you can read and edit yourself

Remembered facts are personal, which is why .gitignore excludes memory/*.md.
Delete that line if you would rather version them.

Run it directly to see what is remembered:  python -m agent.memory
"""

from __future__ import annotations

import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # allow `python agent/memory.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod, llm

# Bounds. A fact is a sentence, not an essay, and a memory that has grown to
# thousands of entries has stopped being memory and become another vault.
MAX_FACT_CHARS = 500
MAX_FACTS = 300
RECALL_LIMIT = 12          # how many can reach a prompt at once
RECENT_ALWAYS = 3          # the newest few are always worth seeing

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_STAMP_RE = re.compile(r"^recorded:\s*(.+)$", re.MULTILINE)
# A list marker, and only when it is genuinely one: the space after it is what
# separates "1. " from "50%" and "2026".
_BULLET_RE = re.compile(r"^\s*(?:[-*•–—]|\d{1,2}[.)])\s+")


@dataclass(frozen=True)
class Fact:
    name: str
    text: str
    recorded: float
    path: Path

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "text": self.text, "recorded": self.recorded}


# ---------------------------------------------------------------------------
# The only writable path in the program
# ---------------------------------------------------------------------------

def _root() -> Path:
    root = data_mod.MEMORY_DIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slug(text: str) -> str:
    folded = unicodedata.normalize("NFD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    slug = _SLUG_RE.sub("-", folded).strip("-")[:60].strip("-")
    return slug or "fact"


def _path_for(slug: str) -> Path:
    """A file inside memory/, or a refusal.

    The slug is ours, not the model's, so this cannot normally escape — which
    is exactly why the check is here: the guarantee should hold even if the
    slug ever comes from somewhere less careful.
    """
    root = _root().resolve()
    candidate = (root / f"{slug}.md").resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ValueError(f"refusing to write outside {root}") from None
    if candidate.name in ("", ".md"):
        raise ValueError("empty filename")
    return candidate


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def facts() -> list[Fact]:
    """Everything remembered, newest first."""
    out: list[Fact] = []
    root = _root()
    for path in sorted(root.glob("*.md")):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        stamp = _STAMP_RE.search(raw)
        try:
            recorded = float(stamp.group(1)) if stamp else path.stat().st_mtime
        except (ValueError, OSError):
            recorded = 0.0
        body = raw.split("---", 2)[-1].strip() if raw.startswith("---") else raw.strip()
        if body:
            out.append(Fact(path.stem, body, recorded, path))
    out.sort(key=lambda f: -f.recorded)
    return out


def _tokens(text: str) -> set[str]:
    folded = unicodedata.normalize("NFD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return {t for t in re.findall(r"[a-z0-9]{3,}", folded)}


def relevant(query: str, limit: int = RECALL_LIMIT) -> list[Fact]:
    """The facts worth putting in front of this question.

    Deliberately simple word overlap. Memory is small — hundreds of short
    lines, not a corpus — so BM25 would be machinery without a purpose, and the
    newest few are included regardless because "what did we just decide" is the
    most common thing to want back.
    """
    everything = facts()
    if not everything:
        return []

    wanted = _tokens(query)
    scored = sorted(
        everything,
        key=lambda f: (-len(wanted & _tokens(f.text)), -f.recorded),
    )
    chosen: dict[str, Fact] = {f.name: f for f in everything[:RECENT_ALWAYS]}
    for fact in scored:
        if len(chosen) >= limit:
            break
        if wanted & _tokens(fact.text):
            chosen.setdefault(fact.name, fact)
    return sorted(chosen.values(), key=lambda f: -f.recorded)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _is_duplicate(text: str, existing: list[Fact]) -> bool:
    """Near-enough to something already known that writing it adds nothing."""
    new = _tokens(text)
    if not new:
        return True
    for fact in existing:
        old = _tokens(fact.text)
        if not old:
            continue
        overlap = len(new & old) / max(len(new), len(old))
        if overlap >= 0.8:
            return True
    return False


def remember(text: str, *, source: str = "ask") -> Fact | None:
    """Write one fact. Returns it, or None when it was not worth keeping."""
    text = " ".join(str(text or "").split())
    if len(text) < 8:
        return None
    if len(text) > MAX_FACT_CHARS:
        text = text[:MAX_FACT_CHARS].rsplit(" ", 1)[0] + "…"

    existing = facts()
    if len(existing) >= MAX_FACTS:
        return None
    if _is_duplicate(text, existing):
        return None

    slug = _slug(text)
    path = _path_for(slug)
    n = 2
    while path.exists():
        path = _path_for(f"{slug}-{n}")
        n += 1

    recorded = time.time()
    path.write_text(
        f"---\nname: {path.stem}\nrecorded: {recorded}\nsource: {source}\n---\n\n{text}\n",
        encoding="utf-8",
    )
    return Fact(path.stem, text, recorded, path)


def forget(name: str) -> bool:
    """Delete one fact by the name shown in the panel. Returns whether it was there.

    Resolved by matching what facts() actually lists, never by re-deriving a
    slug from the name. _slug truncates at 60 characters, so re-slugging a
    disambiguated "…-2" name lands back on the original file: clicking Forget
    on the second of two similar facts would delete the first, report success,
    and leave the row you clicked sitting there.

    Matching the listing also means a file you wrote by hand can be deleted
    from the panel, which re-slugging could not do, and containment comes for
    free — facts() only ever globs inside memory/.
    """
    for fact in facts():
        if fact.name == name:
            try:
                fact.path.unlink()
            except OSError:
                return False
            return True
    return False


# ---------------------------------------------------------------------------
# Deciding what is worth remembering
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """\
You read one exchange between a person and their own notes, and pull out only \
what is worth still knowing next month.

You have no tools. Reply with nothing but the facts, one per line, no bullets, \
no numbering, no preamble. If nothing qualifies — and that is the common case \
— reply with exactly: NOTHING

What qualifies:
  * a decision the person made, and why
  * a standing preference, rule or constraint they stated
  * a correction they made to something that was wrong
  * a durable fact about their work that the notes do not already say

What does not, ever:
  * anything already written in the notes — those are already searchable
  * what was asked, or that a question was asked
  * the answer's content, summarised
  * anything true only today: figures, counts, statuses, amounts outstanding
  * speculation, or anything you inferred rather than were told

Each line must stand alone, in {language}, under 40 words, and be understandable \
a year from now with no other context. Prefer none over a weak one."""


def extract(question: str, answer: str) -> list[str]:
    """Ask the model what, if anything, is worth keeping from an exchange.

    Runs at low effort: this is a filter, not a reasoning task, and it happens
    once per question on top of the question itself.
    """
    lang = data_mod.language()
    system = _EXTRACT_SYSTEM.format(
        language=lang if lang else "the language of the exchange"
    )
    text, _ = llm.complete(
        system,
        f"THEY ASKED\n\n{question}\n\nTHE ANSWER GIVEN\n\n{answer}",
        effort="low",
    )
    if text.strip().upper().startswith("NOTHING"):
        return []
    # Anchored, and only when a marker is followed by space. str.lstrip takes a
    # character *set*, so stripping "-*•0123456789. " ate the leading digits of
    # exactly the facts most worth keeping: "50% é o novo depósito" became
    # "% é o novo depósito", and "2026 é o ano da renovação" lost its year.
    lines = [_BULLET_RE.sub("", " ".join(line.split())).strip()
             for line in text.splitlines()]
    return [line for line in lines if len(line) >= 8][:5]


def learn(question: str, answer: str) -> list[Fact]:
    """Extract and store. Any failure here is silent by design.

    Remembering is a side effect of answering. If the model is busy, rate
    limited or simply unhelpful, the person still got their answer, and a
    failure to record a fact is not worth an alert.
    """
    try:
        candidates = extract(question, answer)
    except (llm.LLMUnavailable, llm.LLMFailed):
        return []
    kept = []
    for line in candidates:
        try:
            fact = remember(line)
        except (OSError, ValueError):
            continue
        if fact:
            kept.append(fact)
    return kept


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    stored = facts()
    print(f"\n  memory   {_root()}")
    print(f"  facts    {len(stored)} of {MAX_FACTS}\n")
    for fact in stored:
        when = time.strftime("%Y-%m-%d", time.localtime(fact.recorded))
        print(f"    {when}  {fact.text}")
    if not stored:
        print("    (nothing yet — it fills as you ask things)")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
