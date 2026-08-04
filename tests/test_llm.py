"""Exercise llm.py against a faked subprocess boundary.

The argv assertions are the point. A silently dropped flag is invisible at
runtime and expensive: without --tools "" the model gets a shell over the
machine, without --no-session-persistence every question spools the vault to
disk forever, and without -n a second model call reads the notes to invent a
session title. These are the regression guards for exactly that.
"""
import os
import json
import subprocess
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The demo vault, always, and built somewhere temporary — these
# assertions are about ITS content. Without this the suite passes or
# fails depending on wherever JARVIS_VAULTS points today, which is
# not a test. ensure() must run before anything from agent/ is
# imported, because data.py reads the setting at call time.
import demo  # noqa: E402
demo.ensure()



from agent import llm  # noqa: E402

calls: list[dict] = []
behaviour: dict = {"payload": None, "stdout": None, "stderr": b"", "rc": 0, "raise": None}


def fake_run(argv, *, input=b"", stdout=None, stderr=None, timeout=None,
             cwd=None, env=None, creationflags=0):
    calls.append({"argv": argv, "stdin": input, "cwd": cwd, "env": env, "timeout": timeout})
    if behaviour["raise"] is not None:
        raise behaviour["raise"]
    if behaviour["stdout"] is not None:
        out = behaviour["stdout"]
    else:
        out = json.dumps(behaviour["payload"] or OK).encode()
    return subprocess.CompletedProcess(argv, behaviour["rc"], out, behaviour["stderr"])


MODEL = llm.model_name()          # whatever .env configured, not a hardcode
OK = {
    "type": "result", "subtype": "success", "is_error": False,
    "result": "Deposits are 40% [demo/notes/deposit-policy.md].",
    "stop_reason": "end_turn", "duration_ms": 4200,
    "usage": {"input_tokens": 2, "cache_creation_input_tokens": 5000,
              "cache_read_input_tokens": 300, "output_tokens": 120},
    "modelUsage": {MODEL: {"inputTokens": 5302, "outputTokens": 120}},
}


def reset(**kw):
    calls.clear()
    behaviour.update({"payload": None, "stdout": None, "stderr": b"", "rc": 0, "raise": None})
    behaviour.update(kw)


llm._run.__globals__["subprocess"] = types.SimpleNamespace(
    run=fake_run, PIPE=subprocess.PIPE,
    TimeoutExpired=subprocess.TimeoutExpired,
    CompletedProcess=subprocess.CompletedProcess,
)
llm._latched = None

# -- 1. the executable ------------------------------------------------------

launcher, is_shim = llm._launcher()
print(f"launcher   {launcher.name}   shim={is_shim}")
assert launcher.suffix.lower() == ".exe", f"not the native exe: {launcher}"
assert not is_shim

# -- 2. the load-bearing flags ----------------------------------------------

reset()
text, usage = llm.complete("SYSTEM RULES", "what is the deposit policy?")
argv = calls[0]["argv"]

def pair(flag):
    return argv[argv.index(flag) + 1] if flag in argv else None

print("\nargv guards")
REQUIRED = {
    "--tools": "",                     # no shell / filesystem / web
    "--setting-sources": "",           # no CLAUDE.md, skills or hooks
    "--output-format": "json",
    "--max-turns": "1",
    "-n": "jarvis",                    # kills the extra title model call
    "--model": llm.model_name(),       # whatever .env asked for, not a hardcode
    "--fallback-model": llm.FALLBACK_MODEL,
    "--effort": "medium",
}
for flag, want in REQUIRED.items():
    got = pair(flag)
    print(f"    {flag:20} {got!r}")
    assert got == want, f"{flag} is {got!r}, expected {want!r}"

for flag in ("--print", "--no-session-persistence", "--strict-mcp-config",
             "--disable-slash-commands"):
    print(f"    {flag:20} present")
    assert flag in argv, f"{flag} missing"

for forbidden in ("--bare", "--verbose", "-d", "--debug"):
    assert forbidden not in argv, f"{forbidden} must never be passed"
print("    --bare/--verbose     absent")

assert pair("--system-prompt") == "SYSTEM RULES"
assert "--system-prompt-file" not in argv

# -- 3. the prompt goes on stdin, not argv ----------------------------------

assert b"what is the deposit policy?" in calls[0]["stdin"]
assert not any("deposit policy" in a for a in argv), "the question leaked onto argv"
print("\nprompt on stdin, absent from argv")

reset()
llm.complete("s", "line one\r\nline two\r\n")
assert b"\r" not in calls[0]["stdin"], "CRLF was not normalised"
print("CRLF normalised")

# -- 4. cwd and environment -------------------------------------------------

cwd = str(calls[0]["cwd"])
print(f"\ncwd        {cwd}")
assert "Documents\\Jarvis" not in cwd, "runs in the repo — a CLAUDE.md there would rewrite the prompt"
assert "claude-cwd" in cwd

env = calls[0]["env"]
for name in llm._SCRUB:
    assert name not in env, f"{name} was not scrubbed from the child environment"
print(f"scrubbed   {', '.join(llm._SCRUB[:4])}, …")
assert env.get("CLAUDE_CODE_MAX_RETRIES") == "2"
assert "PATH" in env and ("USERPROFILE" in env or "HOME" in env), "child cannot find its login"
print("kept       PATH / USERPROFILE (the login lives there)")

