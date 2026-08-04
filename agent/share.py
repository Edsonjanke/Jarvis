"""share.py — taking it to your other machine.

Most of this is already done and needed no code: skills/, memory/ and history/
are plain files in the repository, so syncing the folder — git, a stick,
OneDrive — already carries everything across. That was the whole reason for
putting them there instead of in state_dir().

What needs code is a SLICE. Everything is usually not what you want to hand
over, and one reason dominates:

    Your history contains your bank statements.

An answer about accounts payable quotes accounts payable. An answer about
"Gastos pessoais e pro labore" quotes that. Handing someone your history is
handing them your finances, and the difference between that and handing over
a couple of skills is worth a command that makes you choose.

So the default here is skills only, and history is opt-in with a count of what
is going and a line saying what is in it.

    python -m agent.share                        what would go, and how much
    python -m agent.share out/                   skills + instructions
    python -m agent.share out/ --history         and the whole history
    python -m agent.share out/ --history=cobranca   only turns matching a word

Importing is copying the folders back. There is no format to learn: what comes
out is the same markdown and jsonl that went in, which is also what makes it
reviewable before you send it.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python agent/share.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod, notebook, skills

README = """# JARVIS — pacote

Copie as pastas para dentro de um JARVIS:

    skills/     -> skills/       habilidades
    history/    -> history/      conversas (se vieram)
    JARVIS.md   -> JARVIS.md     instruções permanentes (se veio)

Não há formato pra aprender: é o mesmo markdown e o mesmo jsonl que o JARVIS
lê. Dá pra abrir e conferir antes de mandar pra alguém — o que é exatamente
o ponto, porque o histórico cita as suas notas de volta.
"""


def plan(history: str | None = None) -> dict[str, object]:
    """What would go, without writing anything."""
    loaded = skills.load()
    _, sources = skills.instructions()
    turns = (notebook.turns(limit=10_000, query=history or "")
             if history is not None else [])
    return {
        "skills": [s.slug for s in loaded],
        "broken": [s.slug for s in loaded if s.problem],
        "instructions": sources,
        "turns": len(turns),
        "history_filter": history,
    }


def export(target: str | Path, history: str | None = None) -> dict[str, object]:
    """Write the slice. Returns what was written.

    `history=None` means no history at all. `history=""` means all of it;
    anything else filters, using the same search the panel uses.
    """
    out = Path(target).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    written: dict[str, object] = {"where": str(out), "skills": [], "turns": 0,
                                  "instructions": []}

    # Skills, as files. A broken one goes too — it is yours, and the other
    # machine will report the same problem rather than pretend it is fine.
    src = skills.root()
    if src.is_dir():
        dest = out / "skills"
        dest.mkdir(exist_ok=True)
        for skill in skills.load():
            path = Path(skill.path)
            try:
                if path.parent != src:                # skills/<name>/SKILL.md
                    shutil.copytree(path.parent, dest / path.parent.name,
                                    dirs_exist_ok=True)
                else:
                    shutil.copy2(path, dest / path.name)
            except OSError as exc:
                print(f"  não copiei {path.name}: {exc}", file=sys.stderr)
                continue
            written["skills"].append(skill.slug)

    text, sources = skills.instructions()
    if text:
        try:
            (out / skills.INSTRUCTIONS_FILE).write_text(text, encoding="utf-8")
            written["instructions"] = sources
        except OSError as exc:
            print(f"  não escrevi {skills.INSTRUCTIONS_FILE}: {exc}", file=sys.stderr)

    if history is not None:
        turns = notebook.turns(limit=10_000, query=history)
        dest = out / "history"
        dest.mkdir(exist_ok=True)
        try:
            with (dest / "exported.jsonl").open("w", encoding="utf-8") as handle:
                for turn in reversed(turns):          # oldest first, reading order
                    handle.write(json.dumps(turn.to_dict(), ensure_ascii=False) + "\n")
            written["turns"] = len(turns)
        except OSError as exc:
            print(f"  não escrevi o histórico: {exc}", file=sys.stderr)

    try:
        (out / "LEIA-ME.md").write_text(README, encoding="utf-8")
    except OSError:
        pass
    return written


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    args = [a for a in sys.argv[1:]]
    history: str | None = None
    target = ""
    for arg in args:
        if arg == "--history":
            history = ""
        elif arg.startswith("--history="):
            history = arg.split("=", 1)[1]
        elif not arg.startswith("-"):
            target = arg

    if not target:
        info = plan(history)
        print(f"\n  habilidades  {len(info['skills'])}"
              + (f"  ({len(info['broken'])} com problema, vão assim mesmo)"
                 if info["broken"] else ""))
        for slug in info["skills"]:
            print(f"      {slug}")
        print(f"  instruções   {len(info['instructions'])} arquivo(s)")
        print(f"  histórico    {'não vai (use --history)' if history is None else info['turns']}")
        print(f"\n  uso:  python -m agent.share <pasta> [--history[=filtro]]")
        print(f"\n  O histórico cita as suas notas de volta — extrato bancário e")
        print(f"  pró-labore inclusive. Por isso ele não vai por padrão.\n")
        return 0

    written = export(target, history)
    print(f"\n  escrito em   {written['where']}")
    print(f"  habilidades  {len(written['skills'])}: {', '.join(written['skills']) or '—'}")
    print(f"  instruções   {len(written['instructions'])} arquivo(s)")
    print(f"  histórico    {written['turns']} turnos")
    if written["turns"]:
        print(f"\n  ATENÇÃO: {written['turns']} turnos vão junto, e uma resposta sobre")
        print(f"  as suas contas contém as suas contas. Abra e confira antes de mandar.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
