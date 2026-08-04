"""A POST must never leave anything in the socket.

This exists because it happened. The Reindexar button posts a two-byte body,
`/api/reindex` never read it, and the next request on that keep-alive
connection arrived as:

    {}GET /api/health HTTP/1.1     ->  501 Unsupported method ('{}GET')

One unread body, and the page falls over. The fix drains every POST body in
do_POST before dispatching, so no handler can forget. The test speaks raw HTTP
on one socket, because that is the only way to see the bug at all — urllib
opens a fresh connection per request and would pass either way.

Needs a running server:  python -m agent.main
"""

from __future__ import annotations

import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import data as data_mod  # noqa: E402

HOST = data_mod.setting("JARVIS_HOST", "127.0.0.1")
PORT = int(data_mod.setting("JARVIS_PORT", "8765"))
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  ' + str(detail) if detail else ''}")
    if not ok:
        FAILURES.append(label)


def request(sock: socket.socket, method: str, path: str, body: str = "",
            *, origin: str | None = None, ctype: str = "application/json") -> str:
    """One request on an existing socket. Returns the status line."""
    raw = body.encode("utf-8")
    head = (
        f"{method} {path} HTTP/1.1\r\n"
        f"Host: {HOST}:{PORT}\r\n"
        f"Origin: {origin if origin is not None else f'http://{HOST}:{PORT}'}\r\n"
        f"Content-Type: {ctype}\r\n"
        f"Content-Length: {len(raw)}\r\n"
        f"Connection: keep-alive\r\n\r\n"
    ).encode("ascii")
    sock.sendall(head + raw)

    # Headers, then exactly as many body bytes as declared — reading more
    # would consume the NEXT response and hide the very bug this is for.
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise AssertionError("server closed the connection mid-response")
        buf += chunk
    head_bytes, _, rest = buf.partition(b"\r\n\r\n")
    headers = head_bytes.decode("latin-1")
    status = headers.splitlines()[0]

    length = 0
    for line in headers.splitlines()[1:]:
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    while len(rest) < length:
        rest += sock.recv(4096)
    return status


def read_allowed() -> list[str]:
    """What the model is currently permitted to call, on a fresh connection.

    Fresh on purpose: the whole question is whether something reached the
    server through a poisoned one, so asking down that same socket would be
    asking the suspect.
    """
    import json
    import urllib.request

    with urllib.request.urlopen(f"http://{HOST}:{PORT}/api/tools", timeout=30) as res:
        return list(json.loads(res.read()).get("allowed") or [])


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    try:
        sock = socket.create_connection((HOST, PORT), timeout=180)
    except OSError as exc:
        print(f"  SKIP  o servidor não está de pé em {HOST}:{PORT} — {exc}")
        print("        suba com: python -m agent.main")
        return 0

    with sock:
        print("1. o caso exato que quebrou: reindex e depois qualquer coisa")
        first = request(sock, "POST", "/api/reindex", "{}")
        check("o reindex responde", "200" in first, first)
        second = request(sock, "GET", "/api/health")
        check("a requisição SEGUINTE na mesma conexão não é lixo",
              "200" in second, second)
        check("e não é o 501 de antes", "501" not in second, second)

        print("\n2. um corpo ignorado por outra rota qualquer")
        # /api/reindex is not special — any route that skips the body would
        # have done this. Two more, with bodies they have no use for.
        for route in ("/api/reindex", "/api/tools"):
            body = '{"allowed": []}' if route == "/api/tools" else '{"lixo": 1}'
            request(sock, "POST", route, body)
            after = request(sock, "GET", "/api/health")
            check(f"depois de POST {route} a conexão continua sã",
                  "200" in after, after)

        print("\n3. um corpo grande também é drenado, não abandonado")
        big = '{"q": "' + "x" * 4000 + '"}'
        request(sock, "POST", "/api/reindex", big)
        check("corpo de 4 kB não sobra no socket",
              "200" in request(sock, "GET", "/api/health"))

        print("\n4. corpo inválido é recusado sem envenenar a conexão")
        bad = request(sock, "POST", "/api/tools", "isto nao e json")
        check("JSON inválido vira 400", "400" in bad, bad)
        check("e a conexão sobrevive a ele",
              "200" in request(sock, "GET", "/api/health"))

        bad = request(sock, "POST", "/api/tools", '["uma lista, nao um objeto"]')
        check("lista no lugar de objeto vira 400", "400" in bad, bad)
        check("e a conexão sobrevive a ela",
              "200" in request(sock, "GET", "/api/health"))

    print("\n5. o mesmo mecanismo, usado pra contornar o guard")
    #
    # O guard recusa um POST de outro site com 403. Se ele recusar SEM ler o
    # corpo, os bytes ficam no socket e o parser lê os seguintes como uma
    # requisição nova — com os cabeçalhos que o atacante escreveu, Host e
    # Origin inclusive. O guard aprova, porque está lendo o que o atacante
    # mandou. Isso reabre exatamente a falha que o guard existe pra fechar:
    # uma aba qualquer da web gastando a assinatura.
    #
    # application/json exigiria preflight, que este servidor não responde.
    # text/plain é requisição simples e não exige — então é assim que a
    # tentativa chega de verdade.
    before = read_allowed()
    check("nada ligado antes de tentar", before == [], before)

    smuggled_body = '{"allowed": ["mcp__contrabandeado"]}'
    smuggled = (
        "POST /api/tools HTTP/1.1\r\n"
        f"Host: {HOST}:{PORT}\r\n"
        f"Origin: http://{HOST}:{PORT}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(smuggled_body)}\r\n"
        "Connection: keep-alive\r\n\r\n" + smuggled_body
    )

    with socket.create_connection((HOST, PORT), timeout=60) as evil:
        status = request(evil, "POST", "/api/reindex", smuggled,
                         origin="https://evil.example", ctype="text/plain")
        check("o POST de outro site é recusado", "403" in status, status)
        try:
            second = request(evil, "GET", "/api/health")
        except (AssertionError, OSError) as exc:
            second = f"(conexão morreu: {exc})"
        print(f"       resposta seguinte: {second}")

    after = read_allowed()
    check("a requisição contrabandeada NÃO foi executada",
          after == before, f"allowed={after}")

    # If it DID get through, this test just switched a tool on. Put it back —
    # a test that leaves the machine less safe than it found it is a liability,
    # and this one is only ever run when something is already suspect.
    if after != before:
        from agent import tools
        tools.allow(before)
        print(f"       (estado restaurado: allowed={tools.allowed()})")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FALHOU: {FAILURES}")
        return 1
    print("OK — nenhum POST deixa resto no socket, nem o que foi recusado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
