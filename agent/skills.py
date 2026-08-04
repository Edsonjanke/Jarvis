"""skills.py — THINGS YOU TAUGHT IT, IN FILES.

A skill is a markdown file with a name, a description and instructions. When a
question matches the description, the instructions go into the system prompt.
That is the whole mechanism.

WHY IT IS A FOLDER OF FILES. Because that makes sharing free. Copy skills/ to
your other machine, or commit it, and JARVIS there knows what JARVIS here
knows. No account, no server, no export format to maintain — the same reason
memory/ and history/ live in the repository rather than in state_dir().

WHAT IT IS FOR. The vault holds what is true; a skill holds how you work. That
the PARINOX invoice is R$ 6.226,95 belongs in a note. That you chase overdue
suppliers in a particular order, or that a quote of yours always states weight
and material, is not in any document — it is in your head, and until now it
was retyped into every question.

    skills/cobranca.md            or   skills/cobranca/SKILL.md
    ---
    name: Cobrança
    description: cobrar fornecedor atrasado, boleto vencido, negociar prazo
    ---
    Sempre confira o borderô antes de cobrar. …

`description` is what gets matched, so write it as the words you would use in
the question, not as a summary. `always: true` puts a skill in every prompt —
use it for standing rules, not for knowledge.

THE BUDGET IS THE POINT. Three skills, capped in length, exactly like MAX_NOTES
caps the notes. A prompt with everything you ever wrote in it answers worse
than one with the right three, and it costs more.

Run it directly to see what is loaded:  python -m agent.skills
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # allow `python agent/skills.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod
from agent.vault import _fold, _split_frontmatter

MAX_SKILLS = 3          # in one prompt, for the same reason MAX_NOTES exists
SKILL_CHARS = 4_000     # per skill
MIN_OVERLAP = 1         # matching words needed before a skill is offered

_PUNCT_RE = re.compile(r"[^0-9a-z_]+")


@dataclass
class Skill:
    name: str
    description: str
    body: str
    path: Path
    always: bool = False
    problem: str = ""

    @property
    def slug(self) -> str:
        return self.path.stem if self.path.stem != "SKILL" else self.path.parent.name

    def to_dict(self) -> dict[str, object]:
        return {
            "slug": self.slug, "name": self.name, "description": self.description,
            "always": self.always, "chars": len(self.body),
            "path": str(self.path), "problem": self.problem,
        }


def root() -> Path:
    path = data_mod.ROOT / "skills"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _files() -> list[Path]:
    base = root()
    try:
        flat = sorted(p for p in base.glob("*.md") if p.is_file())
        nested = sorted(p for p in base.glob("*/SKILL.md") if p.is_file())
    except OSError:
        return []
    return flat + nested


def load() -> list[Skill]:
    """Every skill on disk, broken ones included.

    A skill that cannot be used still comes back, carrying the reason. Dropping
    it silently is the failure mode that matters here: you wrote a file, you
    expect it to be in effect, and nothing tells you it is not.
    """
    out: list[Skill] = []
    for path in _files():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            out.append(Skill("", "", "", path, problem=f"não deu pra ler: {exc}"))
            continue

        meta, body = _split_frontmatter(text)
        name = str(meta.get("name") or "").strip() or path.stem
        description = str(meta.get("description") or "").strip()
        always = str(meta.get("always") or "").strip().lower() in ("true", "yes", "1", "sim")

        problem = ""
        if not description and not always:
            problem = ("sem 'description' no frontmatter — nada pra casar com a "
                       "pergunta, então ela nunca é escolhida")
        elif not body.strip():
            problem = "sem instruções abaixo do frontmatter"

        out.append(Skill(name=name, description=description, body=body.strip(),
                         path=path, always=always, problem=problem))
    return out


def _words(text: str) -> set[str]:
    """Words, accent-folded, with punctuation gone.

    Punctuation has to go or a question mark decides everything: "cobranca?"
    is not "cobranca", and the skill you wrote silently never fires.
    """
    return {w for w in _PUNCT_RE.sub(" ", _fold(text)).split() if len(w) > 2}


def relevant(question: str, limit: int = MAX_SKILLS) -> list[Skill]:
    """The skills worth putting in this prompt, best match first.

    Matching is word overlap against the description, accent-folded so
    "cobranca" finds "cobrança". Deliberately blunt: a skill you wrote is
    something you want found, and a clever scorer that silently drops it is
    worse than an extra one that was not needed.
    """
    asked = _words(question)
    always: list[Skill] = []
    scored: list[tuple[int, str, Skill]] = []

    for skill in load():
        if skill.problem and not skill.always:
            continue
        if skill.always:
            always.append(skill)
            continue
        if not skill.body:
            continue
        overlap = len(asked & _words(f"{skill.name} {skill.description}"))
        if overlap >= MIN_OVERLAP:
            scored.append((-overlap, skill.name.lower(), skill))

    scored.sort(key=lambda row: (row[0], row[1]))
    return (always + [s for _, _, s in scored])[:limit]


def block(question: str) -> tuple[str, list[str]]:
    """The prompt section, and the names of the skills in it."""
    chosen = relevant(question)
    if not chosen:
        return "", []
    parts, names = [], []
    for skill in chosen:
        body = skill.body
        if len(body) > SKILL_CHARS:
            body = body[:SKILL_CHARS].rsplit(" ", 1)[0] + " …(truncado)"
        parts.append(f"## {skill.name}\n{body}")
        names.append(skill.name)
    return "\n\n".join(parts), names


# ---------------------------------------------------------------------------
# Standing instructions
# ---------------------------------------------------------------------------

INSTRUCTIONS_FILE = "JARVIS.md"
INSTRUCTIONS_CHARS = 6_000


def instructions() -> tuple[str, list[str]]:
    """JARVIS.md from the project and from each vault root, and where from.

    The vault's own copy comes second, so it can add to the project-wide one
    rather than being buried by it. Capped, because a standing instruction is
    in every single prompt and an unbounded one would quietly eat the budget
    that the notes need.
    """
    seen: list[str] = []
    parts: list[str] = []

    candidates = [data_mod.ROOT / INSTRUCTIONS_FILE]
    try:
        candidates += [r.path / INSTRUCTIONS_FILE for r in data_mod.vault_sources().roots]
    except Exception:  # noqa: BLE001 — instructions must never break answering
        pass

    for path in candidates:
        try:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not text or str(path) in seen:
            continue
        if len(text) > INSTRUCTIONS_CHARS:
            text = text[:INSTRUCTIONS_CHARS].rsplit(" ", 1)[0] + " …(truncado)"
        parts.append(text)
        seen.append(str(path))

    return "\n\n".join(parts), seen


def state() -> dict[str, object]:
    """What the panel shows."""
    loaded = load()
    where, sources = instructions()
    return {
        "skills": [s.to_dict() for s in loaded],
        "where": str(root()),
        "problems": [f"{s.slug}: {s.problem}" for s in loaded if s.problem],
        "instructions": {"chars": len(where), "sources": sources,
                         "file": INSTRUCTIONS_FILE},
        "limit": MAX_SKILLS,
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    info = state()
    print(f"\n  habilidades  {info['where']}")
    if not info["skills"]:
        print("\n  (nenhuma ainda)\n")
        print("  Crie skills/cobranca.md com:\n")
        print("    ---\n    name: Cobrança")
        print("    description: cobrar fornecedor atrasado, boleto vencido, prazo")
        print("    ---\n    Sempre confira o borderô antes de cobrar.\n")
    for skill in info["skills"]:
        mark = "sempre" if skill["always"] else ("  !  " if skill["problem"] else "     ")
        print(f"   {mark} {skill['name'][:26]:<28} {skill['chars']:>5} chars  {skill['description'][:44]}")
        if skill["problem"]:
            print(f"         {skill['problem']}")

    ins = info["instructions"]
    print(f"\n  instruções   {ins['chars']} chars de {len(ins['sources'])} arquivo(s)")
    for src in ins["sources"]:
        print(f"      {src}")
    if not ins["sources"]:
        print(f"      (nenhum {INSTRUCTIONS_FILE} — crie um na raiz do projeto ou do vault)")

    query = " ".join(sys.argv[1:])
    if query:
        _, names = block(query)
        print(f"\n  para {query!r}: {names or 'nenhuma habilidade casou'}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