# -- 5. usage arithmetic ----------------------------------------------------

print(f"\nusage      {usage}")
assert usage["input_tokens"] == 5302, "input must add the two cache fields, not report the raw 2"
assert usage["output_tokens"] == 120
assert usage["model"] == MODEL
assert usage["truncated"] is False

# -- 6. blank prompt is refused before spawning -----------------------------

reset()
for blank in ("", "   \n  "):
    try:
        llm.complete("s", blank)
        raise AssertionError("a blank prompt was sent")
    except llm.LLMFailed as exc:
        assert str(exc) == "no question given", exc
assert not calls, "a process was spawned for a blank prompt"
print("\nblank prompt refused without spawning")

# -- 7. failure taxonomy ----------------------------------------------------

print()
CASES = [
    ("not signed in",
     {"is_error": True, "result": "Not logged in \u00b7 Please run /login"}, 1,
     llm.LLMUnavailable, "not signed in"),
    ("stray api key",
     {"is_error": True, "api_error_status": 401, "result": "Invalid API key"}, 1,
     llm.LLMFailed, "overriding the subscription"),
    ("bad model",
     {"is_error": True, "api_error_status": 404, "result": "model not found"}, 1,
     llm.LLMFailed, "CLAUDE_CLI_MODEL"),
    ("plan window spent",
     {"is_error": True, "api_error_status": 429, "result": "Claude usage limit reached"}, 1,
     llm.LLMFailed, "usage window is spent"),
    ("transient throttle",
     {"is_error": True, "result": "Server is temporarily limiting requests"}, 1,
     llm.LLMFailed, "throttling"),
    ("network down",
     {"is_error": True, "result": "Unable to connect to api.anthropic.com"}, 1,
     llm.LLMFailed, "could not reach"),
    ("no result key at all",
     {"is_error": True, "subtype": "error_max_turns", "errors": ["Max turns reached"]}, 1,
     llm.LLMFailed, "Max turns"),
    ("empty answer",
     {"is_error": False, "subtype": "success", "result": "   ", "stop_reason": "end_turn"}, 0,
     llm.LLMFailed, "returned nothing"),
]
for label, payload, rc, kind, needle in CASES:
    llm._latched = None
    reset(payload=payload, rc=rc)
    try:
        llm.complete("s", "q")
        raise AssertionError(f"{label} did not raise")
    except (llm.LLMFailed, llm.LLMUnavailable) as exc:
        assert isinstance(exc, kind), f"{label}: {type(exc).__name__} not {kind.__name__}"
        assert needle in str(exc), f"{label}: {exc}"
        print(f"{label:22} {kind.__name__:16} {exc}")

# A signed-out failure must latch, so /api/health tells the truth afterwards
# without spawning anything — and a later success must clear it again.
llm._latched = None
reset(payload={"is_error": True, "result": "Not logged in · Please run /login"}, rc=1)
try:
    llm.complete("s", "q")
except llm.LLMUnavailable:
    pass
assert llm.reason() == llm.NO_LOGIN, "a signed-out failure did not latch"
print(f"{'':22} latched  -> reason() = {llm.reason()!r}")

reset()
llm.complete("s", "q")
assert llm.reason() is None, "a success did not clear the latch"
print(f"{'':22} cleared  -> reason() = {llm.reason()!r}")

# -- 8. hostile payload shapes ----------------------------------------------

print()
reset(stdout=b"", stderr=b"error: unknown option '--nope'", rc=1)
try:
    llm.complete("s", "q")
    raise AssertionError("empty stdout accepted")
except llm.LLMFailed as exc:
    print(f"{'stdout empty':22} {exc}")
    assert "unknown option" in str(exc)

reset(stdout=b"Checking for updates...\n{not json")
try:
    llm.complete("s", "q")
    raise AssertionError("garbage accepted")
except llm.LLMFailed as exc:
    print(f"{'stdout not JSON':22} {exc}")

reset(stdout=json.dumps([{"type": "system"}, {"type": "result", **OK}]).encode())
text, _ = llm.complete("s", "q")
print(f"{'stdout is a JSON array':22} recovered the result element")
assert "Deposits are 40%" in text

reset(stderr="\u26a0 claude.ai connectors are disabled".encode("utf-8"))
text, _ = llm.complete("s", "q")
print(f"{'warning on stderr':22} still a success")

# -- 9. the model that answered must be the one we asked for ----------------

print()
reset(payload={**OK, "modelUsage": {"claude-sonnet-5": {"inputTokens": 10, "outputTokens": 2}}})
text, usage = llm.complete("s", "q")
print(f"{'fallback answered':22} accepted ({usage['model']})")

reset(payload={**OK, "modelUsage": {"claude-haiku-4-5-x": {"inputTokens": 10, "outputTokens": 2}}})
try:
    llm.complete("s", "q")
    raise AssertionError("an unexpected model was accepted")
except llm.LLMFailed as exc:
    print(f"{'wrong model answered':22} {exc}")

# -- 10. timeout ------------------------------------------------------------

reset(raise_=None)
behaviour["raise"] = subprocess.TimeoutExpired(cmd="claude", timeout=llm.TIMEOUT_SECONDS)
try:
    llm.complete("s", "q")
    raise AssertionError("timeout not surfaced")
except llm.LLMFailed as exc:
    print(f"\n{'timeout':22} {exc}")

print("\nOK — argv guards, isolation, usage maths, and every failure path.")
