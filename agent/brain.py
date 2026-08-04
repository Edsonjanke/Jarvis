"""brain.py — the vault becomes an answer.

Retrieval, prompt, citation check. No HTTP here and no `anthropic` import: it
takes a Vault, calls llm.complete, and hands back text plus the note ids that
back it up.

Retrieval is BM25 (vault.search) *widened along the graph*. That is the whole
argument for this project over a generic RAG: the links are already resolved,
so a question that names one note can pull in the client it belongs to and the
invoices that point at it without any of those words appearing in the query.

Citations are extracted by scanning the answer for ids that exist in the index,
never by trusting the model's formatting. An id it invented does not match a
real note, so it does not become a clickable citation.

Run it directly to ask from the terminal:  python -m agent.brain "your question"
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # allow `python agent/brain.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod, embed, llm, memory, notebook
from agent.vault import Note, Vault

# ---------------------------------------------------------------------------
# Budgets. Generous enough to answer, small enough not to send the vault.
# ---------------------------------------------------------------------------

SEED_HITS = 8            # BM25 matches before the graph widens the net
THIN = 3                 # below this, the words missed and it is worth asking again
NEIGHBOURS_PER_HIT = 3   # linked notes pulled in per match
MAX_NOTES = 16           # hard cap on what reaches the prompt
NOTE_CHARS = 2_400       # per-note text budget
CONTEXT_CHARS = 48_000   # total, roughly 12k tokens

RECENT_FOR_BRIEF = 12
HUBS_FOR_BRIEF = 6

_WS_RE = re.compile(r"\s+")


@dataclass
class Answer:
    """One reply, plus everything needed to audit it."""

    kind: str
    question: str
    text: str
    citations: list[tuple[str, str, str]]   # (note id, title, type)
    considered: list[str]
    recalled: list[str]                     # remembered facts put in the prompt
    usage: dict[str, object]
    seconds: float

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "question": self.question,
            "answer": self.text,
            "citations": [
                {"id": nid, "title": title, "type": note_type}
                for nid, title, note_type in self.citations
            ],
            "considered": self.considered,
            "recalled": self.recalled,
            "usage": self.usage,
            "seconds": round(self.seconds, 2),
        }


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

_EXPAND_SYSTEM = """\
You are given one question someone is asking of their own notes. Reply with the \
words those notes would most likely actually contain on that subject.

You have no tools. Reply with nothing but the words, comma separated, on one \
line. No explanation, no numbering, no quotes.

Give both the question's own language and English, because notes are often \
written in a different language from the question — "atraso" should also \
produce "outstanding, overdue, unpaid, late". Prefer the plain nouns and verbs \
a note would use over abstract ones. Ten words at most, fewer is better."""


def expand(query: str) -> list[str]:
    """Other words the notes might use for the same thing.

    BM25 only finds words that are there. Folding accents made "depósito"
    reach a note saying "deposit", because a fold is still the same word — it
    does nothing for "atraso" against notes that say "outstanding", which
    returned nothing at all. This is the cheap half of closing that; embed.py
    is the thorough half.

    Failure is silent: an expansion that does not happen leaves the ordinary
    word search exactly as it was.
    """
    try:
        text, _ = llm.complete(_EXPAND_SYSTEM, query, effort="low")
    except (llm.LLMUnavailable, llm.LLMFailed):
        return []
    words = [w.strip(" .,;:\"'") for w in text.replace("\n", ",").split(",")]
    seen: dict[str, None] = {}
    for word in words:
        if 2 < len(word) < 40:
            seen.setdefault(word.lower(), None)
    return list(seen)[:10]


def retrieve(vault: Vault, query: str, *, limit: int = SEED_HITS) -> list[Note]:
    """Words, then other words, then meaning — and then the link graph.

    Seeds keep their rank; neighbours follow, best-connected first. Order is
    the order the model reads them in, so it matters.
    """
    chosen: dict[str, Note] = {}

    # 1. The words that are actually there. Free, and usually enough.
    for hit in vault.search(query, limit=limit):
        chosen.setdefault(hit.note.id, hit.note)

    # 2. Only when that came back thin — a question whose vocabulary simply
    #    does not appear in the notes, which is the normal case for a question
    #    asked in one language about notes written in another.
    if len(chosen) < THIN:
        for word in expand(query):
            for hit in vault.search(word, limit=3):
                chosen.setdefault(hit.note.id, hit.note)

    # 3. Meaning, when Ollama is there to supply it. A no-op otherwise, and
    #    the two above have already done their work either way.
    for note_id in embed.similar(vault, query):
        note = vault.notes.get(note_id)
        if note is not None:
            chosen.setdefault(note_id, note)

    for note in list(chosen.values()):
        neighbours = sorted(
            (vault.notes[nid] for nid in (note.out | note.back) if nid in vault.notes),
            key=lambda n: (-n.degree, n.title.lower()),
        )
        for other in neighbours[:NEIGHBOURS_PER_HIT]:
            if len(chosen) >= MAX_NOTES:
                break
            chosen.setdefault(other.id, other)
        if len(chosen) >= MAX_NOTES:
            break

    return list(chosen.values())[:MAX_NOTES]


