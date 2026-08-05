# Teste de voz pro Jarvis — edge-tts x Kokoro (pt-BR)

## O que tem aqui

- `comparar_tts.py` — gera as mesmas frases nas duas engines, cronometra e imprime uma tabela.
- `amostras/` — áudios que eu já gerei, mesma frase em todas as vozes. Ouça antes de instalar qualquer coisa.

## As amostras

Todas dizem a mesma frase: *"Bom dia, Edson. Todos os sistemas estão operacionais. A EVO tem três orçamentos aguardando resposta, e o limite de desconto da Viacredi está em setenta por cento."*

| Arquivo | Engine | Observação |
|---|---|---|
| `edge_pt-BR-AntonioNeural.mp3` | edge-tts | voz masculina padrão |
| `edge_antonio_modo_jarvis.mp3` | edge-tts | Antonio com `--rate=-8% --pitch=-12Hz` — mais grave e pausado |
| `edge_pt-BR-FranciscaNeural.mp3` | edge-tts | voz feminina padrão |
| `edge_pt-BR-ThalitaMultilingualNeural.mp3` | edge-tts | multilíngue, lida melhor com termos em inglês |
| `kokoro_pm_alex.mp3` | Kokoro-82M | masculina, local |
| `kokoro_pf_dora.mp3` | Kokoro-82M | feminina, local |
| `kokoro_pm_santa.mp3` | Kokoro-82M | masculina alternativa |

## Instalação

```bash
pip install edge-tts kokoro soundfile numpy
```

O Kokoro precisa do **espeak-ng** instalado no sistema (é o fonetizador):

- Windows: `winget install eSpeak-NG`
- Linux: `sudo apt install espeak-ng`
- macOS: `brew install espeak-ng`

Se você só quiser testar o edge-tts primeiro, `pip install edge-tts` já basta.

## Rodando

```bash
python comparar_tts.py                    # as duas engines, 3 frases de teste
python comparar_tts.py --so-edge          # só edge-tts, não baixa modelo nenhum
python comparar_tts.py --so-kokoro        # só Kokoro, 100% offline após o 1º uso
python comparar_tts.py --jarvis           # edge-tts com tom grave de assistente
python comparar_tts.py --texto "Frase que você quiser"
```

Os áudios saem em `saida/edge/` e `saida/kokoro/`.

## Como eu li os números aqui

Rodei o script num container Linux só-CPU (sem GPU). RTF = tempo de geração ÷ duração do áudio; abaixo de 1.0 significa que gera mais rápido do que leva pra falar.

| Engine | RTF medido | Leitura |
|---|---|---|
| edge-tts (Antonio/Francisca) | 0.12–0.15x | latência dominada pela rede, não pelo processamento |
| edge-tts (Thalita) | 0.53x | multilíngue é mais pesado do lado deles |
| Kokoro (CPU pura) | 0.60–0.66x | numa CPU decente ou GPU cai bem abaixo disso |

Os dois servem pra conversa em tempo real. A diferença prática é outra: o edge-tts depende de internet e de um serviço não-oficial da Microsoft; o Kokoro roda offline pra sempre, com licença Apache 2.0.

## O que ouvir

Não julgue pela primeira frase — julgue por:

1. **Números e siglas.** "NF 1.842", "70 por cento", "EVO". É onde TTS ruim se entrega.
2. **Fim de frase.** Entonação de ponto final vs. vírgula.
3. **Escutar 20 vezes seguidas.** A voz do Jarvis você vai ouvir todo dia. Uma voz que impressiona no primeiro teste pode cansar rápido.

## Plugando no agente

O jeito mais limpo é subir o [openai-edge-tts](https://github.com/travisvn/openai-edge-tts) — ele expõe o edge-tts num endpoint compatível com a API da OpenAI, então o Jarvis chama como se fosse serviço pago e você troca de provedor depois só mudando a URL.

Pro Kokoro existe o [Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI), que faz a mesma coisa: endpoint compatível com OpenAI, rodando local. Se você padronizar nessa interface desde já, trocar edge-tts ↔ Kokoro ↔ Chatterbox depois é mudar uma linha de config.
