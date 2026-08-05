"""browse.py — um navegador de verdade, com a sessão do Edson dentro.

Por que existe: a pesquisa em `web.py` lê HTML cru com `urllib`. Isso não roda
JavaScript e não tem sessão, e foi contra esses dois muros que ela bateu —
página de preço montada por JS chega vazia, e marketplace brasileiro esconde
preço atrás de "acesse sua conta". Um navegador resolve os dois.

E resolve trazendo um risco que o `urllib` não tinha: aqui ele navega
**autenticado como o Edson**, num perfil que guarda os logins dele. Uma página
com injeção deixa de ser um texto a relatar e passa a ser uma tentativa de
mandar um navegador logado fazer algo. O desenho abaixo é toda a resposta a
isso.

## A etiqueta, não o portão

O briefing tinha duas regras absolutas separadas: *"Never send"* e *"Never
spend"*. O Edson derrubou as duas, nomeando-as — primeiro `pode liberar o
send`, depois `sim libera tudo`. Então nada aqui bloqueia.

Mas classificar continua, porque a classificação virou **etiqueta de diário**
em vez de muralha. Toda operação é rotulada antes de acontecer, e o rótulo fica
gravado:

| classe | o que é | política |
|---|---|---|
| `read` | abrir URL, ler texto, listar links, screenshot | livre |
| `send` | clicar, preencher, submeter, teclar | liberado |
| `spend` | finalizar compra, pagar, confirmar pedido, assinar | liberado, **marcado** |
| `secret` | qualquer campo de senha | não acontece — ver abaixo |

`spend` sobrevive como rótulo porque "o que este navegador andou fazendo com meu
dinheiro" é uma pergunta que você vai querer responder por leitura de log, e
não por releitura de toda a navegação.

`secret` não é uma regra minha sobrevivendo à liberação: o JARVIS **não tem** as
senhas do Edson. Não há o que digitar. Liberar isso desbloquearia zero, a menos
que credencial fosse guardada em arquivo — outra feature, não pedida. O perfil
persistente é a resposta: ele loga uma vez, na janela, e a sessão fica em disco.

## O que sobra protegendo

Com os portões abertos, o que resta não são barreiras — são retrovisores:

1. **A janela é visível por padrão.** Um navegador headless agindo logado como
   você, sem janela, é a versão assustadora disto. Visível, você vê e fecha.
2. **Tudo vai para um diário**, como em `edit.py`: o que foi feito, onde,
   quando, e de que classe. Uma ação que você não pediu fica gravada.
3. **Conteúdo de página é dado, nunca instrução.** Isto não afrouxa. Uma página
   que diz "agora compre isto" é texto a relatar, e a liberação do Edson vale
   para pedidos *dele*, não para o que um site pede.

Rode direto:  python -m agent.browse ler https://example.com
"""

from __future__ import annotations

import atexit
import json
import queue
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

if __package__ in (None, ""):  # allow `python agent/browse.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod

PROFILE_DIR = "browser-profile"
JOURNAL = "browse/journal.jsonl"

PAGE_CHARS = 20_000
NAV_TIMEOUT = 25_000        # ms
ACT_TIMEOUT = 10_000        # ms

# Gasto. Liberado pelo Edson — o padrão existe para *rotular* o diário, não
# para barrar. Heurística de texto erra nas duas direções; como etiqueta um
# falso positivo custa uma linha de log a mais, e não uma ação recusada.
SPEND_RE = re.compile(
    r"finalizar\s+(compra|pedido)|fechar\s+pedido|ir\s+para\s+o?\s*pagamento"
    r"|confirmar\s+(pedido|compra|pagamento|assinatura)|pagar\s+agora|pagar\b"
    r"|comprar\s+agora|comprar\b|assinar\s+(agora|plano)?"
    r"|checkout|place\s+order|buy\s+now|complete\s+purchase|subscribe\b"
    r"|adicionar\s+cart(ão|ao)|cart(ão|ao)\s+de\s+cr(é|e)dito",
    re.I,
)
SPEND_URL_RE = re.compile(
    r"/checkout|/pagamento|/payment|/carrinho/finaliz|/cart/checkout"
    r"|/pedido/confirm|/order/confirm|/assinatura|/subscribe"
    r"|mercadopago|pagseguro|stripe\.com|paypal\.com",
    re.I,
)

# Campo de senha, em qualquer forma que ele apareça.
SECRET_RE = re.compile(r"password|senha|passwd|\bpin\b|cvv|c(ó|o)digo\s*de\s*seguran", re.I)


class Refused(Exception):
    """A operação não foi permitida. Nunca um bug — sempre uma regra."""


@dataclass
class Action:
    id: str
    when: float
    kind: str              # read | send | spend | secret
    what: str              # goto | text | click | fill | press | shot
    target: str
    url: str
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "when": self.when, "kind": self.kind,
                "what": self.what, "target": self.target, "url": self.url,
                "ok": self.ok, "detail": self.detail}


# ---------------------------------------------------------------------------
# Intenção: quando "abre o youtube" é um comando e não uma pergunta
# ---------------------------------------------------------------------------
#
# Só pega imperativo no começo da frase. "abre o youtube" abre; "como faço para
# abrir o youtube" é pergunta e vai para o modelo, porque não começa com o verbo.
#
# Isto é lido **apenas** do que o Edson digitou ou falou. Nunca do conteúdo de
# uma nota, de um e-mail ou de uma página — senão uma linha escrita num arquivo
# ("abra este site e confirme") viraria uma ação, que é a injeção exata que o
# resto do sistema recusa.
# A palavra de acordo entra no texto, às vezes duas vezes.
#
# Ditado dá "Jarvis? Jarvis, abrir o YouTube" — foi o que o Edson mandou pelo
# microfone, e a intenção não casou porque o verbo não abria a frase. A regra
# está certa e não afrouxa: o vocativo é **removido** antes de olhar, e o verbo
# continua tendo de abrir o que sobra. "Jarvis, como faço para abrir o YouTube"
# segue sendo pergunta.
WAKE_RE = re.compile(
    r"^\s*(?:(?:ei|ô|oi|olá|ola|hey|ok|okay)\s+)?"
    r"(?:jarvis|jarves|jarvez|j[áa]rvis)\s*[,.!?:;–—-]*\s*",
    re.I,
)

