"""Recall that survives a different vocabulary.

The case this exists for was measured before it was built: asking
"quanto está em atraso?" of the demo vault returned NOTHING, because the notes
say "outstanding". Folding accents did not help — that is a different word,
not a different spelling.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The demo vault, always — these assertions are about ITS content.
# Without this the suite passes or fails depending on whatever
# JARVIS_VAULTS happens to point at today, which is not a test.
os.environ["JARVIS_DEMO"] = "1"



from agent import brain, embed, llm  # noqa: E402
from agent.vault import Vault  # noqa: E402

FAILURES = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  ' + str(detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)


vault = Vault.from_config()
print(f"vault    {len(vault.notes)} notas\n")

# ---------------------------------------------------------------------------
print("1. onde estamos: Ollama presente?")
# ---------------------------------------------------------------------------
print(f"  available  {embed.available()}")
print(f"  reason     {embed.reason()}")
check("ausente é reportado sem quebrar nada", embed.reason() is None or "Ollama" in embed.reason())
check("similar() devolve vazio sem Ollama, sem exceção",
      isinstance(embed.similar(vault, "qualquer coisa"), list))
check("index() é no-op sem Ollama", embed.index(vault) == 0 or embed.available())

# ---------------------------------------------------------------------------
print("\n2. o caso que falhava")
# ---------------------------------------------------------------------------
QUESTION = "quanto está em atraso?"

lexical = [h.note.id for h in vault.search(QUESTION, limit=8)]
print(f"  só BM25          {lexical or '[] <- a falha original'}")
check("BM25 sozinho continua não achando (é lexical, e está certo)", lexical == [])

t = time.time()
words = brain.expand(QUESTION)
print(f"  expansão ({time.time()-t:.1f}s)  {words}")
check("a expansão devolveu palavras", bool(words), str(words))
check("trouxe termo em inglês", any(w in " ".join(words).lower()
      for w in ("outstanding", "overdue", "unpaid", "late", "owed", "arrears")), str(words))

t = time.time()
found = brain.retrieve(vault, QUESTION)
print(f"  retrieve ({time.time()-t:.1f}s)   {len(found)} notas")
for n in found[:6]:
    print(f"      {n.title}  ({n.type})")
check("agora encontra alguma coisa", bool(found))
check("e alcança faturas ou o mapa do dinheiro",
      any(n.type == "invoice" or "money" in n.id or "payment" in n.id for n in found),
      [n.id for n in found[:3]])

# ---------------------------------------------------------------------------
print("\n3. uma pergunta que já funcionava não paga o custo extra")
# ---------------------------------------------------------------------------
EASY = "qual e a politica de deposito?"
before = [h.note.id for h in vault.search(EASY, limit=8)]
check("BM25 já resolve essa", len(before) >= brain.THIN, f"{len(before)} hits")

t = time.time()
found = brain.retrieve(vault, EASY)
took = time.time() - t
print(f"  retrieve em {took:.2f}s, {len(found)} notas")
check("sem chamada de modelo quando o BM25 basta", took < 1.5, f"{took:.2f}s")
check("continua achando a nota certa",
      any("deposit-policy" in n.id for n in found))

# ---------------------------------------------------------------------------
print("\n4. a expansão falha em silêncio")
# ---------------------------------------------------------------------------
real = llm.complete
llm.complete = lambda *a, **k: (_ for _ in ()).throw(llm.LLMFailed("modelo ocupado"))
check("expand() devolve [] quando o modelo cai", brain.expand("qualquer coisa") == [])
got = brain.retrieve(vault, EASY)
check("retrieve() ainda funciona pelo BM25", bool(got), f"{len(got)} notas")
llm.complete = lambda *a, **k: ("", {})
check("resposta vazia não vira termo", brain.expand("x") == [])
llm.complete = real

# ---------------------------------------------------------------------------
print("\n5. as citações continuam verificadas")
# ---------------------------------------------------------------------------
found = brain.retrieve(vault, QUESTION)
ids = {n.id for n in found}
check("tudo que voltou existe no índice", ids <= set(vault.notes), list(ids - set(vault.notes))[:3])
check("dentro do teto", len(found) <= brain.MAX_NOTES, len(found))

print()
if FAILURES:
    print(f"{len(FAILURES)} FALHOU: {FAILURES}")
    raise SystemExit(1)
print("OK — palavras, depois outras palavras, depois significado.")
