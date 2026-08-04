"""Serving a file off your disk, and nothing else off your disk.

/api/file hands back the actual document — the PDF of the invoice, not the
words JARVIS managed to pull out of it. That makes it the one route that
reads arbitrary bytes from the filesystem and writes them to a socket, so
the whole question is what it refuses.

The rule it enforces: the only thing a caller may supply is a note id. Not a
path, not a fragment of one. The path comes from the index. Anything not in
the index does not exist as far as this route is concerned — which is why the
traversal cases below are not clever, they are just ids that do not resolve.

Needs a running server:  python -m agent.main
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import data as data_mod  # noqa: E402

HOST = data_mod.setting("JARVIS_HOST", "127.0.0.1")
PORT = int(data_mod.setting("JARVIS_PORT", "8765"))
BASE = f"http://{HOST}:{PORT}"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  ' + str(detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)


def get(path: str) -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(BASE + path, headers={"Origin": BASE})
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return res.status, res.read(), dict(res.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def fetch_file(note_id: str) -> tuple[int, bytes, dict[str, str]]:
    return get("/api/file?id=" + urllib.parse.quote(note_id, safe=""))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    try:
        status, raw, _ = get("/api/graph")
    except OSError as exc:
        print(f"  SKIP  o servidor não está de pé em {BASE} — {exc}")
        print("        suba com: python -m agent.main")
        return 0

    nodes = json.loads(raw).get("nodes", [])
    if not nodes:
        print("  SKIP  o vault indexado está vazio, não há o que abrir")
        return 0

    ids = [n["id"] for n in nodes]
    pdfs = [i for i in ids if i.lower().endswith(".pdf")]
    texts = [i for i in ids if i.lower().endswith((".md", ".txt"))]

    # -----------------------------------------------------------------------
    print(f"1. o que está indexado abre  ({len(ids)} notas: {len(pdfs)} pdf, {len(texts)} texto)")
    # -----------------------------------------------------------------------
    if pdfs:
        status, body, headers = fetch_file(pdfs[0])
        check("um PDF do índice volta 200", status == 200, status)
        check("e é mesmo um PDF, não uma página de erro",
              body[:5] == b"%PDF-", body[:12])
        check("com o Content-Type certo",
              headers.get("Content-Type") == "application/pdf",
              headers.get("Content-Type"))
        check("inline, pro visor do navegador abrir em vez de baixar",
              (headers.get("Content-Disposition") or "").startswith("inline"),
              headers.get("Content-Disposition"))
        # A PDF can carry JavaScript. This response is a document, not the app.
        csp = headers.get("Content-Security-Policy") or ""
        check("com CSP que não deixa o documento executar nada",
              "script-src 'none'" in csp and "default-src 'none'" in csp, csp[:60])
        check("e nosniff", headers.get("X-Content-Type-Options") == "nosniff")
    else:
        print("       (nenhum PDF neste vault, pulando)")

    if texts:
        status, body, headers = fetch_file(texts[0])
        check("um .md/.txt do índice também abre", status == 200, status)
        check("servido como texto puro, nunca text/html",
              (headers.get("Content-Type") or "").startswith("text/plain"),
              headers.get("Content-Type"))

    # -----------------------------------------------------------------------
    print("\n2. o que NÃO está indexado não existe")
    # -----------------------------------------------------------------------
    for label, bad in (
        ("um id inventado", "isto/nao/existe.pdf"),
        ("um caminho absoluto", r"C:\Windows\win.ini"),
        ("o .env do próprio JARVIS", "../.env"),
        ("travessia com barras", "../../../../Windows/System32/drivers/etc/hosts"),
        ("travessia com contrabarras", r"..\..\..\.env"),
        ("id vazio", ""),
        ("um id só com pontos", "../"),
    ):
        status, body, _ = fetch_file(bad)
        ok = status in (400, 403, 404)
        check(f"{label} é recusado", ok, f"{status} {body[:70]}")

    # -----------------------------------------------------------------------
    print("\n3. um id real, mas de um tipo que não se serve")
    # -----------------------------------------------------------------------
    # Nothing else is indexable today, so this asserts the rule rather than
    # a live example: only the suffixes in FILE_TYPES are ever served.
    from agent.main import Handler

    served = set(Handler.FILE_TYPES)
    check("a lista servida é fechada e não inclui executáveis",
          not (served & {".exe", ".dll", ".ps1", ".bat", ".cmd", ".js", ".html"}),
          sorted(served))
    check("a UI oferece exatamente o que o servidor serve",
          {s.lstrip(".") for s in served} ==
          set(__import__("re").search(
              r'const OPENABLE = new Set\(\[([^\]]*)\]',
              (data_mod.ROOT / "ui" / "app.js").read_text(encoding="utf-8")
          ).group(1).replace('"', "").replace(" ", "").split(",")),
          sorted(served))

    # -----------------------------------------------------------------------
    print("\n4. o guard cobre esta rota como cobre as outras")
    # -----------------------------------------------------------------------
    # It serves your invoices. A page on the open web must not be able to read
    # one just because your browser has this open in another tab.
    target = (pdfs or texts or ids)[0]
    req = urllib.request.Request(
        BASE + "/api/file?id=" + urllib.parse.quote(target, safe=""),
        headers={"Origin": "https://evil.example"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            status = res.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    check("de outro site é 403, não o documento", status == 403, status)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FALHOU: {FAILURES}")
        return 1
    print("OK — só o que está no índice, só os tipos declarados, só desta página.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