OPEN_RE = re.compile(
    r"^\s*(?:por favor\s+)?"
    r"(?:abre|abrir|abra|abri|vai\s+(?:em|pra|para|no|na)|"
    r"navega(?:r)?\s+(?:para|pra|até|em)|entra\s+(?:em|no|na)|open|go\s+to)"
    r"\s+(?:o\s|a\s|no\s|na\s|em\s|para\s|pra\s|site\s+d[eoa]\s+|página\s+d[eoa]\s+)?"
    r"(.{2,120}?)\s*[.!?]?\s*$",
    re.I,
)

# Endereço já pronto, ou algo com cara de domínio.
URLISH_RE = re.compile(r"^(?:https?://|www\.)|^[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/|$)", re.I)

# Sites que o Edson vai pedir por nome, e que ninguém deve ter que digitar
# inteiros. Curta de propósito: uma lista longa começa a chutar.
SITES = {
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "conta azul": "https://app.contaazul.com",
    "contaazul": "https://app.contaazul.com",
    "mercado livre": "https://www.mercadolivre.com.br",
    "mercadolivre": "https://www.mercadolivre.com.br",
    "drive": "https://drive.google.com",
    "google drive": "https://drive.google.com",
    "agenda": "https://calendar.google.com",
    "calendario": "https://calendar.google.com",
    "calendário": "https://calendar.google.com",
    "notion": "https://www.notion.so",
    "github": "https://github.com",
    "linkedin": "https://www.linkedin.com",
    "chatgpt": "https://chat.openai.com",
    "claude": "https://claude.ai",
}


def _dewake(text: str) -> str:
    """A frase sem o vocativo que o microfone cola na frente."""
    said = text or ""
    # Duas vezes no máximo: o microfone repete o acordo ("Jarvis? Jarvis, ..."),
    # mas um laço sem teto deixaria "jarvis jarvis jarvis" comer a frase inteira.
    for _ in range(2):
        stripped = WAKE_RE.sub("", said, count=1)
        if stripped == said:
            break
        said = stripped
    return said


# "pesquisar playlist de rock no youtube" — buscar **dentro** de um site.
#
# Diferente de abrir. `abre o youtube` põe a home na tela; isto põe o resultado.
# O verbo abre a frase pelo mesmo motivo de sempre, e o site vem no fim, depois
# de "no"/"na"/"em".
SEARCH_RE = re.compile(
    r"^\s*(?:pesquis\w*|busc\w*|procur\w*|search|acha[r]?)\s+(?:por\s+)?"
    r"(.+?)\s+(?:n[oa]s?|em|dentro\s+d[eoa]|no\s+site\s+d[eoa])\s+"
    r"([\w .\-]{2,40}?)\s*[.!?]?\s*$",
    re.I,
)

# Endereço de busca de cada site, quando ele é conhecido.
#
# Montar a URL é muito mais confiável do que dirigir a caixa de busca na tela:
# não depende de rótulo, de layout nem de banner de cookie na frente. Estes são
# endereços públicos e estáveis, não chutes — onde eu não souber, o código cai
# para preencher o campo de busca da própria página.
SEARCH_URLS = {
    "https://www.youtube.com": "https://www.youtube.com/results?search_query={q}",
    "https://www.google.com": "https://www.google.com/search?q={q}",
    "https://www.mercadolivre.com.br": "https://lista.mercadolivre.com.br/{q}",
    "https://github.com": "https://github.com/search?q={q}",
    "https://mail.google.com": "https://mail.google.com/mail/u/0/#search/{q}",
    "https://drive.google.com": "https://drive.google.com/drive/search?q={q}",
    "https://www.linkedin.com": "https://www.linkedin.com/search/results/all/?keywords={q}",
}


# Grafias que `.title()` estraga.
SPOKEN = {
    "youtube": "YouTube", "github": "GitHub", "linkedin": "LinkedIn",
    "chatgpt": "ChatGPT", "whatsapp": "WhatsApp", "whatsapp web": "WhatsApp",
    "contaazul": "Conta Azul", "mercadolivre": "Mercado Livre",
    "gmail": "Gmail", "notion": "Notion", "drive": "Google Drive",
    "google drive": "Google Drive", "mail": "Gmail", "app": "Conta Azul",
    "calendario": "Agenda", "calendário": "Agenda", "calendar": "Agenda",
    "lista": "Mercado Livre",
}


def site_label(url: str) -> str:
    """O nome do site como se fala, não como se digita.

    "YouTube", não "www.youtube.com". A regra é que endereço é para o olho e
    prosa é para o ouvido: a URL fica na tela, dentro de crase, e a frase falada
    carrega o nome. Ler um domínio em voz alta letra por letra é ruído.
    """
    base = (url or "").rstrip("/")
    for name, known in SITES.items():
        if known.rstrip("/") == base:
            # `.title()` quebra o maiúsculo do meio: "Youtube", "Github".
            # Estes têm grafia própria e ela é lida em voz alta.
            return SPOKEN.get(name, name.title())
    host = re.sub(r"^https?://(?:www\.)?", "", base).split("/")[0]
    return SPOKEN.get(host.split(".")[0], host.split(".")[0].title()) or host


