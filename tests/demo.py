"""The invented vault the assertions are written against, built somewhere
temporary.

It used to live at data/demo_vault — 142 invented notes sitting in the working
tree forever, generic placeholder content about a studio that does not exist.
Once JARVIS started reading real folders that was clutter, so it went.

But the suite still needs it: test_fold asserts that "deposit policy" reaches
a note that says deposit, test_semantic asserts that asking about "atraso"
finds notes that say outstanding. Those are properties of THAT vault, and
rewriting them against a hand-made three-note fixture would weaken them into
tautologies.

So it is generated on demand, into the system temp folder, from the same
fixed seed as always. Same seed, same graph — the assertions hold. It costs
about a second the first time and nothing afterwards, and the repository
stays clean.

Every test calls ensure() before importing anything from agent/.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Named demo_vault because generate.py refuses to write anywhere else — that
# refusal is the only thing standing between a settable path and an rmtree on
# somebody's notes.
PATH = Path(tempfile.gettempdir()) / "jarvis-tests" / "demo_vault"

# Enough notes to know a half-written vault from a finished one. The generator
# makes 142; anything far below that means it died partway.
EXPECTED_AT_LEAST = 120


def _looks_complete() -> bool:
    if not PATH.is_dir():
        return False
    return sum(1 for _ in PATH.rglob("*.md")) >= EXPECTED_AT_LEAST


def ensure() -> Path:
    """Point JARVIS at a demo vault that exists. Builds one if needed."""
    os.environ["JARVIS_DEMO"] = "1"
    os.environ["JARVIS_DEMO_VAULT"] = str(PATH)

    if _looks_complete():
        return PATH

    PATH.parent.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(
        [sys.executable, str(REPO / "data" / "generate.py"), str(PATH)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0 or not _looks_complete():
        raise SystemExit(
            "não consegui gerar o vault de teste em " + str(PATH) + "\n"
            + (done.stdout or "") + (done.stderr or "")
        )
    return PATH


if __name__ == "__main__":
    where = ensure()
    print(f"  vault de teste: {where}")
    print(f"  notas: {sum(1 for _ in where.rglob('*.md'))}")
