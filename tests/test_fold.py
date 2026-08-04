"""Accent folding in the index.

Before this, a dictated question failed while the same question typed without
accents worked — because scribe_v1 spells "depósito" correctly and the prefix
matcher that reaches "deposit" cannot see past the "ó". Both spellings must now
reach the same notes, and English search must be untouched.
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



from agent.vault import STOPWORDS, Vault, _fold  # noqa: E402

FAILURES = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        FAILURES.append(label)


print("1. the fold itself")
for raw, want in [("Depósito", "deposito"), ("peças", "pecas"), ("BRAÇO", "braco"),
                  ("Não", "nao"), ("ação", "acao"), ("Orçamento", "orcamento"),
                  ("plain", "plain"), ("", "")]:
    got = _fold(raw)
    check(f"{raw!r} -> {got!r}", got == want, "" if got == want else f"wanted {want!r}")

print("\n2. length is preserved (the snippet slices the original with these offsets)")
for raw in ["Depósito de 40%", "peças que o Paulo desenhou", "ASCII only",
            "Ação, coração e não", "Straße", "ﬁ ligature"]:
    got = _fold(raw)
    check(f"len({raw[:24]!r})", len(got) == len(raw), f"{len(raw)} -> {len(got)}")

print("\n3. accented Portuguese stopwords still stop")
for word in ["nao", "esta", "voce", "tambem", "sao", "so", "ja", "ha"]:
    check(f"{word!r} is a stopword", word in STOPWORDS)

print("\n4. against the real vault")
vault = Vault.from_config()
print(f"  indexed {len(vault.notes)} notes")

# The invariant is that the two spellings agree. Whether either finds anything
# is a separate question: search is lexical, so a Portuguese word only reaches
# an English note when they are cognates ("política"/"policy").
pairs = [
    ("qual é a política de depósito?", "qual e a politica de deposito?", True),
    ("as peças estão em produção?", "as pecas estao em producao?", False),
    ("quanto está em atraso?", "quanto esta em atraso?", False),
]
for accented, plain, expect_hits in pairs:
    a = [h.note.id for h in vault.search(accented, limit=5)]
    p = [h.note.id for h in vault.search(plain, limit=5)]
    print(f"\n  accented {accented!r}")
    print(f"    -> {a[:3]}")
    print(f"  plain    {plain!r}")
    print(f"    -> {p[:3]}")
    check("both spellings agree", a == p, "" if a == p else "they diverge")
    if expect_hits:
        check("a cognate question reaches the English notes", bool(a))

print("\n5. English search is untouched")
for query, expect in [("deposit policy", "deposit-policy"),
                      ("late payment", "late-payment"),
                      ("invoice", "inv-")]:
    hits = [h.note.id for h in vault.search(query, limit=5)]
    check(f"{query!r} still finds {expect!r}",
          any(expect in h for h in hits), f"top: {hits[:2]}")

print("\n6. snippets still line up with the text they came from")
for hit in vault.search("depósito", limit=3):
    snippet = hit.snippet.strip("… ")
    check(f"snippet of {hit.note.title[:28]!r} is real text",
          snippet[:40] in " ".join(hit.note.text.split()) or not snippet,
          f"{snippet[:48]!r}")

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {FAILURES}")
    raise SystemExit(1)
print("OK — accents fold, lengths hold, English unchanged.")
