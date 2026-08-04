"""run.py — the whole suite, one command.

    python tests/run.py

Every file here pins JARVIS_DEMO=1 for itself: the assertions are about the
demo vault's contents, and a suite that passes or fails depending on where
JARVIS_VAULTS happens to point today is not a suite. Your own vault is never
read by these, and nothing here writes to it.

Two of them spend real money — test_semantic.py asks the model for equivalent
words, and test_llm.py probes the CLI. That is deliberate: the guarantees they
check are about a real subprocess with a real argv, and a mock would assert
that the mock is correct. Pass --fast to skip them.

test_mic.mjs needs node, and test_keepalive.py needs the server running. If
either is absent it is reported as SKIP, not as a pass — a check that did not
run is not a check that succeeded.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Cheap and offline first, so a broken build fails in seconds rather than
# after two minutes of waiting on the model.
FAST = ["check_ui.py", "test_tools.py", "test_fold.py", "test_memory.py",
        "test_keepalive.py", "test_file.py", "test_notebook.py", "test_skills.py"]
SLOW = ["test_llm.py", "test_brain.py", "test_semantic.py"]
NODE = ["test_mic.mjs"]


def run(name: str) -> tuple[str, str, float]:
    """Returns (status, last line, seconds)."""
    path = HERE / name
    if name.endswith(".mjs"):
        node = shutil.which("node")
        if not node:
            return "SKIP", "node não está instalado", 0.0
        argv = [node, str(path)]
    else:
        argv = [sys.executable, str(path)]

    started = time.time()
    done = subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=HERE.parent)
    took = time.time() - started
    out = (done.stdout or "") + (done.stderr or "")
    lines = [ln for ln in out.splitlines() if ln.strip()]

    if done.returncode == 0:
        # A test that stood down still exits 0. Reporting that as a pass is
        # the one thing a runner must never do.
        skip = next((ln.strip() for ln in lines if ln.strip().startswith("SKIP")), "")
        if skip:
            return "SKIP", skip[4:].strip(), took
        return "OK", lines[-1] if lines else "", took
    # The failing assertions are what you want to see, not the last line.
    fails = [ln.strip() for ln in lines if ln.strip().startswith("FAIL")]
    return "FAIL", "; ".join(fails[:3]) or (lines[-1] if lines else "sem saída"), took


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    fast_only = "--fast" in sys.argv
    names = FAST + NODE + ([] if fast_only else SLOW)
    if fast_only:
        print("  (--fast: pulando os que chamam o modelo)\n")

    failed, skipped = [], []
    started = time.time()
    for name in names:
        print(f"  {name:<18} ", end="", flush=True)
        status, detail, took = run(name)
        print(f"{status:<5} {took:5.1f}s  {detail[:96]}")
        if status == "FAIL":
            failed.append(name)
        elif status == "SKIP":
            skipped.append(name)

    print(f"\n  {len(names) - len(failed) - len(skipped)}/{len(names)} passaram "
          f"em {time.time() - started:.0f}s")
    if skipped:
        print(f"  pulados: {', '.join(skipped)}")
    if failed:
        print(f"  FALHARAM: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
