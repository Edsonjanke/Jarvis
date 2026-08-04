"""What the model is allowed to do.

The default has to stay exactly what it was before step 5 existed — that is
the guarantee llm.py's docstring makes, and it is the one worth breaking a
build over. The switched-on path is forced here because no one can reach it
by hand: neither Drive nor Notion is authenticated on this machine.
"""
import os
import json
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The demo vault, always, and built somewhere temporary — these
# assertions are about ITS content. Without this the suite passes or
# fails depending on wherever JARVIS_VAULTS points today, which is
# not a test. ensure() must run before anything from agent/ is
# imported, because data.py reads the setting at call time.
import demo  # noqa: E402
demo.ensure()



from agent import data as data_mod, llm, tools  # noqa: E402

FAILURES = []


def check(label, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  ' + str(detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)


def argv():
    return llm._argv(Path("claude.exe"), [], "claude-opus-5", "medium")


def after(flag, args):
    return args[args.index(flag) + 1] if flag in args else None


# Whatever is on this machine now is put back at the end.
STATE = data_mod.state_dir()
SAVED = {n: (STATE / n).read_text(encoding="utf-8") if (STATE / n).exists() else None
         for n in (tools.ALLOWED_FILE, tools.SERVERS_FILE)}


def restore():
    for name, text in SAVED.items():
        path = STATE / name
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(text, encoding="utf-8")
    # config_path() derives mcp-config.json from the servers file as a side
    # effect of building the argv, so putting the inputs back is not enough:
    # without this the run leaves a fake Notion server and a "Bearer prova"
    # sitting on disk. Found it there after a run, which is how this line
    # came to exist.
    (STATE / "mcp-config.json").unlink(missing_ok=True)
    tools.allow(tools.allowed())      # no cache to invalidate, but be explicit


try:
    # -----------------------------------------------------------------------
    print("1. o padrao e nada, e e identico ao que era antes do passo 5")
    # -----------------------------------------------------------------------
    tools.allow([])
    a = argv()
    check("--tools vazio", after("--tools", a) == "", repr(after("--tools", a)))
    check("--strict-mcp-config presente", "--strict-mcp-config" in a)
    check("nenhum --mcp-config", "--mcp-config" not in a)
    check("nenhum --permission-mode", "--permission-mode" not in a)
    check("--max-turns 1", after("--max-turns", a) == "1")
    check("enabled() e falso", tools.enabled() is False)
    check("--setting-sources continua vazio", after("--setting-sources", a) == "")
    check("--no-session-persistence continua la", "--no-session-persistence" in a)

    # -----------------------------------------------------------------------
    print("\n2. ligado, mas so o que foi nomeado")
    # -----------------------------------------------------------------------
    (STATE / tools.SERVERS_FILE).write_text(json.dumps({
        "notion": {"type": "http", "url": "https://mcp.notion.com/mcp",
                   "headers": {"Authorization": "Bearer prova"}},
    }), encoding="utf-8")
    tools.allow(["mcp__notion"])
    a = argv()
    check("--tools traz so o que foi nomeado", after("--tools", a) == "mcp__notion",
          repr(after("--tools", a)))
    check("--strict-mcp-config CONTINUA ligado", "--strict-mcp-config" in a)
    check("--mcp-config aponta pro nosso arquivo", "--mcp-config" in a)
    check("--permission-mode dontAsk", after("--permission-mode", a) == "dontAsk")
    check("--max-turns sobe (senao a ferramenta gasta o unico turno)",
          int(after("--max-turns", a)) > 1, after("--max-turns", a))

    written = json.loads(Path(after("--mcp-config", a)).read_text(encoding="utf-8"))
    check("o arquivo tem so o servidor que declaramos",
          list(written.get("mcpServers", {})) == ["notion"], list(written.get("mcpServers", {})))
    check("nada da maquina entrou junto", "claude_ai_Google_Drive" not in json.dumps(written))

    # -----------------------------------------------------------------------
    print("\n3. o que a pagina ve bate com o que o argv faz")
    # -----------------------------------------------------------------------
    s = tools.state()
    notion = next(x for x in s["servers"] if x["name"] == "notion")
    drive = next(x for x in s["servers"] if x["name"] == "drive")
    check("Notion aparece autenticado", notion["authenticated"] is True)
    check("Drive aparece NAO autenticado (nao ha token)", drive["authenticated"] is False)
    check("Drive diz o que falta", "OAuth" in drive["needs"], drive["needs"])
    check("state().allowed e o que foi pro --tools",
          ",".join(s["allowed"]) == after("--tools", a))
    check("cada servidor oferece um nome de ferramenta",
          all(x["tools"] == [f"mcp__{x['name']}"] for x in s["servers"]))

    # -----------------------------------------------------------------------
    print("\n4. o que chega pela rede nao vira argv")
    # -----------------------------------------------------------------------
    tools.allow(["mcp__notion --dangerously-skip-permissions", "  ", "bom",
                 "x" * 200, "tem espaco no meio"])
    kept = tools.allowed()
    check("argumento com espaco e recusado", kept == ["bom"], kept)
    check("nada com traco-traco sobreviveu",
          not any("--" in k for k in kept), kept)
    a = argv()
    check("--tools nunca vira uma flag solta",
          after("--tools", a) == "bom", repr(after("--tools", a)))

    tools.allow([])
    check("desligar volta pro padrao exato", after("--tools", argv()) == "" and
          "--mcp-config" not in argv() and after("--max-turns", argv()) == "1")

    # -----------------------------------------------------------------------
    print("\n5. arquivos corrompidos nao derrubam nada")
    # -----------------------------------------------------------------------
    (STATE / tools.ALLOWED_FILE).write_text("{isto nao e json", encoding="utf-8")
    (STATE / tools.SERVERS_FILE).write_text("[]", encoding="utf-8")
    check("allowlist ilegivel = nada ligado", tools.allowed() == [])
    check("servidores no formato errado = nenhum", tools.servers() == {})
    check("argv volta pro padrao seguro", after("--tools", argv()) == "")
finally:
    restore()

print(f"\nestado restaurado: allowed={tools.allowed()}")
if FAILURES:
    print(f"{len(FAILURES)} FALHOU: {FAILURES}")
    raise SystemExit(1)
print("OK — desligado por padrao, ligado so pelo nome, e nunca a config da maquina.")
