"""memory.py — the only file in JARVIS that writes to disk.

The content it stores is chosen by a language model that has just read private
notes, so the guarantees that matter are: it cannot write outside memory/, it
cannot grow without bound, and nothing it stores is hidden from the user.
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The demo vault, always — these assertions are about ITS content.
# Without this the suite passes or fails depending on whatever
# JARVIS_VAULTS happens to point at today, which is not a test.
os.environ["JARVIS_DEMO"] = "1"



from agent import data as data_mod, memory  # noqa: E402

FAILURES = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  ' + str(detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)


# Work in a throwaway directory — never the real memory/.
SANDBOX = Path(tempfile.mkdtemp(prefix="jarvis-memory-"))
data_mod.MEMORY_DIR = SANDBOX
print(f"sandbox  {SANDBOX}\n")

# ---------------------------------------------------------------------------
print("1. it cannot write outside memory/")
# ---------------------------------------------------------------------------

ESCAPES = [
    "../../../etc/passwd",
    "..\\..\\windows\\system32\\config",
    "/absolute/elsewhere",
    "C:\\Users\\Evo\\.env",
    "....//....//escape",
    "a/../../b",
    "\x00nul",
    "con",              # a reserved Windows device name
]
for attempt in ESCAPES:
    fact = memory.remember(f"{attempt} is a thing worth knowing about the setup")
    if fact is None:
        check(f"{attempt[:26]!r} stored nothing", True)
        continue
    inside = SANDBOX.resolve() in fact.path.resolve().parents
    check(f"{attempt[:26]!r} stayed inside memory/", inside, str(fact.path))

# The slug is ours, so even a hostile fact body cannot name a file.
names = [p.name for p in SANDBOX.glob("*")]
check("every file is a plain .md in the sandbox",
      all(n.endswith(".md") and "/" not in n and "\\" not in n for n in names),
      f"{len(names)} files")
check("nothing was created above the sandbox",
      not (SANDBOX.parent / "etc").exists() and not (SANDBOX.parent / "passwd").exists())

for p in SANDBOX.glob("*"):
    p.unlink()

# ---------------------------------------------------------------------------
print("\n2. bounds")
# ---------------------------------------------------------------------------

long_fact = "x" * 5000
kept = memory.remember(long_fact)
check("an over-long fact is truncated, not refused",
      kept is not None and len(kept.text) <= memory.MAX_FACT_CHARS + 1,
      f"{len(kept.text) if kept else 0} chars")

check("a trivially short fact is ignored", memory.remember("ok") is None)
check("an empty fact is ignored", memory.remember("   ") is None)
check("None is ignored", memory.remember(None) is None)

for p in SANDBOX.glob("*"):
    p.unlink()

# Fill to the cap with genuinely distinct facts.
for i in range(memory.MAX_FACTS + 5):
    memory.remember(f"decision number {i} was to use approach alpha{i} for reason beta{i}")
stored = memory.facts()
check(f"stops at MAX_FACTS ({memory.MAX_FACTS})", len(stored) <= memory.MAX_FACTS,
      f"{len(stored)} stored")

for p in SANDBOX.glob("*"):
    p.unlink()

# ---------------------------------------------------------------------------
print("\n3. it does not remember the same thing twice")
# ---------------------------------------------------------------------------

first = memory.remember("Deposits are always forty per cent and never refundable")
again = memory.remember("Deposits are always forty per cent and never refundable")
check("the identical fact is not stored twice", first is not None and again is None)

near = memory.remember("Deposits are always forty per cent and never refundable, ever")
check("a near-duplicate is not stored either", near is None)

other = memory.remember("Invoices go out on the first working day of the month")
check("a genuinely different fact is stored", other is not None)
check("two facts on disk", len(memory.facts()) == 2, f"{len(memory.facts())}")

# ---------------------------------------------------------------------------
print("\n4. reading back and forgetting")
# ---------------------------------------------------------------------------

facts = memory.facts()
check("newest first", facts[0].recorded >= facts[-1].recorded)
check("text survives the round trip",
      any("forty per cent" in f.text for f in facts))

raw = facts[0].path.read_text(encoding="utf-8")
check("the file is readable markdown with frontmatter",
      raw.startswith("---") and "recorded:" in raw and facts[0].text in raw)

check("forget removes it", memory.forget(facts[0].name) is True)
check("and it is gone", len(memory.facts()) == 1)
check("forgetting something absent is False", memory.forget("no-such-fact") is False)
check("forget cannot escape either", memory.forget("../../../etc/passwd") is False)
check("the sandbox parent is untouched", not (SANDBOX.parent / "passwd").exists())

# ---------------------------------------------------------------------------
print("\n5. recall picks what is relevant")
# ---------------------------------------------------------------------------

for p in SANDBOX.glob("*"):
    p.unlink()

memory.remember("Kestrel Fitness always pays late but always pays in the end")
time.sleep(0.01)
memory.remember("Never start work on a project before the deposit clears")
time.sleep(0.01)
memory.remember("Prefer sonnet over opus for routine questions to save the usage window")

hits = memory.relevant("what should I know about Kestrel Fitness paying?")
texts = " | ".join(f.text for f in hits)
print(f"  recalled: {texts[:150]}")
check("the matching fact is recalled", any("Kestrel" in f.text for f in hits))
check("recall is bounded", len(hits) <= memory.RECALL_LIMIT, f"{len(hits)}")
check("the newest few come along regardless", len(hits) >= 1)

empty = memory.relevant("something entirely unrelated to anything stored xyzzy")
check("an unrelated question still gets the recent few",
      len(empty) == min(memory.RECENT_ALWAYS, 3), f"{len(empty)}")

# ---------------------------------------------------------------------------
print("\n6. extraction failures are silent")
# ---------------------------------------------------------------------------

from agent import llm  # noqa: E402

real = llm.complete
llm.complete = lambda *a, **k: (_ for _ in ()).throw(llm.LLMFailed("model is busy"))
check("learn() survives a model failure", memory.learn("q", "a") == [])
llm.complete = lambda *a, **k: ("NOTHING", {})
check("NOTHING stores nothing", memory.learn("q", "a") == [])
llm.complete = lambda *a, **k: ("- A durable preference was stated here today\n"
                                "* Another one worth keeping for later\n", {})
got = memory.learn("q", "a")
check("bullets are stripped and facts stored", len(got) == 2, [f.text[:30] for f in got])
check("no leading bullet survived", all(not f.text.startswith(("-", "*")) for f in got))
llm.complete = real

# ---------------------------------------------------------------------------
print("\n7. the two defects the adversarial review confirmed")
# ---------------------------------------------------------------------------

for p in SANDBOX.glob("*"):
    p.unlink()

# (a) Forget must delete the row that was clicked, not a similar one.
# Two facts sharing a long prefix collide, so the second becomes "<slug>-2" —
# and _slug truncates at 60, which used to fold that back onto the first.
base = "the quarterly reconciliation process for client accounts must"
one = memory.remember(base + " be done")
two = memory.remember(base + " never be skipped under any circumstances at all")
check("two similar facts both stored", one is not None and two is not None)
if one and two:
    print(f"    {one.name}")
    print(f"    {two.name}")
    check("their names differ", one.name != two.name)
    check("forget removes the one asked for", memory.forget(two.name) is True)
    left = [f.name for f in memory.facts()]
    check("and the other one survived", left == [one.name], str(left))

# A file put there by hand must be listed and deletable.
(SANDBOX / "My Own Rule.md").write_text(
    "---\nname: My Own Rule\nrecorded: 1\n---\n\nAlways confirm the address before shipping\n",
    encoding="utf-8")
listed = [f.name for f in memory.facts()]
check("a hand-written file is listed", "My Own Rule" in listed, str(listed))
check("and can be deleted", memory.forget("My Own Rule") is True)
check("it is gone", "My Own Rule" not in [f.name for f in memory.facts()])

check("an unknown name is still False", memory.forget("nothing-like-this") is False)
check("traversal still refused", memory.forget("../../../etc/passwd") is False)
check("the sandbox parent is untouched", not (SANDBOX.parent / "passwd").exists())

# (b) A fact that starts with a figure must keep it.
for p in SANDBOX.glob("*"):
    p.unlink()
llm.complete = lambda *a, **k: (
    "50% e o novo deposito padrao acordado com o cliente\n"
    "2026 sera o ano de renovacao do contrato da Kestrel\n"
    "3 dias e o prazo maximo de resposta acordado\n"
    "- um marcador de lista de verdade e removido\n"
    "1. e a numeracao tambem e removida\n", {})
kept = [f.text for f in memory.learn("q", "a")]
for text in kept:
    print(f"    {text}")
check("a percentage survives", any(t.startswith("50%") for t in kept), str(kept[:1]))
check("a year survives", any(t.startswith("2026") for t in kept))
check("a leading count survives", any(t.startswith("3 dias") for t in kept))
check("a real bullet is still stripped", any(t.startswith("um marcador") for t in kept))
check("numbering is still stripped", any(t.startswith("e a numeracao") for t in kept))
llm.complete = real

shutil.rmtree(SANDBOX, ignore_errors=True)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    raise SystemExit(1)
print("OK — confined to memory/, bounded, deduplicated, and never silent about failing.")
