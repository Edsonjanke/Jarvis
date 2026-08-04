"""Eyes: a picture reaching the model, and nothing else reaching it.

A supplier's quote arrives as a WhatsApp photograph. A statement arrives as a
screenshot. A scan comes back empty from the text extractor. All of it was
invisible to JARVIS, and giving it eyes cost none of the isolation llm.py
defends: the picture travels inside the prompt on stdin, exactly like the
notes, with `--tools ""` still in place. Nothing on disk is opened.

Two things are pinned here. That the argv and stdin change shape correctly
when a picture is attached and not otherwise — and that what arrives over the
network is checked rather than believed, because the string ends up inside
JSON handed to a subprocess.

The last section makes one real call, because the whole feature is a claim
about a real binary and a mock would only prove the mock.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import demo  # noqa: E402
demo.ensure()

from agent import llm  # noqa: E402
from agent.main import _images  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  ' + str(detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)


def refuses(label: str, fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except (ValueError, llm.LLMFailed) as exc:
        check(label, True, str(exc)[:56])
    except Exception as exc:  # noqa: BLE001
        check(label, False, f"levantou {type(exc).__name__}: {exc}")
    else:
        check(label, False, "NÃO foi recusado")


# The smallest valid JPEG this test needs is not a real one — nothing decodes
# it. base64 validity is what the server checks, and that is what matters here.
TINY = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 200).decode()


def argv(images: bool):
    return llm._argv(Path("claude.exe"), [], "claude-opus-5", "medium", images=images)


def after(flag, args):
    return args[args.index(flag) + 1] if flag in args else None


# ---------------------------------------------------------------------------
print("1. sem imagem, nada muda")
# ---------------------------------------------------------------------------
a = argv(False)
check("--output-format json", after("--output-format", a) == "json")
check("nenhum --input-format", "--input-format" not in a)
check("--tools continua vazio", after("--tools", a) == "")
check("--strict-mcp-config continua lá", "--strict-mcp-config" in a)
check("stdin é o texto puro, como sempre foi",
      llm._stdin_for("qual a política?", None) == b"qual a pol\xc3\xadtica?\n")
check("e com lista vazia também", llm._stdin_for("oi", []) == b"oi\n")

# ---------------------------------------------------------------------------
print("\n2. com imagem, os dois formatos mudam juntos")
# ---------------------------------------------------------------------------
# The CLI refuses one without the other: "--input-format=stream-json requires
# output-format=stream-json". Measured against the real binary.
a = argv(True)
check("--input-format stream-json", after("--input-format", a) == "stream-json")
check("--output-format acompanha", after("--output-format", a) == "stream-json")
check("--tools SEGUE vazio — olhos não são permissão",
      after("--tools", a) == "", repr(after("--tools", a)))
check("--strict-mcp-config segue lá", "--strict-mcp-config" in a)
check("--no-session-persistence segue lá", "--no-session-persistence" in a)
check("--setting-sources segue vazio", after("--setting-sources", a) == "")

raw = llm._stdin_for("o que diz aqui?", [("image/jpeg", TINY)])
msg = json.loads(raw.decode("utf-8"))
check("stdin vira uma mensagem stream-json", msg.get("type") == "user")
blocks = msg["message"]["content"]
check("com o texto primeiro", blocks[0] == {"type": "text", "text": "o que diz aqui?"})
check("e a imagem depois", blocks[1]["type"] == "image")
check("como base64, com o tipo declarado",
      blocks[1]["source"]["type"] == "base64"
      and blocks[1]["source"]["media_type"] == "image/jpeg")
check("os bytes chegam intactos", blocks[1]["source"]["data"] == TINY)

many = llm._stdin_for("x", [("image/png", TINY)] * (llm.MAX_IMAGES + 3))
check("o teto de imagens corta",
      len(json.loads(many)["message"]["content"]) == llm.MAX_IMAGES + 1)

# ---------------------------------------------------------------------------
print("\n3. o que chega pela rede é conferido, não acreditado")
# ---------------------------------------------------------------------------
check("sem imagens, lista vazia", _images({}) == [])
check("images vazio, lista vazia", _images({"images": []}) == [])
check("uma boa passa",
      _images({"images": [{"media_type": "image/png", "data": TINY}]})
      == [("image/png", TINY)])

refuses("images que não é lista", _images, {"images": "uma string"})
refuses("item que não é objeto", _images, {"images": ["só texto"]})
refuses("tipo não permitido (svg pode conter script)", _images,
        {"images": [{"media_type": "image/svg+xml", "data": TINY}]})
refuses("tipo ausente", _images, {"images": [{"data": TINY}]})
refuses("dado que não é base64", _images,
        {"images": [{"media_type": "image/png", "data": "isto não é base64 !!!"}]})
refuses("imagem vazia", _images, {"images": [{"media_type": "image/png", "data": ""}]})
refuses("imagens demais", _images,
        {"images": [{"media_type": "image/png", "data": TINY}] * (llm.MAX_IMAGES + 1)})

big = base64.b64encode(b"0" * (llm.MAX_IMAGE_BYTES + 10)).decode()
refuses("acima do teto de tamanho", _images,
        {"images": [{"media_type": "image/jpeg", "data": big}]})

# The type is checked twice on purpose — at the edge and again at the pipe.
refuses("e o tipo é conferido de novo antes do subprocesso",
        llm._stdin_for, "x", [("image/svg+xml", TINY)])

# ---------------------------------------------------------------------------
print("\n4. as duas formas de saída são lidas")
# ---------------------------------------------------------------------------
one = json.dumps({"type": "result", "is_error": False, "result": "olá"})
check("objeto único", llm._parse_output(one)["result"] == "olá")

stream = "\n".join([
    json.dumps({"type": "system", "subtype": "init"}),
    json.dumps({"type": "assistant", "message": {"content": []}}),
    json.dumps({"type": "result", "is_error": False, "result": "do stream"}),
])
check("newline-delimited", llm._parse_output(stream)["result"] == "do stream")
check("lixo entre as linhas não atrapalha",
      llm._parse_output("nao e json\n" + stream)["result"] == "do stream")
refuses("nada utilizável levanta LLMFailed", llm._parse_output, "sem json nenhum")

# ---------------------------------------------------------------------------
print("\n5. contra o binário de verdade")
# ---------------------------------------------------------------------------
# The claim is about a real CLI accepting a real picture. A mock here would
# assert only that the mock is correct.
if not llm.available():
    print("  SKIP  Claude Code não está disponível nesta máquina")
else:
    # A 2x2 red PNG, written by hand so the test needs nothing installed.
    import struct
    import zlib

    def chunk(tag, payload):
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\x00" + b"\xff\x00\x00" * 2 for _ in range(2))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(rows))
           + chunk(b"IEND", b""))

    try:
        text, usage = llm.complete(
            "Responda com UMA palavra, em português, minúscula.",
            "Qual é a cor predominante desta imagem?",
            images=[("image/png", base64.b64encode(png).decode())],
            effort="low")
        answer = text.strip().lower()
        check("o CLI aceitou a imagem e respondeu", bool(answer), answer[:40])
        check("e enxergou a cor certa", "verm" in answer or "red" in answer, answer[:40])
        check("com uso reportado", bool(usage.get("model")), usage.get("model"))
    except llm.LLMUnavailable as exc:
        print(f"  SKIP  {exc}")
    except llm.LLMFailed as exc:
        check("o CLI aceitou a imagem e respondeu", False, str(exc)[:90])

print()
if FAILURES:
    print(f"{len(FAILURES)} FALHOU: {FAILURES}")
    raise SystemExit(1)
print("OK — a imagem vai no prompt, conferida, e sem afrouxar nenhuma flag.")
