"""Skills: how you work, as opposed to what is true.

The property that matters most here is not matching — it is that a skill which
cannot be used still shows up, carrying the reason. You wrote a file, you
believe an instruction is in effect; a silent drop makes that belief wrong and
gives you nothing to notice it by.

Second: skills go in the SYSTEM prompt, not the notes. They are rules, not
evidence, so they must never become citable. cited() only credits ids that
exist in the index and a skill has no id — this pins that down anyway, because
it is the guarantee the whole project rests on.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import demo  # noqa: E402
demo.ensure()

from agent import data as data_mod, skills  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  ' + str(detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)


REAL_ROOT = data_mod.ROOT
SANDBOX = Path(tempfile.mkdtemp(prefix="jarvis-skills-"))
data_mod.ROOT = SANDBOX
SKILLS = SANDBOX / "skills"
SKILLS.mkdir(parents=True)


def write(name: str, text: str) -> Path:
    path = SKILLS / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


try:
    # -----------------------------------------------------------------------
    print("1. uma habilidade boa é carregada e casa")
    # -----------------------------------------------------------------------
    write("cobranca.md",
          "---\nname: Cobrança\n"
          "description: cobrar fornecedor, boleto vencido, atraso, duplicata\n"
          "---\n\nConfira o borderô antes de cobrar.\n")

    loaded = skills.load()
    check("carregou", len(loaded) == 1, len(loaded))
    check("com o nome do frontmatter", loaded[0].name == "Cobrança", loaded[0].name)
    check("sem problema apontado", loaded[0].problem == "", loaded[0].problem)
    check("e o corpo sem o frontmatter",
          loaded[0].body.startswith("Confira"), loaded[0].body[:30])

    check("casa com a pergunta certa",
          [s.name for s in skills.relevant("preciso cobrar um boleto vencido")] == ["Cobrança"])
    check("acento não atrapalha (cobranca -> Cobrança)",
          [s.name for s in skills.relevant("como faço a cobranca?")] == ["Cobrança"])
    check("não casa com pergunta de outro assunto",
          skills.relevant("qual a arquitetura do banco de dados?") == [])

    body, names = skills.block("boleto vencido")
    check("o bloco traz o nome como título", "## Cobrança" in body)
    check("e o corpo", "borderô" in body)
    check("e diz quais entraram", names == ["Cobrança"], names)
    check("bloco vazio quando nada casa", skills.block("nada a ver") == ("", []))

    # -----------------------------------------------------------------------
    print("\n2. uma habilidade quebrada aparece, com o motivo")
    # -----------------------------------------------------------------------
    write("sem-descricao.md", "---\nname: Sem Descrição\n---\n\nInstruções aqui.\n")
    write("sem-corpo.md", "---\nname: Vazia\ndescription: alguma coisa\n---\n\n")
    write("sem-nada.md", "isto não tem frontmatter nenhum\n")

    loaded = {s.slug: s for s in skills.load()}
    check("todas as quatro são listadas", len(loaded) == 4, sorted(loaded))
    check("a sem description diz o porquê",
          "description" in loaded["sem-descricao"].problem,
          loaded["sem-descricao"].problem)
    check("a sem corpo diz o porquê",
          "instruções" in loaded["sem-corpo"].problem, loaded["sem-corpo"].problem)
    check("a sem frontmatter também", bool(loaded["sem-nada"].problem))

    check("mas nenhuma delas é usada",
          [s.name for s in skills.relevant("alguma coisa instruções")] == [],
          [s.name for s in skills.relevant("alguma coisa instruções")])

    problems = skills.state()["problems"]
    check("e o painel recebe os problemas", len(problems) == 3, problems)

    # -----------------------------------------------------------------------
    print("\n3. always entra sempre")
    # -----------------------------------------------------------------------
    write("tom.md", "---\nname: Tom\nalways: true\n---\n\nSeja direto.\n")
    names = [s.name for s in skills.relevant("qualquer coisa completamente sem relação")]
    check("entra numa pergunta que não casaria com nada", names == ["Tom"], names)
    check("e vem antes das que casaram por palavra",
          [s.name for s in skills.relevant("boleto vencido")][0] == "Tom",
          [s.name for s in skills.relevant("boleto vencido")])
    check("sem description não é problema quando é always",
          skills.load() and not [s for s in skills.load()
                                 if s.slug == "tom" and s.problem])

    # -----------------------------------------------------------------------
    print("\n4. os tetos existem, e pelo mesmo motivo que MAX_NOTES existe")
    # -----------------------------------------------------------------------
    for i in range(8):
        write(f"muitas{i}.md",
              f"---\nname: Muitas{i}\ndescription: fornecedor pagamento\n---\n\ncorpo {i}\n")
    chosen = skills.relevant("fornecedor pagamento")
    check("no máximo MAX_SKILLS entram",
          len(chosen) == skills.MAX_SKILLS, len(chosen))

    write("gigante.md",
          "---\nname: Gigante\ndescription: enorme\n---\n\n" + ("x " * 40_000))
    body, _ = skills.block("enorme")
    check("uma habilidade enorme é cortada",
          len(body) < skills.SKILL_CHARS + 500, len(body))
    check("e o corte é visível, não silencioso", "truncado" in body)

    # -----------------------------------------------------------------------
    print("\n5. skills/<nome>/SKILL.md também vale")
    # -----------------------------------------------------------------------
    write("orcamento/SKILL.md",
          "---\nname: Orçamento\ndescription: orçar peça, cotação, proposta\n---\n\n"
          "Sempre informe peso e material.\n")
    found = [s for s in skills.load() if s.slug == "orcamento"]
    check("a pasta com SKILL.md é lida", len(found) == 1)
    check("e o slug vem da pasta, não do arquivo",
          found and found[0].slug == "orcamento", found[0].slug if found else "")
    check("e casa normalmente",
          "Orçamento" in [s.name for s in skills.relevant("preciso fazer uma cotação")])

    # -----------------------------------------------------------------------
    print("\n6. instruções permanentes")
    # -----------------------------------------------------------------------
    check("sem arquivo, vazio", skills.instructions() == ("", []))

    (SANDBOX / "JARVIS.md").write_text(
        "# Regras\n\nResponda em português. Números sempre com a data.\n",
        encoding="utf-8")
    text, sources = skills.instructions()
    check("com arquivo, é lido", "português" in text, text[:40])
    check("e diz de onde veio", len(sources) == 1, sources)

    (SANDBOX / "JARVIS.md").write_text("y " * 20_000, encoding="utf-8")
    text, _ = skills.instructions()
    check("um JARVIS.md gigante é cortado",
          len(text) < skills.INSTRUCTIONS_CHARS + 500, len(text))
    check("com o corte visível", "truncado" in text)

    # -----------------------------------------------------------------------
    print("\n7. uma habilidade não vira citação")
    # -----------------------------------------------------------------------
    # cited() credits ids that exist in the index. A skill has no id, so this
    # cannot happen — asserted anyway, because it is the guarantee the whole
    # project rests on and it now has a new way to be broken.
    from agent import brain
    from agent.vault import Vault

    vault = Vault.from_config()
    real = next(iter(vault.notes))
    answer_text = (f"Segundo [{real}] e conforme a habilidade [Cobrança] e o "
                   f"[JARVIS.md], o valor é X.")
    credited = [c[0] for c in brain.cited(vault, answer_text, [real])]
    check("a nota real é creditada", credited == [real], credited)
    check("a habilidade não", "Cobrança" not in credited)
    check("o JARVIS.md também não", "JARVIS.md" not in str(credited))

finally:
    data_mod.ROOT = REAL_ROOT
    shutil.rmtree(SANDBOX, ignore_errors=True)

print(f"\nhabilidades reais intocadas: {REAL_ROOT / 'skills'}")
if FAILURES:
    print(f"{len(FAILURES)} FALHOU: {FAILURES}")
    raise SystemExit(1)
print("OK — carrega, casa, respeita os tetos, e uma quebrada aparece com o motivo.")
