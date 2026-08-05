"""speak.py — a voz do JARVIS: Antonio, modo jarvis.

O Edson testou as opções e escolheu: `pt-BR-AntonioNeural`, tom -12Hz, o que ele
chamou de "modo jarvis" em `LEIA-ME.md` — mais grave que o Antonio padrão.

A velocidade ele escolheu depois, ouvindo: **+40%**. O teste original era -8%,
mas isso foi julgar uma frase; ouvindo o assistente responder, o pausado vira
arrastado. As seis velocidades comparadas estão em `amostras/velocidade_*.mp3`.

## Por que aqui e não no navegador

A página já falava, usando as vozes instaladas na máquina. Isso tem uma
vantagem que este arquivo perde e que precisa ser dita: **nada saía do
computador**. A voz do navegador é local, e a resposta lida em voz alta é
conteúdo do Cofre do Edson.

Aqui não. `edge-tts` manda o texto para o serviço de síntese da Microsoft e
recebe o áudio de volta. O que o JARVIS fala passa por servidor de terceiro.

Foi uma escolha dele, feita depois de ouvir as amostras, e é defensável — a
alternativa local que soa tão bem (Kokoro) exige instalar modelo e roda mais
devagar. Mas a troca é essa, e ela está escrita aqui em vez de escondida numa
linha de configuração.

`JARVIS_SPEAK=0` desliga e devolve a fala ao navegador, que é local de novo.

## O que isto não faz

Não guarda áudio em disco. O MP3 vai para a página e morre na memória —
gravar tudo que o JARVIS falou seria uma segunda cópia falada do Cofre, e
ninguém pediu por ela.

Rode direto:  python -m agent.speak "bom dia, Edson"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod

# A escolha do Edson, ouvindo as amostras. Ver LEIA-ME.md e amostras/.
#
# O "modo jarvis" que ele documentou era -8%, mais pausado. Ouvindo o JARVIS
# falar de verdade, ele preferiu +40%: a mesma frase em 12,0s em vez de 18,3s.
# Faz sentido — a voz grave já dá o peso, e a lentidão em cima disso vira
# arrastado quando você ouve dez respostas por dia. O tom fica onde estava.
VOICE = "pt-BR-AntonioNeural"
RATE = "+40%"
PITCH = "-12Hz"

# Uma resposta longa demais para falar é uma resposta para ler. O corte evita
# tanto a espera quanto a conta: cada caractere vira uma chamada de rede.
MAX_CHARS = 4_000


class SpeechFailed(RuntimeError):
    """A síntese não veio. Nunca silêncio calado — a página mostra o motivo."""


def enabled() -> bool:
    """Ligado por padrão; `JARVIS_SPEAK=0` devolve a fala ao navegador."""
    return (data_mod.setting("JARVIS_SPEAK") or "1").strip() not in ("0", "false", "no")


def available() -> tuple[bool, str]:
    if not enabled():
        return False, "desligado por JARVIS_SPEAK=0 — a página fala sozinha"
    try:
        import edge_tts  # noqa: PLC0415, F401
    except ImportError:
        return False, "edge-tts não instalado (pip install edge-tts)"
    return True, ""


def voice_name() -> str:
    return (data_mod.setting("JARVIS_SPEAK_VOICE") or VOICE).strip()


async def _synth(text: str) -> bytes:
    import edge_tts  # noqa: PLC0415

    stream = edge_tts.Communicate(
        text,
        voice_name(),
        rate=(data_mod.setting("JARVIS_SPEAK_RATE") or RATE).strip(),
        pitch=(data_mod.setting("JARVIS_SPEAK_PITCH") or PITCH).strip(),
    )
    chunks = bytearray()
    async for piece in stream.stream():
        if piece["type"] == "audio":
            chunks.extend(piece["data"])
    return bytes(chunks)


def say(text: str) -> bytes:
    """O MP3 desta frase. Levanta SpeechFailed com o motivo, nunca vazio.

    Cada chamada roda seu próprio laço asyncio: o servidor é `ThreadingHTTPServer`
    e cada requisição chega numa thread sem laço nenhum. Reaproveitar um laço
    global entre threads é a mesma classe de erro que o Playwright já cobrou
    caro neste projeto.
    """
    ok, why = available()
    if not ok:
        raise SpeechFailed(why)

    clean = " ".join((text or "").split())[:MAX_CHARS]
    if not clean:
        raise SpeechFailed("nada para falar")

    try:
        audio = asyncio.run(_synth(clean))
    except Exception as exc:  # noqa: BLE001 — rede, DNS, serviço fora
        raise SpeechFailed(
            f"a síntese falhou: {str(exc).splitlines()[0][:140]}") from exc
    if not audio:
        raise SpeechFailed("a síntese voltou sem áudio")
    return audio


def state() -> dict[str, object]:
    ok, why = available()
    return {
        "available": ok,
        "reason": why,
        "voice": voice_name(),
        "rate": (data_mod.setting("JARVIS_SPEAK_RATE") or RATE).strip(),
        "pitch": (data_mod.setting("JARVIS_SPEAK_PITCH") or PITCH).strip(),
        # Dito na cara: quem fala manda o texto para fora da máquina.
        "local": False,
        "note": "o texto falado vai para o serviço da Microsoft (edge-tts). "
                "JARVIS_SPEAK=0 devolve a fala ao navegador, que é local.",
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    said = " ".join(sys.argv[1:]).strip() or "Bom dia, Edson. Tudo pronto por aqui."
    try:
        audio = say(said)
    except SpeechFailed as exc:
        print(f"  FALHOU: {exc}")
        return 1
    out = Path("amostras") / "jarvis-teste.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)
    info = state()
    print(f"  {info['voice']}  rate {info['rate']}  pitch {info['pitch']}")
    print(f"  {len(audio):,} bytes -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
