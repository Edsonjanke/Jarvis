"""edit.py — THE ONLY FILE THAT WRITES TO YOUR VAULT.

Same rule as memory.py owning memory/ and notebook.py owning history/. This one
is different in kind, though, and it is worth being blunt about why.

Everything else JARVIS writes, it owns. This writes to files you made, that it
did not create and cannot recreate. The Evo-SI audit in your own vault says
there is no backup of anything — "hoje não existe NENHUMA cópia dos dados fora
da Neon". So a mistake here is not recoverable from anywhere else, and the undo
journal below is not belt-and-braces. It is the backup.

THREE RULES, AND THEY ARE THE WHOLE FILE.

  1. Nothing is written outside a configured vault root. The path is resolved
     and proven to be inside one, every time. A junction that moved since
     indexing is caught here, not trusted.

  2. Nothing is overwritten or deleted without a copy kept first. write() and
     remove() both journal the previous bytes before touching anything, and
     undo() puts them back byte for byte. A write whose backup fails does not
     happen.

  3. Deleting always asks, in every mode. Cowork does the same, and it is right:
     an overwrite you did not want is recoverable from the journal, but the
     journal is the thing that makes it so — and a person who has stopped
     reading prompts should still be stopped by this one.

MODES, as Cowork has them, stored like the tool allowlist:

    manual  (default)  every operation is proposed and waits for you
    auto               writes go through; deletes still ask
    skip               writes go through; deletes still ask

`skip` is not "no questions asked" here, and that is a deliberate difference.

Run it directly to see what has been changed and undo it:
    python -m agent.edit
    python -m agent.edit undo <id>
"""

from __future__ import annotations

import json
import shutil
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):  # allow `python agent/edit.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod

MODE_FILE = "edit-mode.txt"
JOURNAL = "undo/journal.jsonl"
MODES = ("manual", "auto", "skip")
DEFAULT_MODE = "manual"

# A note, not a disk image. Anything larger is a mistake, and journaling it
# would quietly fill the drive the vault lives on.
MAX_WRITE_BYTES = 4 * 1024 * 1024

# What may be written. Deliberately narrower than what the vault indexes: a
# .pdf is not something to regenerate from a language model.
WRITEABLE_SUFFIXES = {".md", ".markdown", ".txt", ".text"}


class Refused(Exception):
    """The operation was not allowed. Never a bug — always a rule."""


@dataclass
class Change:
    id: str
    when: float
    action: str            # write | remove
    path: str
    backup: str            # "" when the file did not exist before
    size_before: int
    size_after: int
    note: str = ""
    undone: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id, "when": self.when, "action": self.action,
            "path": self.path, "had_backup": bool(self.backup),
            "size_before": self.size_before, "size_after": self.size_after,
            "note": self.note, "undone": self.undone,
        }


# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------

def mode() -> str:
    try:
        raw = (data_mod.state_dir() / MODE_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT_MODE
    return raw if raw in MODES else DEFAULT_MODE


def set_mode(value: str) -> str:
    if value not in MODES:
        raise Refused(f"modo desconhecido: {value!r} — use {', '.join(MODES)}")
    (data_mod.state_dir() / MODE_FILE).write_text(value, encoding="utf-8")
    return value


# ---------------------------------------------------------------------------
# Containment — rule 1
# ---------------------------------------------------------------------------

def _roots() -> list[Path]:
    return [r.path.resolve() for r in data_mod.vault_sources().roots]


def resolve(raw: str) -> Path:
    """A path inside the vault, or a refusal.

    Everything about this is deliberately unclever. It resolves first and
    judges after, so a symlink, a junction or a `..` that survived string
    handling is caught by where it actually lands rather than by how it looks.
    """
    text = (raw or "").strip().strip('"')
    if not text:
        raise Refused("nenhum caminho")

    roots = _roots()
    if not roots:
        raise Refused("nenhuma pasta configurada — nada pra escrever dentro")

    candidate = Path(text)
    if not candidate.is_absolute():
        # A relative path is relative to the first root, never to the process
        # working directory, which is somewhere else entirely.
        candidate = roots[0] / candidate

    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise Refused(f"caminho impossível de resolver: {exc}") from None

    if not any(resolved == root or root in resolved.parents for root in roots):
        raise Refused(f"fora do vault: {resolved}")

    if resolved.suffix.lower() not in WRITEABLE_SUFFIXES:
        raise Refused(
            f"{resolved.suffix or '(sem extensão)'} não é um tipo que o JARVIS "
            f"escreve — só {', '.join(sorted(WRITEABLE_SUFFIXES))}"
        )
    return resolved


# ---------------------------------------------------------------------------
# The journal — rule 2
# ---------------------------------------------------------------------------

def _undo_dir() -> Path:
    path = data_mod.state_dir() / "undo"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _journal_path() -> Path:
    _undo_dir()
    return data_mod.state_dir() / JOURNAL


def _keep(path: Path, change_id: str) -> str:
    """Copy the current bytes aside. Returns the backup name, or "" if new.

    Raises if the copy fails. That is the point: a write whose previous state
    could not be saved does not happen at all.
    """
    if not path.exists():
        return ""
    name = f"{change_id}-{path.name}"
    target = _undo_dir() / name
    try:
        shutil.copy2(path, target)
    except OSError as exc:
        raise Refused(f"não consegui guardar a cópia de segurança: {exc}") from None
    return name


def _log(change: Change) -> None:
    try:
        with _journal_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(change.to_dict() | {"backup": change.backup},
                                    ensure_ascii=False) + "\n")
    except OSError as exc:
        # The bytes are already saved; losing the log entry loses the ability
        # to find them from the UI, which is bad enough to say out loud.
        print(f"  undo journal not written: {exc}", file=sys.stderr)


