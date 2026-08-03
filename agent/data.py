"""data.py — THE ONLY FILE THAT TOUCHES REAL DATA.

Every path, key and switch that could point JARVIS at Edson's actual life is
resolved here and nowhere else. `JARVIS_DEMO` is read in this file only; if you
find yourself reaching for os.environ["JARVIS_DEMO"] anywhere else in the
codebase, that is the bug.

Default is demo. You have to opt *in* to your real life.

Nothing in this module writes to a source folder. It hands out paths; vault.py
opens them 'rb' and never anything else.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEMO_VAULT = ROOT / "data" / "demo_vault"
MEMORY_DIR = ROOT / "memory"
ENV_FILE = ROOT / ".env"

# The only place JARVIS is ever allowed to write, other than the runtime's own
# scratch. Enforced in memory.py; declared here because this file owns policy.
WRITEABLE_ROOTS = (MEMORY_DIR,)


# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------

_env_cache: dict[str, str] | None = None


def _load_env() -> dict[str, str]:
    """Parse .env into a dict. Process environment wins over the file."""
    global _env_cache
    if _env_cache is not None:
        return _env_cache

    values: dict[str, str] = {}
    if ENV_FILE.is_file():
        try:
            raw = ENV_FILE.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:  # degrade loudly
            print(f"[data] could not read {ENV_FILE}: {exc}", file=sys.stderr)
            raw = ""
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            if key:
                values[key] = val

    _env_cache = values
    return values


def setting(name: str, default: str = "") -> str:
    """A config value. Process env beats .env beats default."""
    if name in os.environ and os.environ[name] != "":
        return os.environ[name]
    return _load_env().get(name, default) or default


def reload_env() -> None:
    """Drop the cache so a .env edit takes effect without a restart."""
    global _env_cache
    _env_cache = None


# ---------------------------------------------------------------------------
# The switch
# ---------------------------------------------------------------------------

def is_demo() -> bool:
    """True unless JARVIS_DEMO is explicitly 0/false/no/off."""
    raw = setting("JARVIS_DEMO", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def mode_label() -> str:
    return "DEMO (invented fixtures)" if is_demo() else "LIVE (your real folders)"


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VaultRoot:
    """One indexed folder. `label` namespaces note ids across roots."""

    path: Path
    label: str


@dataclass(frozen=True)
class SourceReport:
    """What resolved, and what didn't. Surfaced in the UI — never swallowed."""

    roots: tuple[VaultRoot, ...]
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return bool(self.roots)


def _label_for(path: Path, taken: set[str]) -> str:
    label = path.name or path.drive.rstrip(":") or "root"
    base, n = label, 2
    while label.lower() in taken:
        label = f"{base}-{n}"
        n += 1
    taken.add(label.lower())
    return label


def vault_sources() -> SourceReport:
    """The folders to index, plus anything that went wrong resolving them.

    In demo mode this returns the demo vault and *ignores JARVIS_VAULTS
    entirely* — a stray real path in .env cannot leak into a screen recording.
    """
    problems: list[str] = []

    if is_demo():
        if not DEMO_VAULT.is_dir():
            problems.append(
                f"demo vault missing at {DEMO_VAULT} — run: python data/generate.py"
            )
            return SourceReport((), tuple(problems))
        return SourceReport((VaultRoot(DEMO_VAULT, "demo"),), ())

    raw = setting("JARVIS_VAULTS", "").strip()
    if not raw:
        problems.append(
            "JARVIS_DEMO=0 but JARVIS_VAULTS is empty — nothing to index. "
            "Set JARVIS_VAULTS in .env to semicolon-separated folder paths."
        )
        return SourceReport((), tuple(problems))

    roots: list[VaultRoot] = []
    taken: set[str] = set()
    for chunk in raw.split(";"):
        chunk = chunk.strip().strip('"')
        if not chunk:
            continue
        path = Path(os.path.expandvars(os.path.expanduser(chunk)))
        try:
            path = path.resolve()
        except OSError as exc:
            problems.append(f"{chunk}: {exc}")
            continue
        if not path.exists():
            problems.append(f"{path}: does not exist")
            continue
        if not path.is_dir():
            problems.append(f"{path}: not a folder")
            continue
        roots.append(VaultRoot(path, _label_for(path, taken)))

    if not roots and not problems:
        problems.append("JARVIS_VAULTS parsed to zero usable folders")
    return SourceReport(tuple(roots), tuple(problems))


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

def anthropic_key() -> str:
    return setting("ANTHROPIC_API_KEY")


def anthropic_model() -> str:
    return setting("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


def elevenlabs_key() -> str:
    return setting("ELEVENLABS_API_KEY")


def elevenlabs_voice_id() -> str:
    return setting("ELEVENLABS_VOICE_ID")


def server_address() -> tuple[str, int]:
    host = setting("JARVIS_HOST", "127.0.0.1")
    try:
        port = int(setting("JARVIS_PORT", "8765"))
    except ValueError:
        port = 8765
    return host, port


if __name__ == "__main__":
    report = vault_sources()
    print(f"mode      : {mode_label()}")
    print(f"env file  : {ENV_FILE} {'(found)' if ENV_FILE.is_file() else '(absent)'}")
    for root in report.roots:
        print(f"source    : [{root.label}] {root.path}")
    for problem in report.problems:
        print(f"PROBLEM   : {problem}")
    print(f"anthropic : {'key set' if anthropic_key() else 'NO KEY'}")
    print(f"elevenlabs: {'key set' if elevenlabs_key() else 'NO KEY'}")