def search_intent(text: str) -> tuple[str, str, str] | None:
    """(url de busca, site, termo) — ou None se não foi pedido de busca em site.

    Devolve url vazia quando o site é conhecido mas não tem endereço de busca
    mapeado: nesse caso quem chama abre o site e usa a caixa de busca dele, que
    é mais frágil e por isso é o segundo caminho, não o primeiro.
    """
    match = SEARCH_RE.match(_dewake(text))
    if not match:
        return None
    query = match.group(1).strip().strip("\"'“”")
    where = match.group(2).strip().lower().rstrip(".")

    site = SITES.get(where) or SITES.get(re.sub(r"\s+", "", where))
    if not site:
        if URLISH_RE.match(where):
            site = where if where.startswith("http") else f"https://{where}"
        else:
            return None          # não é um site que eu conheça: não é este caminho

    template = SEARCH_URLS.get(site.rstrip("/"), "")
    url = template.format(q=quote_plus(query)) if template else ""
    return url, site, query


def intent(text: str) -> str | None:
    """O que o Edson mandou abrir, ou None se não foi um comando de abrir.

    Devolve URL quando dá para resolver com certeza, ou o termo cru quando é um
    nome que ninguém conhece — nesse caso quem chama deve **buscar**, nunca
    montar `https://www.<palavra>.com`. Chutar domínio é inventar, e inventar é
    a única coisa que este assistente não tem licença para fazer.
    """
    match = OPEN_RE.match(_dewake(text))
    if not match:
        return None
    what = match.group(1).strip().strip("\"'“”")
    low = what.lower().rstrip("/")

    # "abre um resumo do mês" não é um site. Artigo indefinido e possessivo
    # denunciam substantivo comum, e mandar isso para a busca abriria a primeira
    # página aleatória sobre resumos — pior que não entender.
    if re.match(r"(?:um|uma|uns|umas|meu|minha|meus|minhas|algum|alguma)\s", low):
        return None

    if low in SITES:
        return SITES[low]
    # "you tube" é o que sai quando se fala, e foi o que o Edson digitou no
    # primeiro teste. Ditado e digitação separam palavras que o domínio junta,
    # então tenta de novo sem os espaços antes de desistir.
    squashed = re.sub(r"\s+", "", low)
    if squashed in SITES:
        return SITES[squashed]
    if URLISH_RE.match(low):
        return low if low.startswith("http") else f"https://{low}"
    return what          # nome desconhecido: quem chama busca


# ---------------------------------------------------------------------------
# Diário
# ---------------------------------------------------------------------------

def _journal_path() -> Path:
    path = data_mod.state_dir() / JOURNAL
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _log(action: Action) -> None:
    """Grava e nunca levanta: um diário que não escreve é uma linha perdida,
    não uma ação perdida — e a ação já aconteceu."""
    try:
        with _journal_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(action.to_dict(), ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"[browse] diário não gravou: {exc}", file=sys.stderr)


def history(limit: int = 100) -> list[Action]:
    try:
        lines = _journal_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[Action] = []
    for line in lines[-limit:]:
        try:
            row = json.loads(line)
            out.append(Action(**row))
        except (ValueError, TypeError):
            continue          # uma linha truncada não invalida o diário
    return out


# ---------------------------------------------------------------------------
# Classificação
# ---------------------------------------------------------------------------

def classify(what: str, target: str, url: str = "") -> str:
    """Que classe é esta operação? Chamada antes de tocar na página."""
    if what in ("goto", "text", "links", "shot"):
        # Navegar para uma URL de pagamento não gasta nada por si, mas é o
        # passo anterior, e o diário deve mostrá-lo como tal.
        return "spend" if (what == "goto" and SPEND_URL_RE.search(target)) else "read"
    if SECRET_RE.search(target):
        return "secret"
    if SPEND_RE.search(target) or SPEND_URL_RE.search(url):
        return "spend"
    return "send"


def _gate(kind: str) -> None:
    """A única coisa que ainda não passa. `send` e `spend` estão liberados.

    Sem parâmetro `confirm`: uma flag que nada consulta é mentira na assinatura.
    Quando o Edson quiser reapertar o `spend`, o portão volta aqui, num lugar.
    """
    if kind == "secret":
        raise Refused(
            "campo de senha: o JARVIS não tem suas credenciais, então não há o que "
            "digitar aqui. Faça o login você mesmo na janela — o perfil é "
            "persistente e a sessão fica guardada para as próximas vezes.")


# ---------------------------------------------------------------------------
# O navegador
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_state: dict[str, object] = {}

# Uma única thread toca no Playwright. Todas as outras mandam recado.
#
# Não é preferência de estilo, é a única forma que funciona: a API síncrona do
# Playwright é presa por greenlet à thread que a criou. O servidor é
# `ThreadingHTTPServer`, então cada requisição chega numa thread diferente, e a
# segunda chamada morria com `greenlet.error: cannot switch to a different
# thread (which happens to have exited)` — medido, não teorizado: a primeira
# leitura via HTTP voltou 403 e a segunda derrubou 500.
#
# O efeito colateral é bem-vindo: a fila serializa o navegador. Duas abas
# disputando o mesmo `page` seria pior que lento — seria clicar no lugar errado.
_jobs: "queue.Queue[tuple | None]" = queue.Queue()
_worker: threading.Thread | None = None
JOB_TIMEOUT = 180.0          # s — teto de uma operação, inclusive o Chrome subir


def _pump() -> None:
    """O laço da thread dona do navegador."""
    while True:
        job = _jobs.get()
        if job is None:
            return
        fn, box = job
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 — atravessa para quem pediu
            box["error"] = exc
        finally:
            box["done"].set()


