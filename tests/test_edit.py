"""Writing to your vault, and refusing to write anywhere else.

This is the most important file in the suite, and the reason is in your own
notes: the Evo-SI audit says there is no backup of anything. So a mistake here
has nowhere to be recovered from except the undo journal, which makes the
journal not a nicety but the backup itself.

Three properties, and every check below serves one of them:

  1. Nothing is written outside a configured root.
  2. Nothing is overwritten or deleted without a recoverable copy — and a
     write whose backup fails does not happen at all.
  3. Deleting asks, in every mode, including the permissive one.

Everything runs against a throwaway vault. Nothing here touches "IA OS".
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

from agent import data as data_mod, edit  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  ' + str(detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)


def refuses(label: str, fn, *args, **kwargs) -> None:
    """The operation must be refused, and refused as a rule, not as a crash."""
    try:
        fn(*args, **kwargs)
    except edit.Refused as exc:
        check(label, True, str(exc)[:64])
    except Exception as exc:  # noqa: BLE001
        check(label, False, f"levantou {type(exc).__name__} em vez de Refused: {exc}")
    else:
        check(label, False, "NÃO foi recusado")


SANDBOX = Path(tempfile.mkdtemp(prefix="jarvis-edit-"))
VAULT = SANDBOX / "vault"
OUTSIDE = SANDBOX / "fora"
VAULT.mkdir(parents=True)
OUTSIDE.mkdir(parents=True)
(OUTSIDE / "segredo.md").write_text("não toque nisto", encoding="utf-8")
(VAULT / "nota.md").write_text("conteúdo original\n", encoding="utf-8")

REAL_STATE = data_mod.state_dir
STATE = SANDBOX / "state"
STATE.mkdir()
data_mod.state_dir = lambda: STATE

os.environ["JARVIS_DEMO"] = "0"
os.environ["JARVIS_VAULTS"] = str(VAULT)


# A tripwire, not a check. The first version of this test set JARVIS_VAULTS to
# "" expecting that to mean "none" — data_mod.setting() treats empty as unset
# and fell through to .env, so a write landed in the real "IA OS" vault. The
# code was right; the fence had a hole. This closes it at the level below the
# fence: resolve() cannot return a path outside the sandbox no matter what the
# environment says, so a mistake in the setup fails the test instead of
# touching your documents.
_real_resolve = edit.resolve


def _caged(raw: str) -> Path:
    path = _real_resolve(raw)
    if SANDBOX.resolve() not in path.resolve().parents:
        raise AssertionError(
            f"O TESTE ESCAPOU DO SANDBOX: {path}\n"
            f"        (o cerco falhou, não o edit.py — conserte o teste)"
        )
    return path


edit.resolve = _caged

try:
    check("o vault de teste é o configurado",
          edit._roots() == [VAULT.resolve()], edit._roots())

    # -----------------------------------------------------------------------
    print("\n1. escrever dentro do vault")
    # -----------------------------------------------------------------------
    change = edit.write("nova.md", "criada pelo jarvis\n", note="teste")
    check("cria um arquivo novo", (VAULT / "nova.md").exists())
    check("com o conteúdo pedido",
          (VAULT / "nova.md").read_text(encoding="utf-8") == "criada pelo jarvis\n")
    check("registra que não havia nada antes", change.size_before == 0)
    check("e não guarda cópia do que não existia", change.backup == "")

    change2 = edit.write(str(VAULT / "nota.md"), "conteúdo NOVO\n")
    check("sobrescreve um existente",
          (VAULT / "nota.md").read_text(encoding="utf-8") == "conteúdo NOVO\n")
    check("guardando o anterior", bool(change2.backup), change2.backup)
    check("e o tamanho de antes", change2.size_before > 0, change2.size_before)

    # -----------------------------------------------------------------------
    print("\n2. fora do vault não se escreve")
    # -----------------------------------------------------------------------
    refuses("caminho absoluto fora", edit.write, str(OUTSIDE / "invadido.md"), "x")
    refuses("subindo com ..", edit.write, "../fora/invadido.md", "x")
    refuses("subindo várias vezes", edit.write, "../../../../invadido.md", "x")
    refuses("com contrabarra", edit.write, r"..\fora\invadido.md", "x")
    refuses("o .env do próprio JARVIS", edit.write, "../../.env", "x")
    refuses("caminho vazio", edit.write, "", "x")
    refuses("só espaços", edit.write, "   ", "x")
    check("o arquivo de fora continua intacto",
          (OUTSIDE / "segredo.md").read_text(encoding="utf-8") == "não toque nisto")
    check("e nada novo apareceu lá fora",
          sorted(p.name for p in OUTSIDE.iterdir()) == ["segredo.md"],
          sorted(p.name for p in OUTSIDE.iterdir()))

    # -----------------------------------------------------------------------
    print("\n3. só os tipos declarados")
    # -----------------------------------------------------------------------
    for bad in ("script.ps1", "app.exe", "pagina.html", "config.json", "planilha.xlsx",
                "nota.pdf", "sem_extensao"):
        refuses(f"{bad} é recusado", edit.write, bad, "x")
    check("nenhum deles foi criado",
          sorted(p.name for p in VAULT.iterdir()) == ["nota.md", "nova.md"],
          sorted(p.name for p in VAULT.iterdir()))

    # -----------------------------------------------------------------------
    print("\n4. um link simbólico não é uma saída")
    # -----------------------------------------------------------------------
    # resolve() judges where a path LANDS, not how it looks, so a link inside
    # the vault pointing out of it is caught. Windows needs privilege to make
    # one, so this reports honestly rather than passing by accident.
    link = VAULT / "atalho"
    try:
        link.symlink_to(OUTSIDE, target_is_directory=True)
        made = True
    except (OSError, NotImplementedError):
        made = False
    if made:
        refuses("escrever através de link que aponta pra fora",
                edit.write, str(link / "invadido.md"), "x")
        check("e o alvo continua limpo",
              sorted(p.name for p in OUTSIDE.iterdir()) == ["segredo.md"])
    else:
        print("       (pulado: esta máquina não deixou criar link simbólico)")

    # -----------------------------------------------------------------------
    print("\n5. desfazer restaura byte a byte")
    # -----------------------------------------------------------------------
    original = "linha 1\nlinha 2\nacentuação çãé\n"
    (VAULT / "undo.md").write_text(original, encoding="utf-8")
    before_bytes = (VAULT / "undo.md").read_bytes()

    c = edit.write("undo.md", "destruído\n")
    check("foi mesmo sobrescrito",
          (VAULT / "undo.md").read_text(encoding="utf-8") == "destruído\n")
    edit.undo(c.id)
    check("desfazer devolve os bytes exatos",
          (VAULT / "undo.md").read_bytes() == before_bytes)
    refuses("desfazer duas vezes é recusado", edit.undo, c.id)
    refuses("desfazer id desconhecido", edit.undo, "naoexiste")

    c = edit.write("efemera.md", "só pra existir\n")
    edit.undo(c.id)
    check("desfazer uma criação remove o arquivo",
          not (VAULT / "efemera.md").exists())

    # -----------------------------------------------------------------------
    print("\n6. apagar pede confirmação — em TODOS os modos")
    # -----------------------------------------------------------------------
    (VAULT / "apagar.md").write_text("existo\n", encoding="utf-8")
    for m in edit.MODES:
        edit.set_mode(m)
        refuses(f"no modo {m}, apagar sem confirmar", edit.remove, "apagar.md")
    check("o arquivo sobreviveu aos três modos", (VAULT / "apagar.md").exists())

    c = edit.remove("apagar.md", confirm=True)
    check("com confirmação, apaga", not (VAULT / "apagar.md").exists())
    check("guardando cópia", bool(c.backup))
    edit.undo(c.id)
    check("e desfazer traz de volta",
          (VAULT / "apagar.md").read_text(encoding="utf-8") == "existo\n")
    refuses("apagar o que não existe", edit.remove, "fantasma.md", confirm=True)
    edit.set_mode("manual")

    # -----------------------------------------------------------------------
    print("\n7. uma escrita sem cópia de segurança não acontece")
    # -----------------------------------------------------------------------
    # The rule that makes the journal trustworthy: if the previous bytes
    # cannot be saved, the file is left exactly as it was.
    guarded = VAULT / "guardado.md"
    guarded.write_text("valioso\n", encoding="utf-8")
    real_keep = edit._keep

    def broken(path, change_id):
        raise edit.Refused("disco cheio (simulado)")

    edit._keep = broken
    refuses("a escrita é recusada quando a cópia falha",
            edit.write, "guardado.md", "sobrescrito")
    edit._keep = real_keep
    check("e o arquivo não foi tocado",
          guarded.read_text(encoding="utf-8") == "valioso\n")

    # -----------------------------------------------------------------------
    print("\n8. tetos e modos")
    # -----------------------------------------------------------------------
    refuses("conteúdo acima do teto", edit.write, "gigante.md",
            "x" * (edit.MAX_WRITE_BYTES + 1))
    check("o gigante não foi criado", not (VAULT / "gigante.md").exists())

    check("o modo padrão é manual", edit.mode() == "manual", edit.mode())
    refuses("um modo inventado é recusado", edit.set_mode, "livre")
    check("e o modo continua o que era", edit.mode() == "manual")

    # -----------------------------------------------------------------------
    print("\n9. o que o painel mostra")
    # -----------------------------------------------------------------------
    info = edit.state()
    check("lista as mudanças", len(info["changes"]) > 0, len(info["changes"]))
    check("marca as desfeitas",
          any(c["undone"] for c in info["changes"]))
    check("diz onde pode escrever", info["roots"] == [str(VAULT.resolve())])
    check("e não expõe o caminho da cópia por acidente",
          all("backup" not in c for c in info["changes"]),
          [k for c in info["changes"] for k in c][:8])

    # -----------------------------------------------------------------------
    print("\n10. sem vault utilizável, nada é escrito")
    # -----------------------------------------------------------------------
    # NOT by setting JARVIS_VAULTS to "": data_mod.setting() treats empty as
    # "unset" and falls through to .env, which points at the real vault. The
    # first version of this test did exactly that and created a file in
    # "IA OS" — the accident this whole phase exists to prevent, caused by the
    # test rather than the code. Point it somewhere that does not exist.
    os.environ["JARVIS_VAULTS"] = str(SANDBOX / "pasta-que-nao-existe")
    data_mod.reload_env()
    check("o cerco continua de pé: nenhuma raiz utilizável",
          edit._roots() == [], edit._roots())
    refuses("sem pasta utilizável", edit.write, "qualquer.md", "x")
    os.environ["JARVIS_VAULTS"] = str(VAULT)
    data_mod.reload_env()
    check("e o cerco volta pro sandbox",
          edit._roots() == [VAULT.resolve()], edit._roots())

finally:
    edit.resolve = _real_resolve
    data_mod.state_dir = REAL_STATE
    os.environ.pop("JARVIS_VAULTS", None)
    shutil.rmtree(SANDBOX, ignore_errors=True)

print(f"\nnada fora de {SANDBOX} foi tocado")
if FAILURES:
    print(f"{len(FAILURES)} FALHOU: {FAILURES}")
    raise SystemExit(1)
print("OK — só dentro do vault, nunca sem cópia, e apagar sempre pergunta.")
