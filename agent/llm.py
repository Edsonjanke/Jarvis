"""llm.py — THE ONLY FILE THAT TALKS TO A MODEL.

JARVIS runs on the Claude subscription already signed in on this machine, not
on a metered API key. It drives the Claude Code CLI in print mode, which is the
documented way to use that agent loop from another language:

    https://code.claude.com/docs/en/headless

So there is no key in .env to leak, and no pip dependency: the project is back
to standard library only, which is how the rest of it is written.

Same rule as data.py owning the DEMO switch — if you find yourself spawning
`claude` anywhere else in this codebase, that is the bug. Everything above this
file passes two strings and gets back text or a typed failure.

WHY THE ARGV LOOKS LIKE THAT. Every flag below was measured, and most of them
are load-bearing rather than tidy:

  * `--no-session-persistence` is not optional. Without it, every question
    writes the whole notes block — the user's private vault, verbatim and in
    the clear — into ~/.claude/projects/<cwd>/<uuid>.jsonl, and leaves it there.
  * `-n jarvis` is the only thing that suppresses a *second* model call that
    Claude Code makes to name the session. That call also receives the notes.
  * `--tools ""` is the guarantee that the model never touches the disk. The
    notes arrive in the prompt; there is nothing for it to go and read.
  * `--setting-sources ""` stops the working directory supplying a CLAUDE.md,
    a skill, or a settings file with shell hooks in it. A CLAUDE.md is an
    instruction: left discoverable, it silently rewrites the system prompt.
  * We run from a scratch directory of our own, outside the repo, for the same
    reason — the cwd is what makes those files discoverable in the first place.
  * `--system-prompt` *replaces* Claude Code's own preamble. That is what stops
    the model narrating tool calls it cannot make ("I'll read that file for
    you…") into the answer, and it cuts the input from ~30k tokens to ~200.
  * The child environment is scrubbed. A stray ANTHROPIC_API_KEY anywhere in
    the environment silently overrides the subscription and fails with a 401;
    CLAUDE_EFFORT and a user-level effort setting quietly multiply the cost.

And two that must never appear:

  * `--bare` reads only ANTHROPIC_API_KEY and deliberately ignores the
    subscription login. The docs say it may become the default for -p one day;
    if a future version stops honouring the subscription, look here first.
  * `--verbose` turns stdout from a JSON object into a JSON array. json.loads
    still succeeds, and every field read after it is then wrong.

Run it directly for a one-line check:  python -m agent.llm
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

if __package__ in (None, ""):  # allow `python agent/llm.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod

NO_CLI = ("Claude Code is not installed, or not on PATH — see "
          "https://code.claude.com/docs/en/quickstart")
NO_LOGIN = "Claude Code is not signed in — run: claude auth login"

# Rescues the turn when the primary model is unavailable. Free when it is not.
FALLBACK_MODEL = "claude-sonnet-5"

EFFORTS = ("low", "medium", "high", "xhigh", "max")

# ~5-6s is normal, of which ~3.5s is Node starting up; a big brief at high
# effort runs to ~20s. Left alone the CLI retries a dead network for about
# three minutes, which is why the child gets CLAUDE_CODE_MAX_RETRIES=2 below —
# with that, everything real finishes well inside this, and 30s or 60s would
# instead kill calls that were about to succeed.
TIMEOUT_SECONDS = 120

# ThreadingHTTPServer will happily start a Node process per browser tab.
MAX_CONCURRENT = 3
_slots = threading.Semaphore(MAX_CONCURRENT)

# Anything in the parent environment that would change WHERE the notes go, or
# WHICH model reads them. The provider switches matter most: one of those set
# anywhere in the environment sends the whole vault to Bedrock, Vertex or
# Foundry instead of to the subscription, and nothing in the reply would say so.
#
# Deliberately NOT scrubbed: CLAUDE_CONFIG_DIR and CLAUDE_CODE_OAUTH_TOKEN.
# Those are where a legitimate login lives — removing them would break the very
# subscription auth this file exists to use. We inherit the rest too, because
# the CLI needs USERPROFILE, APPDATA and PATH to find that login at all.
_SCRUB = (
    # credentials that would displace the subscription
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
    # a different destination for the notes
    "ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
    # a different model than the one we asked for
    "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    # a different amount of thinking than we asked and budgeted for
    "CLAUDE_EFFORT", "MAX_THINKING_TOKENS",
    # inherited identity of the Claude Code session that started the server
    "CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT",
)

_launcher_cache: tuple[Path, bool] | None = None
_cli_note: str | None = None
_latched: str | None = None
_lock = threading.Lock()


class LLMUnavailable(RuntimeError):
    """No CLI, or not signed in. A configuration fact, not a failure."""


class LLMFailed(RuntimeError):
    """The call was made and did not come back usable."""


# ---------------------------------------------------------------------------
# Where the binary is, and where we run it
# ---------------------------------------------------------------------------

def _launcher() -> tuple[Path, bool] | None:
    """The Claude Code binary, and whether we are stuck with a batch shim.

    CLAUDE_CLI in .env wins when it points at something real. When it points at
    nothing — a path copied from another machine, say — we go and find the CLI
    anyway rather than refuse to work, and say so in cli_note().

    Otherwise: shutil.which finds claude.CMD on Windows, which is a batch
    wrapper around the real claude.exe. Batch files re-parse & | ^ % " < > in
    arguments — a system prompt containing '>' exits 1 with "'>' was unexpected
    at this time" — so prefer the executable it wraps.
    """
    global _launcher_cache, _cli_note
    if _launcher_cache is not None:
        return _launcher_cache

    configured = data_mod.claude_cli()
    if configured:
        if Path(configured).is_file():
            _launcher_cache = (Path(configured), Path(configured).suffix.lower()
                               in (".cmd", ".bat", ".ps1"))
            return _launcher_cache
        _cli_note = (f"CLAUDE_CLI in .env points at {configured}, which does not "
                     f"exist — found Claude Code on PATH instead")

    found = shutil.which("claude")
    if not found:
        return None

    path = Path(found)
    if path.suffix.lower() in (".cmd", ".bat", ".ps1"):
        for candidate in (
            path.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe",
            path.parent / "claude.exe",
        ):
            if candidate.is_file():
                path = candidate
                break

    _launcher_cache = (path, path.suffix.lower() in (".cmd", ".bat", ".ps1"))
    return _launcher_cache


def _workdir() -> Path:
    """A scratch directory we own, deliberately outside the repo.

    The cwd decides which CLAUDE.md, skills, settings and .mcp.json the CLI
    discovers, and which folder it names under ~/.claude/projects/. Running
    from the repo would mean a CLAUDE.md added there later could rewrite the
    system prompt with nothing to show for it.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    path = root / "Jarvis" / "claude-cwd"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
    # Without this the CLI spends ~3 minutes retrying a dead network before it
    # reports anything at all.
    env["CLAUDE_CODE_MAX_RETRIES"] = "2"
    return env


