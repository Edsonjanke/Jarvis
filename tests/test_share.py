"""Taking a slice to another machine, without taking your bank statements.

Syncing the whole folder already works and needed no code. What needs code is
choosing, and the choice that matters is one:

    History quotes your notes back at you.

An answer about accounts payable contains your accounts payable. So the
default here is skills only, and this file exists mostly to pin that default
down — a future change that flips it would hand someone your finances without
anyone noticing.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import demo  # noqa: E402
demo.ensure()

from agent import data as data_mod, notebook, share, skills  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  ' + str(detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)


class Stub:
    def __init__(self, q, a):
        self.q, self.a = q, a

    def to_dict(self):
        return {"kind": "ask", "question": self.q, "answer": self.a,
                "citations": [], "considered": [], "recalled": [],
                "usage": {"model": "m"}, "seconds": 1.0}


REAL_ROOT = data_mod.ROOT
SANDBOX = Path(tempfile.mkdtemp(prefix="jarvis-share-"))
data_mod.ROOT = SANDBOX
OUT = SANDBOX / "pacote"

try:
    (SANDBOX / "skills").mkdir(parents=True)
    (SANDBOX / "skills" / "cobranca.md").write_text(
        "---\nname: Cobrança\ndescription: cobrar fornecedor\n---\n\nConfira o borderô.\n",
        encoding="utf-8")
    (SANDBOX / "skills" / "orcamento").mkdir()
    (SANDBOX / "skills" / "orcamento" / "SKILL.md").write_text(
        "---\nname: Orçamento\ndescription: orçar peça\n---\n\nPeso e material.\n",
        encoding="utf-8")
    (SANDBOX / "skills" / "quebrada.md").write_text(
        "---\nname: Quebrada\n---\n\nsem description\n", encoding="utf-8")
    (SANDBOX / "JARVIS.md").write_text("Responda em português.\n", encoding="utf-8")

    notebook.record(Stub("quanto tenho no banco?", "Saldo -R$ 6.226,72 no extrato."))
    notebook.record(Stub("e o pró-labore?", "R$ 4.000,00 em julho."))
    notebook.record(Stub("qual o prazo da PARINOX?", "30 dias."))

    # -----------------------------------------------------------------------
    print("1. o padrão NÃO leva o histórico")
    # -----------------------------------------------------------------------
    written = share.export(OUT)
    check("habilidades vão", len(written["skills"]) == 3, written["skills"])
    check("instruções vão", len(written["instructions"]) == 1)
    check("histórico NÃO vai", written["turns"] == 0, written["turns"])
    check("e nem a pasta dele é criada", not (OUT / "history").exists())

    everything = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                           for p in OUT.rglob("*") if p.is_file())
    check("nada de saldo bancário no pacote", "6.226,72" not in everything)
    check("nem de pró-labore", "pró-labore" not in everything.lower()
          and "4.000,00" not in everything)

    check("o plano também diz que não vai", share.plan()["turns"] == 0)

    # -----------------------------------------------------------------------
    print("\n2. o que foi levado é utilizável do outro lado")
    # -----------------------------------------------------------------------
    check("a habilidade simples veio", (OUT / "skills" / "cobranca.md").is_file())
    check("a de pasta veio inteira",
          (OUT / "skills" / "orcamento" / "SKILL.md").is_file())
    check("o JARVIS.md veio", (OUT / "JARVIS.md").is_file())
    check("com um LEIA-ME dizendo onde copiar", (OUT / "LEIA-ME.md").is_file())

    # The other side must load exactly what this side had.
    other = SANDBOX / "outra-maquina"
    other.mkdir()
    shutil.copytree(OUT / "skills", other / "skills")
    data_mod.ROOT = other
    names = sorted(s.name for s in skills.load())
    check("o outro JARVIS carrega as mesmas",
          names == ["Cobrança", "Orçamento", "Quebrada"], names)
    check("e reporta a quebrada como quebrada, não a esconde",
          any(s.problem for s in skills.load() if s.name == "Quebrada"))
    data_mod.ROOT = SANDBOX

    # -----------------------------------------------------------------------
    print("\n3. com --history vai, e com filtro vai só o pedido")
    # -----------------------------------------------------------------------
    out2 = SANDBOX / "com-historico"
    written = share.export(out2, history="")
    check("todos os turnos vão", written["turns"] == 3, written["turns"])

    lines = (out2 / "history" / "exported.jsonl").read_text(encoding="utf-8").splitlines()
    check("um objeto por linha", len(lines) == 3, len(lines))
    check("na ordem de leitura, mais antigo primeiro",
          json.loads(lines[0])["question"].startswith("quanto"),
          json.loads(lines[0])["question"][:22])

    out3 = SANDBOX / "so-parinox"
    written = share.export(out3, history="parinox")
    check("o filtro corta", written["turns"] == 1, written["turns"])
    text = (out3 / "history" / "exported.jsonl").read_text(encoding="utf-8")
    check("levou o que casou", "PARINOX" in text)
    check("e NÃO levou o saldo bancário", "6.226,72" not in text)
    check("nem o pró-labore", "4.000,00" not in text)

    # -----------------------------------------------------------------------
    print("\n4. o pacote é legível antes de ser mandado")
    # -----------------------------------------------------------------------
    # No archive, no encoding, no format to learn — that is what makes it
    # possible to check what you are handing over.
    check("tudo é texto simples",
          all(p.suffix in (".md", ".jsonl") for p in out3.rglob("*") if p.is_file()),
          sorted({p.suffix for p in out3.rglob("*") if p.is_file()}))
    check("o histórico é o mesmo jsonl que o JARVIS lê",
          all(json.loads(l).get("id") for l in
              (out3 / "history" / "exported.jsonl").read_text(encoding="utf-8").splitlines()))

finally:
    data_mod.ROOT = REAL_ROOT
    shutil.rmtree(SANDBOX, ignore_errors=True)

if FAILURES:
    print(f"\n{len(FAILURES)} FALHOU: {FAILURES}")
    raise SystemExit(1)
print("\nOK — habilidades por padrão, histórico só se você pedir, e tudo legível.")
