"""History: what was asked, what came back, and being able to follow up.

The two properties that matter here are opposites of each other. It has to
keep everything faithfully — a turn you cannot find is a turn you did not
record — and it has to survive being written badly, because it is appended to
on every answer and a crash halfway through one line must not cost the rest.

Nothing here calls the model. The history is a file format and a search; the
Answer it stores is stood in for by a stub.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import demo  # noqa: E402
demo.ensure()

from agent import data as data_mod, notebook  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  ' + str(detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)


class Stub:
    """Stands in for brain.Answer — only to_dict() is ever used."""

    def __init__(self, question: str, answer: str, **extra):
        self.payload = {
            "kind": "ask", "question": question, "answer": answer,
            "citations": [{"id": "demo/notes/x.md", "title": "x", "type": "note"}],
            "considered": ["demo/notes/x.md"], "recalled": [],
            "usage": {"model": "claude-opus-5", "output_tokens": 42}, "seconds": 1.5,
        }
        self.payload.update(extra)

    def to_dict(self):
        return dict(self.payload)


# History lives in the repository next to memory/, so the real one must not be
# touched. Point ROOT at a throwaway for the whole run and put it back after.
REAL_ROOT = data_mod.ROOT
SANDBOX = Path(tempfile.mkdtemp(prefix="jarvis-history-"))
data_mod.ROOT = SANDBOX

try:
    # -----------------------------------------------------------------------
    print("1. um turno gravado volta")
    # -----------------------------------------------------------------------
    first = notebook.record(Stub("quanto tenho a pagar?", "R$ 14.862,96 em aberto."))
    check("record devolve um id", bool(first.id), first.id)
    check("e abre uma conversa", bool(first.thread), first.thread)
    check("o arquivo do mês existe", notebook._file_for(time.time()).exists())

    found = notebook.turns()
    check("turns() encontra", len(found) == 1, len(found))
    check("com a pergunta intacta", found[0].question == "quanto tenho a pagar?")
    check("com a resposta intacta", "14.862,96" in found[0].answer)
    check("com as citações", len(found[0].citations) == 1)
    check("e com o modelo que respondeu", found[0].model == "claude-opus-5", found[0].model)

    # -----------------------------------------------------------------------
    print("\n2. a conversa continua")
    # -----------------------------------------------------------------------
    second = notebook.record(
        Stub("e desses, quais são do PARINOX?", "R$ 6.226,95."), first.thread)
    check("o segundo turno fica na mesma conversa", second.thread == first.thread)

    line = notebook.thread(first.thread)
    check("a thread devolve os dois", len(line) == 2, len(line))
    check("na ordem de leitura, mais antigo primeiro",
          line[0].question.startswith("quanto"), [t.question[:18] for t in line])

    block = notebook.conversation_block(first.thread)
    check("o bloco do prompt tem as duas perguntas",
          "quanto tenho a pagar?" in block and "PARINOX" in block)
    check("e as respostas", "14.862,96" in block and "6.226,95" in block)
    check("uma thread desconhecida devolve vazio, sem quebrar",
          notebook.conversation_block("naoexiste") == "")
    check("thread vazia devolve vazio", notebook.conversation_block("") == "")

    # -----------------------------------------------------------------------
    print("\n3. respostas longas não estouram o prompt")
    # -----------------------------------------------------------------------
    long_thread = notebook.new_thread()
    notebook.record(Stub("pergunta longa", "x" * 20_000), long_thread)
    block = notebook.conversation_block(long_thread)
    check("a resposta é truncada", len(block) < notebook.ANSWER_IN_PROMPT + 500, len(block))
    check("e o corte é visível, não silencioso", "[…]" in block)

    # a thread only carries so many turns back
    many = notebook.new_thread()
    for i in range(notebook.THREAD_TURNS + 4):
        notebook.record(Stub(f"pergunta {i}", f"resposta {i}"), many)
    check("a thread para no teto",
          len(notebook.thread(many)) == notebook.THREAD_TURNS,
          len(notebook.thread(many)))
    check("e mantém as MAIS RECENTES",
          "pergunta 9" in notebook.conversation_block(many),
          notebook.conversation_block(many)[:40])

    # -----------------------------------------------------------------------
    print("\n4. busca")
    # -----------------------------------------------------------------------
    check("acha pela pergunta", len(notebook.turns(query="PARINOX")) == 1)
    check("sem diferenciar maiúscula", len(notebook.turns(query="parinox")) == 1)
    check("acha pela resposta", len(notebook.turns(query="6.226")) == 1)
    notebook.record(Stub("qual é a política de depósito?", "40% na assinatura."))
    check("acento não atrapalha (politica -> política)",
          len(notebook.turns(query="politica")) == 1,
          [t.question for t in notebook.turns(query="politica")])
    check("todas as palavras precisam bater",
          notebook.turns(query="PARINOX depósito") == [])
    check("o limite é respeitado", len(notebook.turns(limit=2)) == 2)

    # -----------------------------------------------------------------------
    print("\n5. uma linha quebrada não derruba as outras")
    # -----------------------------------------------------------------------
    # This is the entire reason the format is one JSON object per line: a
    # process killed mid-write costs you that record and nothing else.
    path = notebook._file_for(time.time())
    before = len(notebook.turns(limit=500))
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"id": "meio-escrito", "question": "cortou aqui')  # no newline
    notebook.record(Stub("depois do estrago", "ainda funciona"))
    after = notebook.turns(limit=500)
    check("os turnos anteriores continuam legíveis", len(after) >= before, len(after))
    check("e o gravado depois também",
          any(t.question == "depois do estrago" for t in after))
    check("a linha quebrada é ignorada, não vira turno",
          not any(t.id == "meio-escrito" for t in after))

    # -----------------------------------------------------------------------
    print("\n6. apagar")
    # -----------------------------------------------------------------------
    target = notebook.turns(query="depósito")[0]
    check("apaga um turno", notebook.forget(target.id) is True)
    check("e ele some", notebook.turns(query="depósito") == [])
    check("apagar o que não existe devolve False", notebook.forget("nao-existe") is False)

    left = len(notebook.turns(limit=500))
    gone = notebook.forget_thread(first.thread)
    check("apaga a conversa inteira", gone == 2, gone)
    check("e os dois somem", notebook.thread(first.thread) == [])
    check("sem levar os outros junto",
          len(notebook.turns(limit=500)) == left - 2, len(notebook.turns(limit=500)))

    # -----------------------------------------------------------------------
    print("\n7. o disco pode falhar, a resposta não se perde")
    # -----------------------------------------------------------------------
    data_mod.ROOT = Path(SANDBOX) / "nao" / "existe" / "\x00invalido"
    try:
        turn = notebook.record(Stub("com o disco quebrado", "a resposta ainda existe"))
        check("record não levanta exceção", True)
        check("e ainda devolve um turno utilizável", bool(turn.id) and bool(turn.thread))
    except Exception as exc:  # noqa: BLE001
        check("record não levanta exceção", False, f"{type(exc).__name__}: {exc}")
    data_mod.ROOT = SANDBOX

    # -----------------------------------------------------------------------
    print("\n8. um arquivo com lixo não é confundido com histórico")
    # -----------------------------------------------------------------------
    (SANDBOX / "history" / "2020-01.jsonl").write_text(
        '"uma string, não um objeto"\n[1,2,3]\nnão é json de jeito nenhum\n',
        encoding="utf-8")
    check("nada disso vira turno",
          all(t.when > 0 for t in notebook.turns(limit=500)))
    check("e a leitura não quebra", isinstance(notebook.turns(limit=500), list))

    # -----------------------------------------------------------------------
    print("\n9. o que o painel mostra")
    # -----------------------------------------------------------------------
    threads = notebook.threads()
    check("as conversas são listadas", len(threads) >= 1, len(threads))
    check("cada uma diz quantos turnos tem",
          all(int(t["turns"]) >= 1 for t in threads))
    check("e é nomeada pela primeira pergunta, não pela última",
          any(str(t["title"]).startswith("pergunta 0") for t in threads),
          [t["title"][:24] for t in threads])

    # the recorded shape has to survive a JSON round trip, since that is what
    # the route sends and the page reads
    sample = notebook.turns(limit=1)[0].to_dict()
    check("um turno é serializável pra rota",
          json.loads(json.dumps(sample))["id"] == sample["id"])
    for key in ("id", "thread", "when", "kind", "question", "answer",
                "citations", "usage", "model", "seconds"):
        if key not in sample:
            check(f"o turno traz {key}", False)
            break
    else:
        check("o turno traz tudo que a auditoria precisa", True, len(sample))

finally:
    data_mod.ROOT = REAL_ROOT
    shutil.rmtree(SANDBOX, ignore_errors=True)

print(f"\nhistórico real intocado: {(REAL_ROOT / 'history')}")
if FAILURES:
    print(f"{len(FAILURES)} FALHOU: {FAILURES}")
    raise SystemExit(1)
print("OK — grava, encontra, continua a conversa, e sobrevive a uma linha quebrada.")
