"""Exercise retrieval, context building and citation extraction without a key.

llm.complete is replaced by a stub that echoes back ids from the context, plus
one id that does not exist. A real note must survive; the invented one must be
dropped. That is the property that matters: a hallucinated citation can never
become a clickable chip.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The demo vault, always, and built somewhere temporary — these
# assertions are about ITS content. Without this the suite passes or
# fails depending on wherever JARVIS_VAULTS points today, which is
# not a test. ensure() must run before anything from agent/ is
# imported, because data.py reads the setting at call time.
import demo  # noqa: E402
demo.ensure()



from agent import brain, llm  # noqa: E402
from agent.vault import Vault  # noqa: E402

vault = Vault.from_config()
print(f"indexed {len(vault.notes)} notes\n")

# -- retrieval ---------------------------------------------------------------

QUESTION = "what is the deposit policy and how do we chase late payment?"
seeds = [h.note.id for h in vault.search(QUESTION, limit=brain.SEED_HITS)]
notes = brain.retrieve(vault, QUESTION)
block, considered = brain.context(notes)

print(f"BM25 seeds        {len(seeds)}")
print(f"after graph widen {len(notes)}")
print(f"fit in context    {len(considered)}  ({len(block):,} chars, cap {brain.CONTEXT_CHARS:,})")
added = [n for n in considered if n not in seeds]
print(f"pulled in by links only: {len(added)}")
for note_id in added[:5]:
    print(f"    {note_id}")
assert notes, "retrieval returned nothing"
assert len(block) <= brain.CONTEXT_CHARS, "context blew its budget"
assert all(f"[{n}]" in block for n in considered), "an id is missing from the context"

# -- citations ---------------------------------------------------------------

real_a, real_b = considered[0], considered[1]
FAKE = "demo/notes/this-note-does-not-exist.md"
reply = (
    f"Deposits are non-negotiable [{real_b}]. We chase at day 7 and day 21 "
    f"[{real_a}], which is also what the ledger shows [{FAKE}]."
)

cites = brain.cited(vault, reply, considered)
ids = [c[0] for c in cites]
print(f"\nmodel cited 3 ids, 1 invented -> {len(cites)} survived")
for note_id, title, note_type in cites:
    print(f"    {title}  ({note_type})  {note_id}")

assert FAKE not in ids, "an invented citation survived"
assert set(ids) == {real_a, real_b}, f"wrong citations: {ids}"
assert ids == [real_b, real_a], f"citations not in order of appearance: {ids}"

# -- empty input is refused before anything is spawned ----------------------

print()
for label, call, expected in (
    ("ask",  lambda: brain.ask(vault, "   "), "no question given"),
    ("plan", lambda: brain.plan(vault, ""), "no goal given"),
):
    try:
        call()
        raise AssertionError(f"{label} accepted an empty input")
    except llm.LLMFailed as exc:
        assert str(exc) == expected, exc
        print(f"{label:6} empty input refused: {exc}")

# -- a stubbed model, to prove the whole path end to end ---------------------

captured = {}


def fake_complete(system, user, **kwargs):
    captured["system"] = system
    captured["user"] = user
    body = user.split("NOTES", 1)[1]
    ids = [line[1:line.index("]")] for line in body.splitlines() if line.startswith("[")]
    return (f"Stubbed answer citing [{ids[1]}] and then [{ids[0]}].",
            {"model": "stub", "stop_reason": "end_turn", "truncated": False,
             "input_tokens": 1, "output_tokens": 2})


llm.complete = fake_complete
answer = brain.ask(vault, QUESTION)
payload = answer.to_dict()

print("\nend to end with a stubbed model:")
print(f"    kind        {payload['kind']}")
print(f"    considered  {len(payload['considered'])}")
print(f"    citations   {[c['title'] for c in payload['citations']]}")
assert payload["citations"], "no citations came through"
assert all(c["id"] in vault.notes for c in payload["citations"])
assert QUESTION in captured["user"], "the question never reached the prompt"

# No secret from .env may reach the prompt. Test with a value that is actually
# set — the ElevenLabs key — since ANTHROPIC_API_KEY is empty here.
from agent import data as data_mod  # noqa: E402

sent = captured["system"] + captured["user"]
for name in ("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"):
    secret = data_mod.setting(name)
    if secret:
        assert secret not in sent, f"{name} leaked into the prompt"
        print(f"    {name} present in .env, absent from the prompt")

print("\nOK — retrieval, budget, citation verification and the full path.")