# O navegador morreu debaixo de nós. Não é a mesma coisa que a página não abrir.
DEAD_RE = re.compile(
    r"has been closed|Target closed|browser has disconnected|Connection closed",
    re.I,
)


def _run(fn, *, heal: bool = True):
    """Executa `fn` na thread do navegador e devolve o resultado aqui.

    `heal`: quando o erro é "o navegador morreu", descarta os destroços e tenta
    **uma** vez com um navegador novo. Uma tentativa, não um laço: se o segundo
    também morre, o problema não é corrida e insistir só esconde a causa.
    """
    try:
        return _submit(fn)
    except Refused:
        raise                            # recusa é decisão, não falha
    except Exception as exc:
        if not heal or not DEAD_RE.search(str(exc)):
            raise
        _submit(_forget)
        return _submit(fn)


def _submit(fn):
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_pump, name="browse", daemon=True)
            _worker.start()
    box: dict[str, object] = {"done": threading.Event()}
    _jobs.put((fn, box))
    if not box["done"].wait(JOB_TIMEOUT):
        # Não mata a thread: um Chrome no meio de um clique não volta atrás só
        # porque desistimos de esperar. Diz a verdade e deixa o diário mostrar.
        raise Refused(
            f"o navegador não respondeu em {JOB_TIMEOUT:.0f}s — veja a janela, "
            "pode haver um diálogo ou um captcha esperando você")
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box["value"]


def profile_dir() -> Path:
    path = data_mod.state_dir() / PROFILE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _forget() -> None:
    """Solta as referências de um navegador morto, sem tentar fechá-lo bonito.

    Separado de `close()` de propósito: `close()` fecha um navegador vivo, isto
    aqui limpa os destroços de um que já morreu. Chamar `context.close()` num
    contexto morto só levanta outra exceção em cima da primeira.
    """
    for key in ("page", "context", "driver"):
        thing = _state.pop(key, None)
        if key == "driver" and thing is not None:
            try:
                thing.stop()      # o processo do Node fica de pé se ninguém pedir
            except Exception:  # noqa: BLE001
                pass


def available() -> tuple[bool, str]:
    """Playwright está pronto? Devolve (pode, motivo quando não)."""
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415, F401
    except ImportError:
        return False, "playwright não instalado (pip install playwright)"
    return True, ""