# ---------------------------------------------------------------------------
# Availability — reason() must never spawn, /api/health calls it on page load
# ---------------------------------------------------------------------------

def _run(argv: list[str], *, stdin: bytes = b"", timeout: int,
         cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        argv,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
        env=_child_env(),
        # Stops a console window flashing if the server is ever run detached.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def cli_note() -> str | None:
    """A configuration oddity worth mentioning, but not worth failing over."""
    _launcher()          # resolving is what discovers it
    return _cli_note


def probe() -> str | None:
    """Ask the CLI whether it is signed in, and remember the answer.

    Spawns a process (~1.4s) but spends no tokens. Called once at server start;
    reason() reads what it latched. Not called per request.
    """
    global _latched
    launcher = _launcher()
    if launcher is None:
        with _lock:
            _latched = NO_CLI
        return NO_CLI

    try:
        proc = _run([str(launcher[0]), "auth", "status"], timeout=60)
        status = json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
        problem = None if status.get("loggedIn") else NO_LOGIN
    except subprocess.TimeoutExpired:
        problem = "Claude Code did not answer `auth status`"
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        problem = NO_LOGIN

    with _lock:
        _latched = problem
    return problem


def reason() -> str | None:
    """Why the model cannot be used, or None. Never spawns anything.

    Before the first probe or call, an install we have not checked is reported
    as usable — an optimistic unknown beats greying out a working button.
    """
    mode = data_mod.llm_mode()
    if mode != "subscription":
        return (f"JARVIS_LLM is set to {mode!r}, and only 'subscription' exists — "
                f"the API-key path was removed")
    if _launcher() is None:
        return NO_CLI
    return _latched


def available() -> bool:
    return reason() is None


def account() -> dict[str, object]:
    """Which login and plan is answering. Spawns; for the terminal, not the UI."""
    launcher = _launcher()
    if launcher is None:
        return {}
    try:
        proc = _run([str(launcher[0]), "auth", "status"], timeout=60)
        status = json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    # The email is the user's own and stays in the terminal. Only the shape of
    # the account goes anywhere near a JSON payload.
    return {"auth": status.get("authMethod"), "plan": status.get("subscriptionType")}


def model_name() -> str:
    return data_mod.claude_model()


# ---------------------------------------------------------------------------
# The call
# ---------------------------------------------------------------------------

def _argv(launcher: Path, system_flag: list[str], model: str, effort: str) -> list[str]:
    """The whole command line, built here and nowhere else.

    A silently dropped flag would be invisible at runtime and expensive — one
    would hand the model a shell, another would spool the vault to disk. Keeping
    them as one unconditional list is the only defence, so resist making any of
    them conditional.
    """
    return [
        str(launcher),
        "--print",
        "--output-format", "json",
        "--model", model,
        "--fallback-model", FALLBACK_MODEL,
        "--effort", effort,
        "--tools", "",                  # no shell, no filesystem, no web
        "--setting-sources", "",        # no CLAUDE.md, no skills, no hooks
        "--strict-mcp-config",          # no MCP servers from this machine
        "--disable-slash-commands",     # the prompt cannot invoke a skill
        "--no-session-persistence",     # the vault is not written to disk
        "--max-turns", "1",             # one question, one answer
        "-n", "jarvis",                 # suppresses the extra title-model call
        *system_flag,
    ]


def complete(
    system: str,
    user: str,
    *,
    max_tokens: int | None = None,   # accepted, ignored — see below
    effort: str = "medium",
) -> tuple[str, dict[str, object]]:
    """One turn. Returns the answer text and a small usage report.

    `max_tokens` has no equivalent: Claude Code owns the output budget. It is
    accepted so callers written against the API-backed version keep working,
    and it does nothing — it is not quietly approximated.

    Raises LLMUnavailable when there is nothing to call, LLMFailed with a
    sentence fit for the alert strip when the call itself goes wrong.
    """
    global _latched

    # Gate only on the fact we can check for free and that cannot change while
    # the server runs. Deliberately NOT on the latched sign-in state: if a
    # signed-out latch blocked the call, `claude auth login` in another window
    # could never take effect, and JARVIS would stay dead until restarted. The
    # call itself is what discovers sign-in, and what clears the latch.
    if _launcher() is None:
        raise LLMUnavailable(NO_CLI)

    prompt = user.replace("\r\n", "\n").strip()
    if not prompt:
        # Empty and whitespace-only stdin fail differently and unhelpfully.
        raise LLMFailed("no question given")

    launcher, is_shim = _launcher()  # type: ignore[misc]
    model = model_name()
    if effort not in EFFORTS:
        effort = "medium"

    with _slots:
        with tempfile.TemporaryDirectory() as tmp:
            if is_shim:
                # No claude.exe, so the launch goes through cmd.exe and free
                # text on argv would be re-parsed. Hand it a file instead.
                spfile = Path(tmp) / "system.txt"
                spfile.write_text(system, encoding="utf-8")
                system_flag = ["--system-prompt-file", str(spfile)]
            else:
                system_flag = ["--system-prompt", system]

            argv = _argv(launcher, system_flag, model, effort)
            try:
                proc = _run(argv, stdin=prompt.encode("utf-8") + b"\n",
                            timeout=TIMEOUT_SECONDS, cwd=_workdir())
            except subprocess.TimeoutExpired:
                raise LLMFailed(
                    f"Claude did not answer within {TIMEOUT_SECONDS}s — try a narrower question"
                ) from None
            except OSError as exc:
                raise LLMFailed(f"could not start Claude Code: {exc}") from None

    stdout = proc.stdout.decode("utf-8", "replace").strip()
    stderr = proc.stderr.decode("utf-8", "replace").strip()

    if not stdout:
        # An unknown flag is reported to stderr before the run starts. A
        # successful run also writes warnings there, so stderr alone is never
        # treated as failure — only stderr with nothing on stdout.
        raise LLMFailed(_last_line(stderr) or f"Claude Code exited {proc.returncode} with no output")

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        raise LLMFailed(f"Claude Code returned something that is not JSON: {stdout[:120]}") from None

    if isinstance(payload, list):  # --verbose shape; should not happen here
        payload = next((p for p in reversed(payload)
                        if isinstance(p, dict) and p.get("type") == "result"), {})
    if not isinstance(payload, dict):
        raise LLMFailed("Claude Code returned an unexpected payload shape")

    # A failure inside the run comes back looking successful: exit may be 1 but
    # the JSON parses, and `subtype` can still say "success" while is_error is
    # true. is_error is the gate; subtype is not.
    if payload.get("is_error") or proc.returncode != 0:
        message = _explain(payload, model)
        if message is NO_LOGIN:
            with _lock:
                _latched = NO_LOGIN
            raise LLMUnavailable(NO_LOGIN)
        raise LLMFailed(message)

    text = str(payload.get("result") or "").strip()
    if not text:
        raise LLMFailed(f"Claude returned nothing (stop_reason: {payload.get('stop_reason')})")

    usage = _usage(payload, model)
    answered = usage["model"]
    if answered not in (model, FALLBACK_MODEL, None):
        # The only runtime tell that our flags actually reached the CLI.
        raise LLMFailed(f"Claude answered with {answered!r} instead of {model!r}")

    with _lock:
        _latched = None      # it works; clear anything latched earlier
    return text, usage


def _last_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line:
            return line.removeprefix("Error: ").removeprefix("error: ")
    return ""


def _explain(payload: dict[str, object], model: str) -> str:
    """One sentence for the alert strip.

    Several failure shapes carry no `result` key at all, so nothing here may
    assume one exists.
    """
    errors = payload.get("errors")
    raw = str(
        payload.get("result")
        or (errors[0] if isinstance(errors, list) and errors else "")
        or ""
    ).strip()
    status = payload.get("api_error_status")
    lowered = raw.lower()

    if "not logged in" in lowered or "please run /login" in lowered:
        return NO_LOGIN
    if status == 401:
        return "an ANTHROPIC_API_KEY in the environment is overriding the subscription — unset it"
    if status == 404 or "not found" in lowered:
        return f"no model called {model!r} on this account — fix CLAUDE_CLI_MODEL in .env"
    if "usage limit" in lowered:
        return "the Claude plan's usage window is spent — try again after it resets"
    if "temporarily limiting" in lowered or status == 429:
        return "Anthropic is throttling requests — ask again in a moment"
    if "unable to connect" in lowered or "timed out" in lowered:
        return "could not reach Anthropic — check the network"
    if raw:
        return _last_line(raw)[:300]
    return f"Claude Code failed ({payload.get('subtype') or 'no detail'})"


def _usage(payload: dict[str, object], model: str) -> dict[str, object]:
    """Token counts, from the fields that are actually trustworthy.

    `usage.input_tokens` counts only the *uncached* part — it reads 1 or 2 for
    a 48 kB prompt whose bulk landed in the cache — so the input figure is the
    three input fields added together. `modelUsage` names the model; `usage`
    never does. With `-n` set it has exactly one key.
    """
    counts = payload.get("usage")
    counts = counts if isinstance(counts, dict) else {}
    per_model = payload.get("modelUsage")
    answered = None
    if isinstance(per_model, dict) and per_model:
        answered = next(iter(per_model)) if len(per_model) == 1 else max(
            per_model,
            key=lambda k: (per_model[k].get("inputTokens", 0)
                           if isinstance(per_model[k], dict) else 0),
        )

    stop = payload.get("stop_reason")
    return {
        "model": answered or model,
        "stop_reason": stop,
        # Kept because the UI reads it. Claude Code owns the output budget, so
        # in practice this never fires — JARVIS can no longer tell that an
        # answer was cut short, and pretending otherwise would be a false alarm.
        "truncated": stop == "max_tokens",
        "input_tokens": (counts.get("input_tokens", 0)
                         + counts.get("cache_creation_input_tokens", 0)
                         + counts.get("cache_read_input_tokens", 0)) or None,
        "output_tokens": counts.get("output_tokens"),
        "seconds": round((payload.get("duration_ms") or 0) / 1000, 1),
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    launcher = _launcher()
    print(f"  cli      {launcher[0] if launcher else 'NOT FOUND'}")
    if launcher and launcher[1]:
        print("           note: batch shim only, no claude.exe found")
    if cli_note():
        print(f"  note     {cli_note()}")
    print(f"  workdir  {_workdir()}")

    problem = probe()
    if problem:
        print(f"  model    UNAVAILABLE — {problem}")
        return 1

    who = account()
    print(f"  account  {who.get('auth')} ({who.get('plan')} plan)")
    print(f"  model    {model_name()}  (fallback {FALLBACK_MODEL})")

    started = time.time()
    text, usage = complete("Answer in exactly one short sentence. You have no tools.",
                           "Confirm you are reachable.")
    print(f"  reply    {text}")
    print(f"  usage    {usage}")
    print(f"  took     {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