def changes(limit: int = 100) -> list[Change]:
    """What has been changed, newest first."""
    out: list[Change] = []
    try:
        text = _journal_path().read_text(encoding="utf-8")
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
        out.append(Change(
            id=str(raw.get("id") or ""), when=float(raw.get("when") or 0),
            action=str(raw.get("action") or ""), path=str(raw.get("path") or ""),
            backup=str(raw.get("backup") or ""),
            size_before=int(raw.get("size_before") or 0),
            size_after=int(raw.get("size_after") or 0),
            note=str(raw.get("note") or ""), undone=bool(raw.get("undone")),
        ))
    out.reverse()
    return out[:limit]


def _mark_undone(change_id: str) -> None:
    try:
        path = _journal_path()
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    out = []
    for line in lines:
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        if raw.get("id") == change_id:
            raw["undone"] = True
        out.append(json.dumps(raw, ensure_ascii=False))
    try:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def write(raw_path: str, content: str, *, note: str = "") -> Change:
    """Create or replace one file inside the vault, keeping what was there."""
    path = resolve(raw_path)
    data = (content or "").encode("utf-8")
    if len(data) > MAX_WRITE_BYTES:
        raise Refused(f"conteúdo acima do teto de {MAX_WRITE_BYTES // 1024 // 1024} MB")

    change_id = uuid.uuid4().hex[:12]
    before = path.stat().st_size if path.exists() else 0
    backup = _keep(path, change_id)         # raises rather than write blind

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError as exc:
        raise Refused(f"não deu pra escrever: {exc}") from None

    change = Change(id=change_id, when=time.time(), action="write",
                    path=str(path), backup=backup, size_before=before,
                    size_after=len(data), note=note)
    _log(change)
    return change


def remove(raw_path: str, *, confirm: bool = False, note: str = "") -> Change:
    """Delete one file inside the vault. Asks in every mode.

    `confirm` is not a formality and no mode waives it. An overwrite is
    recoverable because the journal exists; this is the operation that would
    make you need the journal, so it gets the one hard stop in the file.
    """
    if not confirm:
        raise Refused("apagar exige confirmação explícita, em qualquer modo")

    path = resolve(raw_path)
    if not path.exists():
        raise Refused(f"não existe: {path}")

    change_id = uuid.uuid4().hex[:12]
    before = path.stat().st_size
    backup = _keep(path, change_id)
    try:
        path.unlink()
    except OSError as exc:
        raise Refused(f"não deu pra apagar: {exc}") from None

    change = Change(id=change_id, when=time.time(), action="remove",
                    path=str(path), backup=backup, size_before=before,
                    size_after=0, note=note)
    _log(change)
    return change


def undo(change_id: str) -> Change:
    """Put a file back exactly as it was."""
    for change in changes(limit=10_000):
        if change.id != change_id:
            continue
        if change.undone:
            raise Refused("essa mudança já foi desfeita")

        path = Path(change.path)
        # Where it goes must still be inside the vault — the configuration
        # could have changed since, and undo must not become a way out.
        try:
            resolve(str(path))
        except Refused as exc:
            raise Refused(f"não dá pra desfazer aqui: {exc}") from None

        if change.backup:
            source = _undo_dir() / change.backup
            if not source.exists():
                raise Refused(f"a cópia de segurança sumiu: {source}")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, path)
            except OSError as exc:
                raise Refused(f"não deu pra restaurar: {exc}") from None
        else:
            # There was no file before, so undoing means there is none now.
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                raise Refused(f"não deu pra remover: {exc}") from None

        _mark_undone(change_id)
        change.undone = True
        return change
    raise Refused(f"mudança desconhecida: {change_id!r}")


def state() -> dict[str, object]:
    return {
        "mode": mode(),
        "modes": list(MODES),
        "changes": [c.to_dict() for c in changes(limit=50)],
        "roots": [str(r) for r in _roots()],
        "writeable": sorted(WRITEABLE_SUFFIXES),
        "undo_dir": str(_undo_dir()),
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    args = sys.argv[1:]
    if args and args[0] == "undo":
        if len(args) < 2:
            print("  uso: python -m agent.edit undo <id>")
            return 1
        try:
            change = undo(args[1])
        except Refused as exc:
            print(f"  recusado: {exc}")
            return 1
        print(f"  desfeito: {change.path}")
        return 0

    info = state()
    print(f"\n  modo        {info['mode']}   (de: {', '.join(info['modes'])})")
    print(f"  escreve em  {', '.join(info['roots']) or '(nenhuma pasta configurada)'}")
    print(f"  tipos       {', '.join(info['writeable'])}")
    print(f"  cópias em   {info['undo_dir']}\n")
    if not info["changes"]:
        print("  nada alterado ainda.\n")
        return 0
    for change in info["changes"]:
        when = time.strftime("%d/%m %H:%M", time.localtime(change["when"]))
        mark = "desfeito" if change["undone"] else change["action"]
        print(f"  {when}  {mark:<8} {change['path']}")
        print(f"            {change['size_before']} -> {change['size_after']} bytes"
              f"   desfazer: python -m agent.edit undo {change['id']}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