def recent(vault: Vault, limit: int = RECENT_FOR_BRIEF) -> list[Note]:
    return sorted(vault.notes.values(), key=lambda n: -n.mtime)[:limit]


def _block(note: Note) -> str:
    """One note as the model sees it. The id leads, so it can be cited."""
    body = _WS_RE.sub(" ", note.text).strip()
    if len(body) > NOTE_CHARS:
        body = body[:NOTE_CHARS].rsplit(" ", 1)[0] + " …(truncated)"
    head = f"[{note.id}] {note.title} — {note.type}"
    if note.tags:
        head += f" — tags: {' '.join(note.tags[:8])}"
    links = sorted(note.out | note.back)
    if links:
        head += f"\nlinks to: {', '.join(links[:8])}"
        if len(links) > 8:
            head += f" (+{len(links) - 8} more)"
    return f"{head}\n{body or '(no text)'}"


def context(notes: list[Note]) -> tuple[str, list[str]]:
    """The notes block, and the ids that actually fitted in it."""
    parts: list[str] = []
    used: list[str] = []
    budget = CONTEXT_CHARS
    for note in notes:
        block = _block(note)
        if len(block) > budget:
            break
        parts.append(block)
        used.append(note.id)
        budget -= len(block)
    return "\n\n---\n\n".join(parts), used


# ---------------------------------------------------------------------------
# Citations — verified against the index, never taken on trust
# ---------------------------------------------------------------------------

def cited(vault: Vault, text: str, considered: list[str]) -> list[tuple[str, str, str]]:
    """Note ids that appear in the answer AND exist in the vault.

    The bracketed form is what the prompt asks for, so look for that first. The
    bare id is only accepted when the model wrote no brackets at all, because
    one id can sit inside another: index two roots where one contains a folder
    named after the other — or, more easily, nest two entries in JARVIS_VAULTS —
    and 'Notes/plan.md' is a substring of 'Vault/Notes/plan.md'. Matching bare
    would then credit a note the model never mentioned, and the UI presents
    every chip as a source the answer stands on.

    Longest first, and each match consumes its span, so a short id cannot be
    found inside a longer one that was already credited.

    Ordered by where they appear, so the chips read in the order they are used.
    """
    def scan(bracketed: bool) -> list[tuple[int, str]]:
        hits: list[tuple[int, str]] = []
        taken: list[tuple[int, int]] = []
        for note_id in sorted(considered, key=len, reverse=True):
            needle = f"[{note_id}]" if bracketed else note_id
            start = 0
            while (at := text.find(needle, start)) != -1:
                end = at + len(needle)
                if not any(a < end and at < b for a, b in taken):
                    taken.append((at, end))
                    hits.append((at, note_id))
                    break
                start = at + 1
        return hits

    found = scan(bracketed=True) or scan(bracketed=False)
    found.sort()
    return [
        (nid, vault.notes[nid].title, vault.notes[nid].type)
        for _, nid in found
        if nid in vault.notes
    ]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_GROUND_RULES = """\
You are JARVIS, reading one person's own notes. You have been given the notes \
most likely to be relevant, each headed by its id in square brackets.

You have no tools. You cannot read files, run commands or search the web, and \
there is no point saying you will — everything you have to work with is below. \
Answer directly from it.

Rules, in order of importance:
1. Answer only from the notes below. If they do not contain the answer, say so \
plainly and name what is missing. Never fill a gap from general knowledge.
2. Cite by writing the exact id in square brackets, e.g. [demo/notes/pricing-ladder.md], \
right after the claim it supports. Only ids that appear below exist; do not \
invent one, and do not reformat one.
3. Be specific. Names, figures and dates from the notes beat a summary of them.
4. {language}
5. No preamble. Open with the answer."""

# The briefing has no question to take a cue from, so without JARVIS_LANG set
# it answers in whatever language the notes happen to be in.
_FOLLOW_QUESTION = "Answer in the language the question is written in."

_ASK_SYSTEM = _GROUND_RULES + """

Keep it to a few short paragraphs unless the question genuinely needs more.

You do keep things between conversations: anything durable the person tells you \
— a decision, a preference, a standing rule — is recorded afterwards and comes \
back to you later under REMEMBERED. So never say you cannot remember something \
or that you have no memory. You are not a store of records and cannot change \
their notes, but what they tell you does carry forward. Do not announce that \
you are remembering; just answer."""

_BRIEF_SYSTEM = _GROUND_RULES + """

You are writing a standing briefing, not answering a question. Cover, in this \
order and only where the notes support it: what changed most recently, what \
looks like it needs a decision or a chase, and the one thing worth attention \
today. Six short bullets at most."""

