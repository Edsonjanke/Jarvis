"""web.py — olhar para fora, e voltar com a fonte e a data.

O briefing pedia seis ferramentas. Esta é a segunda, e era a única que nunca
existiu: *"research_web — look something up, then land it back on my numbers.
Not 'it costs $22' but 'that's £4 off your margin'."*

Cinco decisões que valem estar explicadas aqui:

1. **Só stdlib.** `urllib` e `html.parser`. O servidor do JARVIS não tem
   dependência nenhuma e não vai ganhar uma para fazer uma busca.

2. **Falhar em voz alta.** Raspar HTML de busca é frágil por natureza — o
   provedor muda o markup quando quer, sem aviso. Uma busca quebrada tem de
   levantar `WebUnavailable` com o motivo, **nunca** devolver lista vazia. Vazio
   silencioso lido em voz alta soa como "não existe nada sobre isso", que é uma
   afirmação, e falsa.

3. **Fontes em paralelo, a primeira válida ganha.** Mata a latência do fallback
   em série. Ideia vista no Mark L; implementação daqui.

   Uma correção medida, contra o que este arquivo dizia antes: os dois
   endpoints de HTML **não** são redundância real. Sob limite de taxa os dois
   devolvem a mesma página de bloqueio, byte por byte — eles dividem o mesmo
   portão anti-robô. A redundância que vale é a biblioteca `ddgs`, quando
   instalada, porque ela usa um cliente HTTP que se apresenta como navegador.
   Sem ela o JARVIS continua buscando; só fica mais fácil de barrar.

4. **Toda linha volta com `fetched_at`.** A guardrail do briefing diz: *"Never
   state a derived number without its qualifier."* Um preço de inox de três
   semanas atrás não é o preço de hoje, e quem responde precisa poder dizer
   quando aquilo foi lido.

5. **Página buscada é dado, nunca instrução.** O texto volta escapado e é
   entregue ao prompt dentro de uma cerca explícita. Um "ignore suas
   instruções" numa página é conteúdo a relatar, não ordem a cumprir.

Rode direto para ver funcionando:  python -m agent.web "inox 304 preço kg"
"""

from __future__ import annotations

import gzip
import html
import ipaddress
import json
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

if __package__ in (None, ""):  # allow `python agent/web.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Política
# ---------------------------------------------------------------------------

TIMEOUT = 12                 # segundos por requisição
RESULTS = 8                  # candidatos por busca, como o briefing sugere
PAGE_CHARS = 20_000          # teto do texto de uma página lida
SNIPPET_CHARS = 320

# Um User-Agent de navegador. `urllib` sem isto leva 403 na maioria dos sites,
# e o silêncio resultante pareceria "nada encontrado".
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

MODES = {
    "search":  "",
    "news":    "notícias ",
    "research": "",
    "price":   "preço ",
    "compare": "comparação ",
}


class WebUnavailable(RuntimeError):
    """A busca não aconteceu. Traz o motivo, para ser dito em voz alta."""


@dataclass
class Result:
    title: str
    url: str
    snippet: str
    source: str                       # qual endpoint respondeu
    fetched_at: str                   # ISO 8601, hora local

    @property
    def domain(self) -> str:
        """O domínio, para dizer de onde veio sem despejar a URL inteira."""
        return domain_of(self.url)

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title, "url": self.url, "snippet": self.snippet,
            "source": self.source, "fetched_at": self.fetched_at,
            "domain": self.domain,
        }