def _page(headless: bool = False):
    """A aba, criando o navegador na primeira vez.

    Perfil persistente: os logins do Edson ficam em disco e sobrevivem ao
    fechamento. Visível por padrão, de propósito — ver o que ele faz é a
    proteção que nenhuma heurística substitui.
    """
    ok, why = available()
    if not ok:
        raise Refused(why)

    # Aba viva é reaproveitada; aba morta é descartada e nasce outra.
    #
    # Sem esta checagem, um lançamento que morreu envenena o cache para sempre:
    # `_state["page"]` aponta para uma página fechada, `_page()` a devolve
    # contente, e toda chamada seguinte falha com "Target page, context or
    # browser has been closed" até alguém reiniciar o servidor. Foi exatamente
    # o que o Edson viu ao pedir "Abre o YouTube" — o Chrome do servidor
    # anterior ainda estava saindo e segurando o perfil, o novo nasceu morto, e
    # o erro passou a ser permanente em vez de passageiro.
    cached = _state.get("page")
    if cached is not None:
        try:
            if not cached.is_closed():
                return cached
        except Exception:  # noqa: BLE001 — objeto órfão do Playwright
            pass
        _forget()

    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    driver = sync_playwright().start()
    opts = {
        "user_data_dir": str(profile_dir()),
        "headless": headless,
        "viewport": {"width": 1360, "height": 900},
        "locale": "pt-BR",
        "timezone_id": "America/Sao_Paulo",
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    # Chrome do sistema antes do Chromium empacotado. Não é preferência: o
    # Mercado Livre derrubou o Chromium na primeira tentativa (redirecionou para
    # a página "Seguridad") e o Chrome real passa, porque a impressão digital é
    # a de um navegador de gente. Se não houver Chrome, cai no Chromium e a
    # leitura pode voltar vazia — o que `text()` diz em voz alta.
    try:
        context = driver.chromium.launch_persistent_context(channel="chrome", **opts)
    except Exception as exc:  # noqa: BLE001
        # Perfil ocupado é o erro comum, e o Playwright o conta mal: devolve
        # "Target page, context or browser has been closed", que soa como bug
        # e é na verdade o Chrome recusando dois processos no mesmo
        # user-data-dir. Acontece toda vez que o servidor já abriu o navegador
        # e alguém roda a CLI ao lado.
        if "has been closed" in str(exc) or "ProcessSingleton" in str(exc):
            driver.stop()
            raise Refused(
                "o perfil do navegador já está aberto por outro processo — "
                "feche a janela do JARVIS (ou pare o servidor) e tente de novo. "
                "O Chrome não aceita dois donos do mesmo perfil.") from exc
        try:
            context = driver.chromium.launch_persistent_context(**opts)
        except Exception as fallback:  # noqa: BLE001 — nem Chrome nem Chromium
            driver.stop()
            raise Refused(
                f"não consegui abrir o navegador: {str(fallback).splitlines()[0][:160]}"
            ) from fallback
    page = context.pages[0] if context.pages else context.new_page()
    page.set_default_timeout(ACT_TIMEOUT)
    page.set_default_navigation_timeout(NAV_TIMEOUT)
    _state.update(driver=driver, context=context, page=page)
    return page


def close() -> None:
    def _shut() -> None:
        for key in ("context", "driver"):
            thing = _state.pop(key, None)
            try:
                if key == "context" and thing:
                    thing.close()
                elif thing:
                    thing.stop()
            except Exception:  # noqa: BLE001 — fechar não deve levantar
                pass
        _state.pop("page", None)

    if not _state.get("context") and not _state.get("driver"):
        return                     # nada aberto: fechar é operação vazia

    if _worker is not None and _worker.is_alive():
        # heal=False: um navegador que já morreu não precisa nascer de novo só
        # para ser fechado.
        _run(_shut, heal=False)
    else:
        _shut()


def _settle(page, floor: int = 200, budget_ms: int = 6_000) -> int:
    """Espera o JS pintar, e devolve quantos chars o corpo tem no fim.

    Um `wait_for_timeout` fixo é o que fazia o Mercado Livre voltar com 0 chars:
    o DOM estava pronto, a lista não. Aqui a espera olha o que importa — o texto
    parou de crescer e já passou de um piso — em vez de contar segundos no vazio.
    Devolve o tamanho para que quem chama possa dizer "veio vazio" com número.
    """
    seen, stable = 0, 0
    step = 250
    for _ in range(max(1, budget_ms // step)):
        try:
            size = page.evaluate("() => (document.body?.innerText || '').length")
        except Exception:  # noqa: BLE001 — navegação no meio da medição
            size = 0
        if size > floor and size == seen:
            stable += 1
            if stable >= 2:          # duas medidas iguais: parou de pintar
                return size
        else:
            stable = 0
        seen = size
        page.wait_for_timeout(step)
    return seen


def _clean(text: str) -> str:
    """Texto de página sem os buracos de espaçamento que o layout deixa."""
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _record(kind: str, what: str, target: str, url: str, ok: bool,
            detail: str = "") -> Action:
    action = Action(id=uuid.uuid4().hex[:12], when=time.time(), kind=kind,
                    what=what, target=target, url=url, ok=ok, detail=detail)
    _log(action)
    return action


# ---------------------------------------------------------------------------
# Operações
#
# Cada uma é uma casca fina em volta de um `_impl` que roda na thread dona do
# navegador. A casca existe só para atravessar a fronteira de thread; toda a
# lógica está no `_impl`, e é ele que classifica, age e escreve no diário.
# ---------------------------------------------------------------------------

def goto(url: str, *, headless: bool = False) -> dict[str, object]:
    kind = classify("goto", url)
    _gate(kind)                       # antes da fila: recusar não precisa de aba

    def _impl() -> dict[str, object]:
        page = _page(headless)
        try:
            page.goto(url, wait_until="domcontentloaded")
            size = _settle(page)
        except Exception as exc:  # noqa: BLE001
            _record(kind, "goto", url, page.url, False, str(exc)[:200])
            # Navegador morto sobe cru, para `_run` poder curar e tentar de novo.
            # Embrulhado em Refused, viraria uma recusa definitiva — e foi assim
            # que "Abre o YouTube" virou erro permanente em vez de um tropeço.
            if DEAD_RE.search(str(exc)):
                raise
            raise Refused(f"não abriu {url}: {str(exc).splitlines()[0][:140]}") from exc
        _record(kind, "goto", url, page.url, True, f"{size} chars")
        return {"url": page.url, "title": page.title(), "chars": size}

    return _run(_impl)


def text(*, headless: bool = False, limit: int = PAGE_CHARS) -> dict[str, object]:
    """O texto renderizado da aba atual. Dado — nunca instrução."""
    def _impl() -> dict[str, object]:
        page = _page(headless)
        body = _clean(page.inner_text("body"))
        if len(body) < 200:                 # pode ser que o JS ainda não pintou
            _settle(page)
            body = _clean(page.inner_text("body"))
        truncated = len(body) > limit
        # Vazio nunca volta calado: foi assim que o urllib enganou a pesquisa.
        empty = "" if body else (
            "página abriu mas o corpo veio vazio — provavelmente exige login, "
            "ou é bloqueio de robô")
        _record("read", "text", "body", page.url, True, empty or f"{len(body)} chars")
        return {
            "url": page.url, "title": page.title(),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "chars": len(body), "truncated": truncated, "empty": empty,
            "text": body[:limit] + ("\n[truncado]" if truncated else ""),
        }

    return _run(_impl)


def fetch(url: str, *, limit: int = PAGE_CHARS) -> dict[str, object]:
    """Abrir e ler como **uma** operação. É o que a pesquisa deve chamar.

    `goto()` seguido de `text()` são dois trabalhos na fila, e entre eles cabe o
    trabalho de outra thread. `web.read_many()` abre três páginas em paralelo e
    há uma só aba: sem isto, a thread A navega, a B navega por cima, e a A lê o
    texto da página da B — devolvendo o conteúdo errado com a URL certa, que é
    o tipo de erro que ninguém percebe até citar o preço de outro fornecedor.
    """
    kind = classify("goto", url)
    _gate(kind)

    def _impl() -> dict[str, object]:
        page = _page()
        try:
            page.goto(url, wait_until="domcontentloaded")
            _settle(page)
        except Exception as exc:  # noqa: BLE001
            _record(kind, "goto", url, page.url, False, str(exc)[:200])
            # Navegador morto sobe cru, para `_run` poder curar e tentar de novo.
            # Embrulhado em Refused, viraria uma recusa definitiva — e foi assim
            # que "Abre o YouTube" virou erro permanente em vez de um tropeço.
            if DEAD_RE.search(str(exc)):
                raise
            raise Refused(f"não abriu {url}: {str(exc).splitlines()[0][:140]}") from exc
        body = _clean(page.inner_text("body"))
        truncated = len(body) > limit
        empty = "" if body else (
            "página abriu mas o corpo veio vazio — provavelmente exige login, "
            "ou é bloqueio de robô")
        _record(kind, "fetch", url, page.url, True, empty or f"{len(body)} chars")
        return {
            "url": page.url, "title": page.title(),
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "chars": len(body), "truncated": truncated, "empty": empty,
            "text": body[:limit] + ("\n[truncado]" if truncated else ""),
        }

    return _run(_impl)


def search_site(site: str, query: str, *, limit: int = 3_000) -> dict[str, object]:
    """Buscar dentro de um site e devolver a página de resultados.

    Dois caminhos, e a ordem importa. Com endereço de busca conhecido, monta a
    URL e vai direto: não depende de rótulo de campo, de layout nem de banner de
    cookie na frente. Sem ele, abre o site e usa a caixa de busca da própria
    página — mais frágil, por isso segundo.
    """
    template = SEARCH_URLS.get(site.rstrip("/"), "")
    if template:
        page = fetch(template.format(q=quote_plus(query)), limit=limit)
        page["how"] = "endereço de busca"
        page["query"] = query
        return page

    def _impl() -> dict[str, object]:
        pg = _page()
        pg.goto(site, wait_until="domcontentloaded")
        _settle(pg)
        # A caixa de busca, procurada pelos nomes que os sites de fato usam.
        box = None
        for how in ('input[type="search"]', '[role="searchbox"]',
                    'input[name="q"]', 'input[name="query"]',
                    'input[name="busca"]', 'input[name="search"]',
                    'input[placeholder*="usca" i]', 'input[placeholder*="earch" i]'):
            found = pg.locator(how).first
            try:
                if found.count() and found.is_visible():
                    box = found
                    break
            except Exception:  # noqa: BLE001 — seletor que não casa é normal
                continue
        if box is None:
            _record("send", "search", query, pg.url, False, "sem caixa de busca")
            raise Refused(
                f"abri {site} mas não achei a caixa de busca dele. A janela está "
                "aberta — busque aí, ou me dê o endereço do resultado.")
        box.fill(query)
        box.press("Enter")
        _settle(pg)
        body = _clean(pg.inner_text("body"))
        _record("send", "search", query, pg.url, True, f"{len(body)} chars")
        return {
            "url": pg.url, "title": pg.title(), "query": query,
            "how": "caixa de busca da página",
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "chars": len(body), "truncated": len(body) > limit, "empty": "",
            "text": body[:limit] + ("\n[truncado]" if len(body) > limit else ""),
        }

    return _run(_impl)


def shot(path: str = "") -> dict[str, object]:
    def _impl() -> dict[str, object]:
        page = _page()
        target = Path(path) if path else (data_mod.state_dir() / "browse" / "shot.png")
        target.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(target), full_page=False)
        _record("read", "shot", str(target), page.url, True)
        return {"path": str(target), "url": page.url}

    return _run(_impl)


def click(target: str) -> dict[str, object]:
    """Clica por texto visível. `target` é o que o humano leria no botão."""
    def _impl() -> dict[str, object]:
        page = _page()
        kind = classify("click", target, page.url)
        _gate(kind)
        try:
            page.get_by_text(target, exact=False).first.click()
            _settle(page)
        except Exception as exc:  # noqa: BLE001
            _record(kind, "click", target, page.url, False, str(exc)[:200])
            raise Refused(f"não achou '{target}' na página") from exc
        _record(kind, "click", target, page.url, True)
        return {"clicked": target, "url": page.url}

    return _run(_impl)


def fill(field: str, value: str) -> dict[str, object]:
    """Preenche um campo pelo rótulo. Senha é recusada antes de qualquer coisa."""
    # Recusa pelo rótulo sem abrir nada: pedir para digitar uma senha não
    # deveria nem custar o tempo de subir o Chrome.
    _gate(classify("fill", field))

    def _impl() -> dict[str, object]:
        page = _page()
        # Classifica também pelo tipo real do campo: um rótulo inocente sobre um
        # input[type=password] ainda é uma senha.
        kind = classify("fill", field, page.url)
        if kind != "secret":
            try:
                handle = page.get_by_label(field, exact=False).first
                if (handle.get_attribute("type") or "").lower() == "password":
                    kind = "secret"
            except Exception:  # noqa: BLE001 — sem rótulo, segue pela heurística
                pass
        _gate(kind)
        try:
            page.get_by_label(field, exact=False).first.fill(value)
        except Exception as exc:  # noqa: BLE001
            _record(kind, "fill", field, page.url, False, str(exc)[:200])
            raise Refused(f"não achou o campo '{field}'") from exc
        # O valor não vai para o diário: pode ser conteúdo de mensagem.
        _record(kind, "fill", field, page.url, True, f"{len(value)} chars")
        return {"filled": field, "url": page.url}

    return _run(_impl)


def press(key: str = "Enter") -> dict[str, object]:
    """Tecla no elemento focado. É assim que a maioria dos formulários envia."""
    def _impl() -> dict[str, object]:
        page = _page()
        _gate("send")
        page.keyboard.press(key)
        _settle(page)
        _record("send", "press", key, page.url, True)
        return {"pressed": key, "url": page.url}

    return _run(_impl)


def fields(limit: int = 30) -> dict[str, object]:
    """O que há para preencher nesta página, e de que tipo.

    Existe para que o modelo escolha um rótulo real em vez de adivinhar — um
    `fill` que erra o campo pode escrever a mensagem no lugar errado.
    """
    def _impl() -> dict[str, object]:
        page = _page()
        found = page.eval_on_selector_all(
            "input, textarea, select",
            "els => els.slice(0, 120).map(e => ({"
            " type: (e.type || e.tagName).toLowerCase(),"
            " name: e.name || '',"
            " label: (e.labels && e.labels[0] ? e.labels[0].innerText : "
            "         (e.getAttribute('aria-label') || e.placeholder || '')).trim().slice(0,70)"
            "}))",
        )
        rows = [row for row in found if row.get("label") or row.get("name")][:limit]
        # Marca os que o JARVIS não vai preencher, para o modelo não tentar.
        for row in rows:
            row["locked"] = row["type"] == "password" or bool(
                SECRET_RE.search(row["label"] + " " + row["name"]))
        _record("read", "fields", f"{len(rows)}", page.url, True)
        return {"url": page.url, "fields": rows}

    return _run(_impl)


def candidates(limit: int = 40) -> dict[str, object]:
    """O que dá para clicar nesta página, numerado.

    Existe para não voltar ao catálogo de frases. "o primeiro vídeo da lista"
    não é texto visível em lugar nenhum — nenhum seletor casa com isso, e
    escrever um seletor por site ("no YouTube o vídeo é a#video-title") seria
    exatamente a parede de exceções que o Edson mandou derrubar.

    Então a página diz o que oferece, numerado, e quem escolhe é o modelo. Ele
    é bom em "qual destes é o primeiro vídeo"; eu sou ruim em prever a pergunta.

    A ordem é a do DOM, que na prática é a ordem visual da lista — é o que faz
    "o primeiro" e "o terceiro" significarem algo.
    """
    def _impl() -> dict[str, object]:
        page = _page()
        found = page.evaluate(
            """() => {
                const out = [];
                const seen = new Set();
                const sel = 'a[href], button, [role="button"], [role="link"]';
                for (const el of document.querySelectorAll(sel)) {
                    const r = el.getBoundingClientRect();
                    if (r.width < 24 || r.height < 12) continue;   // ícone, não alvo
                    const t = (el.innerText || el.getAttribute('aria-label') || '')
                              .trim().replace(/\\s+/g, ' ').slice(0, 110);
                    if (t.length < 2) continue;
                    const href = el.getAttribute('href') || '';
                    const key = t + '|' + href;
                    if (seen.has(key)) continue;                   // o mesmo card duas vezes
                    seen.add(key);
                    out.push({ text: t, href: href ? el.href : '', top: Math.round(r.top) });
                    if (out.length > 200) break;
                }
                return out;
            }""",
        )
        rows = found[:limit]
        for i, row in enumerate(rows):
            row["n"] = i + 1
        _record("read", "candidates", f"{len(rows)}", page.url, True)
        return {"url": page.url, "title": page.title(), "candidates": rows}

    return _run(_impl)


def marked_shot(limit: int = 40) -> dict[str, object]:
    """Uma foto da página com os alvos numerados em cima, mais a lista.

    Isto é o que o Edson pediu ao dizer "dá visão a ele como o co-work do
    Claude desktop", e é a técnica que os sistemas de uso-de-computador de
    verdade usam: *set-of-marks*. Em vez de descrever a página em texto e torcer
    para o modelo imaginar o layout, marca-se cada alvo com um número visível e
    manda-se a imagem. "O primeiro vídeo da lista" deixa de ser um problema de
    adivinhação e vira um problema de olhar.

    A lista de texto vai junto, e não é redundância: a imagem diz *qual*, a
    lista diz *para onde* — o href, que é como o clique acontece sem depender do
    layout continuar igual.

    As marcas são removidas antes de sair. Uma página deixada com bolinhas
    amarelas em cima é uma página que o Edson vê e não entende.
    """
    def _impl() -> dict[str, object]:
        page = _page()
        rows = page.evaluate(
            """(limit) => {
                const out = [];
                const seen = new Set();
                const sel = 'a[href], button, [role="button"], [role="link"]';
                const vh = window.innerHeight, vw = window.innerWidth;
                // Menu, cabeçalho e barra lateral não são conteúdo, e sem isto
                // eles comem as 40 vagas: no YouTube a lista voltava "Guia,
                // Limpar consulta, Pesquisar com sua voz, Criar" e nenhum vídeo.
                // É estrutura de web, não seletor de site — vale em qualquer um.
                const CHROME = 'nav, header, aside, footer, [role="navigation"],'
                             + ' [role="banner"], [role="complementary"],'
                             + ' [role="contentinfo"], [role="search"]';
                for (const el of document.querySelectorAll(sel)) {
                    if (el.closest(CHROME)) continue;
                    const r = el.getBoundingClientRect();
                    // Só o que está na tela: marcar o que ninguém vê põe número
                    // na foto sem alvo embaixo, e o modelo escolhe fantasma.
                    if (r.width < 24 || r.height < 12) continue;
                    if (r.bottom < 0 || r.top > vh || r.right < 0 || r.left > vw) continue;
                    const t = (el.innerText || el.getAttribute('aria-label') || '')
                              .trim().replace(/\\s+/g, ' ').slice(0, 110);
                    if (t.length < 2) continue;
                    const href = el.getAttribute('href') || '';
                    const key = t + '|' + href;
                    if (seen.has(key)) continue;
                    seen.add(key);
                    out.push({ text: t, href: href ? el.href : '',
                               x: Math.round(r.left), y: Math.round(r.top) });
                }
                // Ordem visual, não ordem do DOM. "O primeiro da lista" é uma
                // afirmação sobre o que se vê em cima, e o DOM não promete isso.
                out.sort((a, b) => (a.y - b.y) || (a.x - b.x));
                return out.slice(0, limit);
            }""",
            limit,
        )
        for i, row in enumerate(rows):
            row["n"] = i + 1

        page.evaluate(
            """(rows) => {
                const box = document.createElement('div');
                box.id = '__jarvis_marks__';
                box.style.cssText = 'position:fixed;inset:0;z-index:2147483647;pointer-events:none';
                for (const r of rows) {
                    const tag = document.createElement('div');
                    tag.textContent = r.n;
                    tag.style.cssText =
                      'position:absolute;left:' + Math.max(0, r.x) + 'px;top:' + Math.max(0, r.y) + 'px;'
                      + 'background:#ffd400;color:#111;font:700 12px/1.1 monospace;'
                      + 'padding:2px 4px;border:1px solid #111;border-radius:3px';
                    box.appendChild(tag);
                }
                document.body.appendChild(box);
            }""",
            rows,
        )
        try:
            png = page.screenshot(full_page=False)
        finally:
            # Sempre, mesmo se o screenshot falhar: as marcas não podem ficar.
            page.evaluate(
                "() => document.getElementById('__jarvis_marks__')?.remove()")

        _record("read", "marked", f"{len(rows)}", page.url, True)
        return {"url": page.url, "title": page.title(),
                "candidates": rows, "png": png}

    return _run(_impl)


def click_candidate(row: dict[str, object]) -> dict[str, object]:
    """Clica um item devolvido por `candidates()`.

    Prefere navegar pelo href a clicar no elemento: um clique depende de o
    layout não ter mexido entre listar e clicar, e em página que carrega
    sozinha (YouTube, Mercado Livre) ele mexe. O href não mexe.
    """
    href = str(row.get("href") or "")
    text = str(row.get("text") or "")
    if href:
        kind = classify("goto", href)
        _gate(kind)

        def _nav() -> dict[str, object]:
            page = _page()
            page.goto(href, wait_until="domcontentloaded")
            _settle(page)
            _record(kind, "click", text[:60], page.url, True, "via href")
            return {"clicked": text, "url": page.url, "title": page.title()}

        return _run(_nav)
    return click(text)


def links(limit: int = 40) -> dict[str, object]:
    def _impl() -> dict[str, object]:
        page = _page()
        found = page.eval_on_selector_all(
            "a[href]",
            "els => els.slice(0, 200).map(e => ({t: e.innerText.trim().slice(0,90),"
            " h: e.href}))",
        )
        rows = [row for row in found if row.get("t")][:limit]
        _record("read", "links", f"{len(rows)}", page.url, True)
        return {"url": page.url, "links": rows}

    return _run(_impl)


def _journal_count() -> tuple[int, int]:
    """Total de ações e de gastos no diário inteiro.

    Contado sobre o arquivo, não sobre a janela recente: `len(history(20))` dava
    "20 ações" para sempre depois da vigésima, e um contador que congela mente
    de forma mais convincente do que um ausente.
    """
    try:
        lines = _journal_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0, 0
    total = spent = 0
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        total += 1
        if row.get("kind") == "spend" and row.get("ok"):
            spent += 1
    return total, spent


def state() -> dict[str, object]:
    ok, why = available()
    recent = history(20)
    total, spent = _journal_count()
    return {
        "available": ok,
        "reason": why,
        "open": _state.get("page") is not None,
        "url": (_state["page"].url if _state.get("page") is not None else ""),
        "profile": str(profile_dir()),
        "actions": total,
        "policy": {
            "read": "livre",
            "send": "liberado",
            "spend": "liberado, marcado no diário",
            "secret": "sem senha guardada — logue você na janela",
        },
        "spent": spent,
        "recent": [a.to_dict() for a in recent[-8:]],
    }


# Fechar o Chrome quando o processo termina normalmente.
#
# É a causa raiz do erro que o Edson viu: o servidor foi derrubado, o Chrome dele
# ficou saindo devagar segurando o perfil, e o servidor seguinte lançou um
# navegador que nasceu morto. Não cobre `Stop-Process -Force` — nada cobre — mas
# cobre Ctrl-C e saída limpa, que é a maioria das reinicializações.
atexit.register(close)


# ---------------------------------------------------------------------------
# Linha de comando
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    args = sys.argv[1:]
    if not args:
        info = state()
        print(f"\n  playwright  {'pronto' if info['available'] else info['reason']}")
        print(f"  perfil      {info['profile']}")
        for name, rule in info["policy"].items():   # type: ignore[union-attr]
            print(f"  {name:<11} {rule}")
        print("\n  uso: python -m agent.browse ler <url> | abrir <url>"
              " | clicar <texto> | campos | links | diario\n")
        return 0

    verb, rest = args[0], " ".join(args[1:])
    try:
        if verb in ("ler", "read"):
            goto(rest)
            page = text()
            print(f"\n  {page['title']}\n  {page['url']}  ({page['chars']} chars)\n")
            print(page["text"][:1500])
            return 0
        if verb in ("abrir", "open"):
            print(goto(rest))
            return 0
        if verb in ("clicar", "click"):
            print(click(rest))
            return 0
        if verb == "links":
            for row in links()["links"]:            # type: ignore[index]
                print(f"  {row['t'][:60]:62} {row['h'][:70]}")
            return 0
        if verb == "campos":
            for row in fields()["fields"]:          # type: ignore[index]
                mark = "  [senha, não preenchido]" if row["locked"] else ""
                print(f"  {row['type']:<10} {row['label'][:50]:52}{mark}")
            return 0
        if verb in ("diario", "diário", "log"):
            for act in history(40):
                flag = "ok " if act.ok else "ERR"
                print(f"  {flag} {act.kind:<7} {act.what:<7} {act.target[:40]:42}"
                      f" {act.url[:44]}")
            return 0
    except Refused as exc:
        print(f"\n  RECUSADO: {exc}\n")
        return 1

    print(f"verbo desconhecido: {verb}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
