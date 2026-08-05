#!/usr/bin/env python3
"""
Comparador de TTS pt-BR: edge-tts (nuvem, grátis) x Kokoro-82M (local, Apache 2.0)

Gera as mesmas frases nas duas engines, mede o tempo e monta uma tabela
pra você decidir qual vai virar a voz do Jarvis.

Instalação:
    pip install edge-tts kokoro soundfile numpy
    # Kokoro precisa do espeak-ng no sistema:
    #   Linux : sudo apt install espeak-ng
    #   Windows: winget install eSpeak-NG   (ou baixe do GitHub do espeak-ng)
    #   macOS : brew install espeak-ng

Uso:
    python comparar_tts.py                 # roda as duas engines
    python comparar_tts.py --so-edge       # só edge-tts (não baixa modelo)
    python comparar_tts.py --so-kokoro     # só Kokoro (100% offline após 1º uso)
    python comparar_tts.py --texto "Sua frase aqui"
"""

import argparse
import asyncio
import time
from pathlib import Path

SAIDA = Path(__file__).parent / "saida"

# Frases de teste: fala corrida, números/siglas e comando curto.
# Número e sigla são onde as engines mais se diferenciam.
FRASES = {
    "01_saudacao": (
        "Bom dia, Edson. Todos os sistemas estão operacionais. "
        "A EVO tem três orçamentos aguardando resposta."
    ),
    "02_numeros": (
        "O borderô fechou em quarenta e sete mil, duzentos e trinta reais. "
        "A NF 1.842 vence dia 15, e o limite de desconto está em 70 por cento."
    ),
    "03_comando": "Certo. Desligando as luzes da oficina e ativando o alarme.",
}

VOZES_EDGE = [
    "pt-BR-AntonioNeural",
    "pt-BR-FranciscaNeural",
    "pt-BR-ThalitaMultilingualNeural",
]

# lang_code 'p' = português brasileiro
VOZES_KOKORO = ["pm_alex", "pf_dora", "pm_santa"]

resultados = []  # (engine, voz, id_frase, segundos, dur_audio, arquivo)


# ---------------------------------------------------------------- edge-tts
async def rodar_edge(textos, ajuste_jarvis=False):
    import edge_tts

    destino = SAIDA / "edge"
    destino.mkdir(parents=True, exist_ok=True)

    for voz in VOZES_EDGE:
        for nome, texto in textos.items():
            arq = destino / f"{voz}__{nome}.mp3"
            t0 = time.perf_counter()
            extras = {"rate": "-8%", "pitch": "-12Hz"} if ajuste_jarvis else {}
            com = edge_tts.Communicate(texto, voz, **extras)
            await com.save(str(arq))
            dt = time.perf_counter() - t0
            dur = duracao_mp3(arq)
            resultados.append(("edge-tts", voz, nome, dt, dur, arq))
            print(f"  [edge-tts] {voz:34} {nome}  {dt:5.2f}s")


def duracao_mp3(caminho: Path) -> float:
    """Duração aproximada do MP3 (sem dependência externa: 24 kbps mono do edge)."""
    try:
        import soundfile as sf

        info = sf.info(str(caminho))
        return info.duration
    except Exception:
        # edge-tts entrega ~24 kbps -> bytes / 3000 ≈ segundos
        return caminho.stat().st_size / 3000.0


# ------------------------------------------------------------------ Kokoro
def rodar_kokoro(textos):
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    destino = SAIDA / "kokoro"
    destino.mkdir(parents=True, exist_ok=True)

    print("  (primeira execução baixa ~350 MB do modelo; depois roda offline)")
    pipe = KPipeline(lang_code="p", repo_id="hexgrad/Kokoro-82M")

    for voz in VOZES_KOKORO:
        for nome, texto in textos.items():
            arq = destino / f"{voz}__{nome}.wav"
            t0 = time.perf_counter()
            audio = np.concatenate([g.audio.numpy() for g in pipe(texto, voice=voz)])
            dt = time.perf_counter() - t0
            sf.write(str(arq), audio, 24000)
            dur = len(audio) / 24000
            resultados.append(("kokoro", voz, nome, dt, dur, arq))
            print(f"  [kokoro  ] {voz:34} {nome}  {dt:5.2f}s  (RTF {dt/dur:.2f}x)")


# ------------------------------------------------------------------ relatório
def tabela():
    if not resultados:
        return
    print("\n" + "=" * 78)
    print(f"{'ENGINE':<10} {'VOZ':<34} {'GERAÇÃO':>9} {'ÁUDIO':>8} {'RTF':>7}")
    print("-" * 78)

    agregado = {}
    for engine, voz, _, dt, dur, _ in resultados:
        chave = (engine, voz)
        soma_dt, soma_dur = agregado.get(chave, (0.0, 0.0))
        agregado[chave] = (soma_dt + dt, soma_dur + dur)

    for (engine, voz), (dt, dur) in agregado.items():
        rtf = dt / dur if dur else 0
        print(f"{engine:<10} {voz:<34} {dt:8.2f}s {dur:7.2f}s {rtf:6.2f}x")

    print("=" * 78)
    print("RTF = tempo de geração ÷ duração do áudio. Abaixo de 1.0 é mais rápido")
    print("que tempo real — o mínimo pra um assistente responder sem parecer travado.")
    print(f"\nÁudios em: {SAIDA}")
    print("Ouça na ordem: mesma frase, engines diferentes. Preste atenção em")
    print("números, siglas (EVO, NF) e no final das frases — é onde a diferença aparece.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--so-edge", action="store_true", help="roda só edge-tts")
    ap.add_argument("--so-kokoro", action="store_true", help="roda só Kokoro")
    ap.add_argument("--texto", help="usa uma frase própria no lugar das três padrão")
    ap.add_argument(
        "--jarvis",
        action="store_true",
        help="no edge-tts, baixa tom e velocidade (fica mais 'assistente')",
    )
    args = ap.parse_args()

    textos = {"custom": args.texto} if args.texto else FRASES
    SAIDA.mkdir(exist_ok=True)

    if not args.so_kokoro:
        print("\n>> edge-tts (nuvem, sem API key)")
        try:
            asyncio.run(rodar_edge(textos, ajuste_jarvis=args.jarvis))
        except Exception as e:
            print(f"  !! edge-tts falhou: {e}")

    if not args.so_edge:
        print("\n>> Kokoro-82M (local)")
        try:
            rodar_kokoro(textos)
        except Exception as e:
            print(f"  !! Kokoro falhou: {e}")
            print("     Falta o espeak-ng? Linux: sudo apt install espeak-ng")

    tabela()


if __name__ == "__main__":
    main()
