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


def demo_vault() -> Path:
    """Where the invented vault lives, when there is one.

    It used to be a constant at data/demo_vault, and a copy of 142 invented
    notes sat in the working tree forever. It does not any more: it is a test
    fixture and a screen-recording mode, not something the repository should
    carry around. JARVIS_DEMO_VAULT moves it, which is how the suite builds
    its own throwaway copy somewhere temporary and leaves this tree clean.
    """
    override = setting("JARVIS_DEMO_VAULT", "").strip().strip('"')
    if override:
        return Path(os.path.expandvars(os.path.expanduser(override)))
    return ROOT / "data" / "demo_vault"


def vault_sources() -> SourceReport:
    """The folders to index, plus anything that went wrong resolving them.

    In demo mode this returns the demo vault and *ignores JARVIS_VAULTS
    entirely* — a stray real path in .env cannot leak into a screen recording.
    """
    problems: list[str] = []

    if is_demo():
        demo = demo_vault()
        if not demo.is_dir():
            problems.append(
                f"demo vault missing at {demo} — run: python data/generate.py"
            )
            return SourceReport((), tuple(problems))
        return SourceReport((VaultRoot(demo, "demo"),), ())

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
# Model and keys
#
# There is no Anthropic API key here any more. The model runs on the Claude
# subscription already signed in on this machine, and llm.py owns that.
# ---------------------------------------------------------------------------

def llm_mode() -> str:
    """How JARVIS reaches a model. Only 'subscription' exists now.

    The API-key path was removed when this moved onto the Claude subscription.
    The setting is still read so that a .env asking for something else gets a
    straight answer instead of being quietly overruled.
    """
    return setting("JARVIS_LLM", "subscription").strip().lower()


def claude_cli() -> str:
    """An explicit path to claude.exe, or '' to go and find it."""
    return setting("CLAUDE_CLI").strip().strip('"')


def state_dir() -> Path:
    """The runtime's own scratch — outside the repo, and not the vault.

    WRITEABLE_ROOTS above says memory/ is the only place JARVIS writes "other
    than the runtime's own scratch". This is that scratch: llm.py runs the CLI
    from a directory in here, and the chosen brain is remembered here. Nothing
    personal goes in it, and none of it is versioned.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path.home() / ".local" / "state"
    path = root / "Jarvis"
    path.mkdir(parents=True, exist_ok=True)
    return path


BRAIN_FILE = "brain.txt"


def claude_model() -> str:
    """The model JARVIS asks for — its brain — as a concrete id.

    Three sources, in order: what you picked in the UI, then CLAUDE_CLI_MODEL
    in .env, then Opus. Picking in the UI wins so that changing your mind does
    not mean editing a file, and .env stays the answer for a machine you have
    not clicked on yet.

    Concrete ids, not aliases: 'opus' and 'sonnet' are moved from release to
    release, and a silent move throws away the prompt cache that makes repeated
    questions over the same vault cheap.
    """
    try:
        picked = (state_dir() / BRAIN_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        picked = ""
    return picked or setting("CLAUDE_CLI_MODEL") or setting("CLAUDE_MODEL", "claude-opus-5")


def choose_model(model: str) -> None:
    """Remember which brain to use. Empty string falls back to .env."""
    model = " ".join(str(model or "").split())
    (state_dir() / BRAIN_FILE).write_text(model, encoding="utf-8")


def language() -> str:
    """The language answers should come back in, or '' to follow the question.

    Matters most for the briefing, which has no question to take a cue from.
    """
    return setting("JARVIS_LANG").strip()


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
    print(f"model     : {claude_model()} (on the Claude subscription)")
    print(f"elevenlabs: {'key set' if elevenlabs_key() else 'NO KEY'}")