@dataclass
class Search:
    query: str
    mode: str
    results: list[Result] = field(default_factory=list)
    provider: str = ""
    seconds: float = 0.0
    tried: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query, "mode": self.mode, "provider": self.provider,
            "seconds": round(self.seconds, 2), "tried": self.tried,
            "results": [r.to_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# Rede
# ---------------------------------------------------------------------------

def domain_of(url: str) -> str:
    try:
        return urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return ""


def _is_private(host: str) -> bool:
    """O destino é uma máquina desta rede?

    Um resultado de busca é conteúdo de terceiro, e um `fetch` obediente a um
    link de terceiro é uma requisição que sai de dentro desta máquina. Sem esta
    checagem, uma página poderia mandar o JARVIS ler
    `http://127.0.0.1:8765/api/...` — a própria API dele — ou um endereço da
    rede local do Edson. Bloqueado antes de abrir o socket.
    """
    if not host:
        return True
    lowered = host.lower().rstrip(".")
    if lowered == "localhost" or lowered.endswith(".localhost") or lowered.endswith(".internal"):
        return True
    try:
        infos = socket.getaddrinfo(lowered, None)
    except socket.gaierror:
        return True                     # não resolve: não vale tentar
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return True
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return True
    return False


# Como a página de bloqueio se identifica. Medido: sob limite de taxa os dois
# endpoints devolvem 14 KB idênticos contendo `anomaly.js?...&cc=botnet`. Sem
# esta checagem o parser acha zero resultados e o motivo relatado seria
# "0 resultados no HTML" — que soa como "não existe nada sobre isso", uma
# afirmação diferente e falsa.
_BLOCKED_RE = re.compile(r"anomaly\.js|cc=botnet|/captcha|unusual traffic", re.I)


def _open(url: str, *, data: bytes | None = None, timeout: int = TIMEOUT) -> str:
    """GET/POST e devolve texto. Levanta WebUnavailable com o motivo."""
    if _is_private(domain_of(url)):
        raise WebUnavailable(f"destino recusado (endereço interno): {domain_of(url) or url}")

    request = urllib.request.Request(
        url, data=data,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            # Só gzip: urllib não descomprime sozinho, e br/zstd não têm
            # decodificador na stdlib. Pedir o que não sabemos ler devolve
            # bytes ilegíveis que pareceriam uma página vazia.
            "Accept-Encoding": "gzip",
        },
        method="POST" if data else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            if response.headers.get("Content-Encoding", "").lower() == "gzip":
                raw = gzip.decompress(raw)
            charset = response.headers.get_content_charset() or "utf-8"
            page = raw.decode(charset, "replace")
            if _BLOCKED_RE.search(page[:20_000]):
                raise WebUnavailable(
                    f"{domain_of(url)} recusou a requisição como robô "
                    "(limite de taxa) — tente de novo em alguns minutos")
            return page
    except urllib.error.HTTPError as exc:
        raise WebUnavailable(f"{domain_of(url)} respondeu HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise WebUnavailable(f"{domain_of(url)} inacessível: {exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise WebUnavailable(f"{domain_of(url)} não respondeu em {timeout}s") from exc
    except OSError as exc:
        raise WebUnavailable(f"{domain_of(url)}: {exc}") from exc


def _unwrap(href: str) -> str:
    """Desembrulha o redirecionador do buscador para a URL real."""
    if href.startswith("//"):
        href = "https:" + href
    parts = urllib.parse.urlsplit(href)
    if "duckduckgo.com" in (parts.hostname or "") and parts.path.startswith("/l/"):
        target = urllib.parse.parse_qs(parts.query).get("uddg", [""])[0]
        if target:
            return urllib.parse.unquote(target)
    return href


# ---------------------------------------------------------------------------
# Dois parsers, porque são dois markups
# ---------------------------------------------------------------------------

class _HtmlResults(HTMLParser):
    """html.duckduckgo.com — links com class result__a / result__snippet."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, str]] = []
        self._grab = ""
        self._href = ""
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        classes = attr.get("class", "").split()
        if tag == "a" and "result__a" in classes:
            self._flush()
            self._grab, self._href = "title", _unwrap(attr.get("href", ""))
        elif "result__snippet" in classes:
            self._flush()
            self._grab = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if self._grab and tag in ("a", "div", "td", "span"):
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._grab:
            self._buf.append(data)

    def _flush(self) -> None:
        if not self._grab:
            return
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        self._buf = []
        if self._grab == "title" and text and self._href:
            self.rows.append({"title": text, "url": self._href, "snippet": ""})
        elif self._grab == "snippet" and text and self.rows:
            if not self.rows[-1]["snippet"]:
                self.rows[-1]["snippet"] = text[:SNIPPET_CHARS]
        self._grab = ""

    def close(self) -> None:      # noqa: D102
        self._flush()
        super().close()


class _LiteResults(HTMLParser):
    """lite.duckduckgo.com — tabela, links com class result-link."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, str]] = []
        self._in_link = False
        self._in_snippet = False
        self._href = ""
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        classes = attr.get("class", "").split()
        if tag == "a" and "result-link" in classes:
            self._in_link, self._href = True, _unwrap(attr.get("href", ""))
            self._buf = []
        elif tag == "td" and "result-snippet" in classes:
            self._in_snippet, self._buf = True, []

    def handle_endtag(self, tag: str) -> None:
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        if self._in_link and tag == "a":
            self._in_link = False
            if text and self._href:
                self.rows.append({"title": text, "url": self._href, "snippet": ""})
            self._buf = []
        elif self._in_snippet and tag == "td":
            self._in_snippet = False
            if text and self.rows and not self.rows[-1]["snippet"]:
                self.rows[-1]["snippet"] = text[:SNIPPET_CHARS]
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._in_link or self._in_snippet:
            self._buf.append(data)


def _provider_html(query: str) -> list[dict[str, str]]:
    body = urllib.parse.urlencode({"q": query, "kl": "br-pt"}).encode()
    parser = _HtmlResults()
    parser.feed(_open("https://html.duckduckgo.com/html/", data=body))
    parser.close()
    return parser.rows


def _provider_lite(query: str) -> list[dict[str, str]]:
    body = urllib.parse.urlencode({"q": query, "kl": "br-pt"}).encode()
    parser = _LiteResults()
    parser.feed(_open("https://lite.duckduckgo.com/lite/", data=body))
    parser.close()
    return parser.rows


def _provider_ddgs(query: str) -> list[dict[str, str]]:
    """A biblioteca `ddgs`, se estiver instalada.

    Importada aqui dentro, de propósito: o servidor do JARVIS roda com stdlib
    puro e não pode falhar ao subir porque um pacote opcional não existe. Sem
    a biblioteca este provedor simplesmente se retira, e os dois raspadores de
    HTML seguem tentando.
    """
    try:
        from ddgs import DDGS                              # noqa: PLC0415
    except ImportError as exc:
        raise WebUnavailable("ddgs não instalado") from exc

    try:
        rows = DDGS().text(query, region="br-pt", max_results=RESULTS)
    except Exception as exc:  # noqa: BLE001 — a biblioteca tem exceções próprias
        raise WebUnavailable(f"ddgs: {type(exc).__name__}: {exc}") from exc

    out: list[dict[str, str]] = []
    for row in rows or []:
        # Os nomes de campo mudaram entre versões; aceita os dois.
        url = str(row.get("href") or row.get("url") or "")
        title = str(row.get("title") or "")
        snippet = str(row.get("body") or row.get("description") or "")
        if url and title:
            out.append({"title": title, "url": url, "snippet": snippet[:SNIPPET_CHARS]})
    return out


# A biblioteca primeiro: é a que sobrevive ao portão anti-robô. Os raspadores
# ficam porque funcionam sem dependência nenhuma, que é o modo padrão daqui.
PROVIDERS = (("ddgs", _provider_ddgs), ("html", _provider_html), ("lite", _provider_lite))


# ---------------------------------------------------------------------------
# Busca
# ---------------------------------------------------------------------------

def search(query: str, mode: str = "search", *, limit: int = RESULTS) -> Search:
    """Busca em dois endpoints ao mesmo tempo; a primeira resposta válida vence.

    Levanta WebUnavailable se nenhum dos dois responder. Uma busca que
    devolvesse lista vazia em silêncio viraria "não há nada sobre isso" na
    resposta falada, e isso é uma afirmação que ninguém verificou.
    """
    query = (query or "").strip()
    if not query:
        raise WebUnavailable("busca sem termo")
    if mode not in MODES:
        mode = "search"

    phrase = MODES[mode] + query
    started = time.time()
    done: dict[str, object] = {}
    lock = threading.Lock()
    first = threading.Event()

    def run(name: str, fn) -> None:
        try:
            rows = fn(phrase)
        except WebUnavailable as exc:
            with lock:
                done.setdefault("errors", []).append(f"{name}: {exc}")  # type: ignore[union-attr]
            return
        except Exception as exc:  # noqa: BLE001 — um parser quebrado não derruba o outro
            with lock:
                done.setdefault("errors", []).append(f"{name}: markup inesperado ({exc})")  # type: ignore[union-attr]
            return
        if rows:
            with lock:
                if "rows" not in done:
                    done["rows"], done["who"] = rows, name
            first.set()
        else:
            with lock:
                done.setdefault("errors", []).append(f"{name}: 0 resultados no HTML")  # type: ignore[union-attr]

    threads = [threading.Thread(target=run, args=p, daemon=True, name=f"web-{p[0]}")
               for p in PROVIDERS]
    for thread in threads:
        thread.start()
    first.wait(timeout=TIMEOUT + 2)
    for thread in threads:                      # deixa o perdedor terminar de sair
        thread.join(timeout=0.4)

    rows = done.get("rows")
    errors = done.get("errors") or []
    if not rows:
        raise WebUnavailable(
            "a busca na web não respondeu — " + "; ".join(errors[:3])
            if errors else "a busca na web não respondeu")

    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    who = str(done.get("who", "?"))
    seen: set[str] = set()
    results: list[Result] = []
    for row in rows:                            # type: ignore[union-attr]
        url = row.get("url", "")
        key = url.split("#", 1)[0]
        if not url.startswith("http") or key in seen:
            continue
        seen.add(key)
        results.append(Result(
            title=html.unescape(row.get("title", ""))[:200],
            url=url,
            snippet=html.unescape(row.get("snippet", "")),
            source=f"duckduckgo/{who}",
            fetched_at=stamp,
        ))
        if len(results) >= limit:
            break

    return Search(query=query, mode=mode, results=results, provider=who,
                  seconds=time.time() - started,
                  tried=[name for name, _ in PROVIDERS])


# ---------------------------------------------------------------------------
# Ler uma página
# ---------------------------------------------------------------------------

class _Text(HTMLParser):
    """Texto visível. Descarta script, style e o resto do que não se lê."""

    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}
    BREAK = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
             "section", "article", "td"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag in self.BREAK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data)

    def text(self) -> str:
        joined = "".join(self.parts)
        joined = re.sub(r"[ \t\r\f\v]+", " ", joined)
        return re.sub(r"\n\s*\n\s*\n+", "\n\n", joined).strip()


def read(url: str, *, limit: int = PAGE_CHARS) -> dict[str, object]:
    """Texto de uma página, com a hora em que foi lida.

    O que volta é **dado**. Quem monta o prompt tem de cercá-lo como tal: uma
    instrução escrita dentro de uma página é conteúdo a relatar, não ordem a
    cumprir.
    """
    parser = _Text()
    parser.feed(_open(url))
    parser.close()
    body = parser.text()
    truncated = len(body) > limit
    return {
        "url": url,
        "domain": domain_of(url),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "chars": len(body),
        "truncated": truncated,
        "text": body[:limit] + ("\n[truncado]" if truncated else ""),
    }


def read_many(results: list[Result], *, count: int = 3,
              chars: int = 6_000) -> list[dict[str, object]]:
    """Abre as primeiras páginas em paralelo e devolve o texto de cada uma.

    Existe porque a busca sozinha não responde a pergunta que o Edson faz. Um
    snippet traz o título e a chamada; o preço por quilo está dentro da página.
    Medido: uma pesquisa de preço com oito snippets e nenhuma leitura fez o
    modelo dizer, corretamente, que não daria o número — a informação
    simplesmente não tinha chegado até ele.

    Falha de uma página não derruba as outras nem a resposta: volta com o motivo
    no lugar do texto, para a resposta poder dizer que aquela fonte não abriu.
    """
    chosen = results[:max(0, count)]
    out: list[dict[str, object]] = [{} for _ in chosen]
    lock = threading.Lock()

    def grab(index: int, item: Result) -> None:
        try:
            page = read(item.url, limit=chars)
        except WebUnavailable as exc:
            page = {"url": item.url, "domain": item.domain, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — uma página malformada é comum
            page = {"url": item.url, "domain": item.domain,
                    "error": f"{type(exc).__name__}: {exc}"}
        page["title"] = item.title
        with lock:
            out[index] = page

    threads = [threading.Thread(target=grab, args=(i, item), daemon=True,
                                name=f"web-read-{i}")
               for i, item in enumerate(chosen)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=TIMEOUT + 2)
    return [page for page in out if page]


# ---------------------------------------------------------------------------
# Linha de comando
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    args = sys.argv[1:]
    mode = "search"
    if args and args[0].lstrip("-") in MODES:
        mode = args.pop(0).lstrip("-")
    query = " ".join(args).strip()
    if not query:
        print("uso: python -m agent.web [--news|--price|--compare] <termo>")
        return 2

    try:
        found = search(query, mode)
    except WebUnavailable as exc:
        print(f"\n  INDISPONÍVEL: {exc}\n")
        return 1

    print(f"\n  {found.provider} respondeu em {found.seconds:.1f}s "
          f"— {len(found.results)} resultados, modo {found.mode}\n")
    for i, item in enumerate(found.results, 1):
        print(f"  {i:>2}. {item.title[:74]}")
        print(f"      {item.domain}  lido {item.fetched_at}")
        if item.snippet:
            print(f"      {item.snippet[:150]}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