_PLAN_SYSTEM = _GROUND_RULES + """

You are turning a goal into a plan grounded in these notes. Give numbered \
steps, each one concrete and citing the note it comes from. Where the notes do \
not cover a step, mark it "(not in the vault)" rather than guessing. End with \
the single biggest unknown."""


# ---------------------------------------------------------------------------
# The three calls
# ---------------------------------------------------------------------------

def _run(vault: Vault, kind: str, question: str, system: str,
         notes: list[Note], user: str, thread: str = "") -> Answer:
    started = time.time()
    block, considered = context(notes)
    if not considered:
        raise llm.LLMFailed("nothing in the vault to answer from")

    lang = data_mod.language()
    system = system.format(
        language=f"Answer in {lang}." if lang else _FOLLOW_QUESTION
    )

    # Remembered facts go in their own section, above the notes and clearly not
    # part of them. They have no note id, so they can never be cited — cited()
    # only credits ids that exist in the index, and that stays true.
    prompt = f"{user}\n\nNOTES\n\n{block}"
    recalled = memory.relevant(question)
    if recalled:
        prompt = (
            "REMEMBERED — things you were told in earlier conversations. Not notes, and\n"
            "not citable: they have no id. Use them for context; if one contradicts a\n"
            "note, say so rather than choosing silently.\n\n"
            + "\n".join(f"- {f.text}" for f in recalled)
            + f"\n\n{prompt}"
        )

    # Earlier turns of this same conversation, above everything else, so
    # "and of those, which are PARINOX?" has a "those" to refer to. Like
    # REMEMBERED these carry no note id and therefore cannot be cited — the
    # guarantee that a citation names a real note is unaffected.
    #
    # Above REMEMBERED rather than below: what was just said in this thread is
    # more immediate than something learned weeks ago, and when the two
    # disagree the model should see the recent one in the context of the old,
    # not the reverse.
    earlier = notebook.conversation_block(thread)
    if earlier:
        prompt = (
            "CONVERSATION — what was already asked and answered in this session.\n"
            "Context only: not notes, not citable, and possibly out of date if the\n"
            "vault changed since. A follow-up question refers to this.\n\n"
            + earlier
            + f"\n\n{prompt}"
        )

    text, usage = llm.complete(system, prompt)
    return Answer(
        kind=kind,
        question=question,
        text=text,
        citations=cited(vault, text, considered),
        considered=considered,
        recalled=[f.text for f in recalled],
        usage=usage,
        seconds=time.time() - started,
    )


def ask(vault: Vault, question: str, thread: str = "") -> Answer:
    question = question.strip()
    if not question:
        raise llm.LLMFailed("no question given")

    notes = retrieve(vault, question)
    if notes:
        return _run(vault, "ask", question, _ASK_SYSTEM, notes,
                    f"QUESTION\n\n{question}", thread)

    # Search is lexical, so a question can miss everything — a word the notes
    # never use, or a question in one language about notes in another. Raising
    # here would be a dead end, and a spoken question would just fail. Show the
    # vault's best-connected notes instead and let the answer say, truthfully,
    # that nothing covers it and what is actually in there.
    return _run(
        vault, "ask", question, _ASK_SYSTEM, vault.hubs(HUBS_FOR_BRIEF),
        f"QUESTION\n\n{question}\n\n"
        "Searching the vault for this matched no note at all. The notes below are not "
        "results — they are simply its most connected ones. Say plainly, in one line, that "
        "nothing here answers the question, then say briefly what the vault does cover.",
        thread,
    )


def brief(vault: Vault) -> Answer:
    hubs = vault.hubs(HUBS_FOR_BRIEF)
    notes: dict[str, Note] = {n.id: n for n in recent(vault)}
    for note in hubs:
        notes.setdefault(note.id, note)
    return _run(
        vault, "brief", "brief", _BRIEF_SYSTEM, list(notes.values()),
        "Brief me on this vault. The notes below are the most recently changed, "
        "followed by the most connected.",
    )


def plan(vault: Vault, goal: str) -> Answer:
    goal = goal.strip()
    if not goal:
        raise llm.LLMFailed("no goal given")
    notes: dict[str, Note] = {n.id: n for n in retrieve(vault, goal)}
    for note in vault.hubs(4):
        notes.setdefault(note.id, note)
    return _run(vault, "plan", goal, _PLAN_SYSTEM, list(notes.values()),
                f"GOAL\n\n{goal}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    question = " ".join(sys.argv[1:]).strip()
    vault = Vault.from_config()
    if not vault.notes:
        print("  Nothing indexed — run: python data/generate.py")
        return 1

    try:
        answer = brief(vault) if not question else ask(vault, question)
    except (llm.LLMUnavailable, llm.LLMFailed) as exc:
        print(f"  {exc}")
        return 1

    print(f"\n{answer.text}\n")
    print(f"  cited    {len(answer.citations)} of {len(answer.considered)} notes read")
    for nid, title, note_type in answer.citations:
        print(f"    {title}  ({note_type})  {nid}")
    print(f"  usage    {answer.usage}")
    print(f"  took     {answer.seconds:.1f}s\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
