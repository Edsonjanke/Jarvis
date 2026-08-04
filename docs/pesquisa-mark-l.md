# Mark L — inventário e veredito

Pesquisa, não implementação. Levantamento de <https://github.com/FatihMakes/Mark-L>
(671 estrelas, Python + PyQt6, Gemini Live) para decidir item por item o que vale
trazer para o JARVIS.

## A questão da licença vem primeiro

O repositório **não tem arquivo `LICENSE`** — a API de licenças do GitHub devolve
404. O readme, porém, declara:

> Personal and non-commercial use only. Licensed under Creative Commons BY-NC 4.0.

Duas consequências, e a segunda é a que decide:

1. **CC não é licença de software.** A própria Creative Commons recomenda não
   aplicar suas licenças a código, porque elas não tratam de código-fonte,
   binários nem patentes.
2. **A cláusula NC nos exclui.** Edson opera a EVO Soluções Industriais. Um
   assistente que orça usinagem e analisa borderô é uso comercial — exatamente o
   que a BY-NC proíbe. Adaptar aquele código também carimbaria a obrigação NC
   sobre este repositório, que é público.

**Portanto: nada de código copiado, adaptado ou traduzido.** Ideias e arquitetura
não são protegidas por copyright; implementação é. O que segue trata cada
capacidade como *ideia a reimplementar do zero em stdlib*, e nada mais.

Observação lateral: o repositório versiona uma chave privada
(`config/certs/jarvis.key`) num repo público. Não é nosso problema, e não é algo
a imitar.

## O conflito de arquitetura

| | Mark L | JARVIS |
|---|---|---|
| Modelo | Gemini Live (Google, chave própria) | assinatura Claude já logada |
| Interface | app desktop PyQt6 | navegador, JS puro |
| Dependências | 26 pacotes pip | **zero** |
| Alcance | controla o computador | lê o vault, responde, fala |

O briefing do Edson exige *"standard library only no servidor, vanilla JS no
navegador, sem framework, sem build, sem gerenciador de pacotes"*. Qualquer item
abaixo que dependa de `pyautogui`, `opencv`, `mss`, `pywinauto`, `playwright` ou
`fastapi` custa essa exigência para existir. Isso está anotado item a item.

## Inventário — 30 capacidades

Veredito: **TRAZER** reimplementar · **JÁ TEM** existe no JARVIS · **TALVEZ**
decisão do Edson · **NÃO** descartar, com motivo.

| # | Capacidade | Veredito | Por quê |
|---|---|---|---|
| 1 | Multi-Mode Web Search (news/research/price/compare) | **TRAZER** | É o `research_web`, item 2 da lista de seis ferramentas do briefing original — e o JARVIS não tem busca na web nenhuma. Dá em `urllib`, sem dependência. O maior buraco aberto. |
| 2 | Session Memory — resume a sessão, menciona amanhã, consome | **TRAZER** | Padrão elegante contra inchaço: o resumo é apagado depois de usado. `memory.py` tem teto de 300 fatos; isto respeita o teto por construção. |
| 3 | Proactive 2.0 — hora do dia, projetos, últimos turnos, rotação, cooldown 20min | **TRAZER** | Encaixa no botão SEMPRE que já existe. A rotação entre três focos é o que evita o assistente repetir a mesma abertura e virar ruído. |
| 4 | Morning Briefing (cumprimenta, hora, recapitula ontem, notícias) | **TALVEZ** | Destravaria o que foi pedido e travou por falta de Gmail/Calendar — esta versão não usa conector nenhum. Não foi selecionado; fica registrado como disponível. |
| 5 | Background Monitoring — vigia um tópico, checa 1×/dia | **TALVEZ** | Útil para preço de inox e nome de cliente. Depende do item 1 existir primeiro. Vale copiar a decisão deles de bloquear cripto/financeiro no código. |
| 6 | Parallel News Search — duas buscas em threads, a primeira válida ganha | **TRAZER** (junto do 1) | Não é feature, é técnica: mata a latência do fallback. Cabe em `threading` da stdlib. |
| 7 | Persistent Memory | **JÁ TEM** | `agent/memory.py`, um fato por arquivo datado em `memory/`. |
| 8 | Visual Awareness (tela e webcam) | **JÁ TEM** | Chegou no commit "olhos"; `tests/test_vision.py` passa. |
| 9 | Real-time Voice | **JÁ TEM** (diferente) | ElevenLabs Scribe na escuta, vozes do navegador na fala. Gemini Live significaria pagar o Google e abandonar a assinatura Claude. |
| 10 | Hybrid Input (teclado e voz) | **JÁ TEM** | Barra de perguntas + MIC + SEMPRE. |
| 11 | Silent Language Memory — detecta o idioma e adapta | **JÁ TEM** | `JARVIS_LANG=pt-BR` e o `JARVIS.md` fixam português. Detectar é pior que declarar. |
| 12 | Assistant Customization (nome do assistente e do usuário) | **JÁ TEM** | `JARVIS.md` carrega quem pergunta e como responder. |
| 13 | File Processor — lê e resume arquivos locais | **JÁ TEM**, melhor | O `pdftext.py` lê desenho SolidWorks com CMap `/ToUnicode`, que quase nenhum extrator faz. |
| 14 | Autonomous Tasks / agent mode | **JÁ TEM** parcialmente | `brain.plan()` e o botão PLAN. Sem execução autônoma, o que é acerto e não falta. |
| 15 | Dynamic Content Panel | **JÁ TEM** | O inspetor da esquerda. |
| 16 | Smart Reminders — agendamento nativo do SO | **TALVEZ** | Task Scheduler no Windows. Modesto e útil, mas nunca esteve no briefing, e escrever no agendador do SO é um poder novo. |
| 17 | Weather Report | **NÃO** | Não move nada numa usinagem. |
| 18 | Hardware Monitoring (CPU/RAM/GPU/temperatura) | **NÃO** | Exige `psutil`. Existem monitores melhores e o assistente não é um deles. |
| 19 | Open App — abre aplicativo por voz | **TALVEZ** | Abrir o Evo-SI ou o CAM falando é atraente. Mas é "controlar o computador", que o briefing nunca pediu. |
| 20 | Computer Settings (volume, brilho, WiFi, energia) | **NÃO** | `pycaw`, `comtypes`. Nada a ver com o problema dele. |
| 21 | Computer Control (atalhos, mouse, janelas) | **NÃO** | `pyautogui`, `pywinauto`. Superfície enorme, risco de clique errado, valor nenhum aqui. |
| 22 | Desktop Control (barra de tarefas, janelas) | **NÃO** | Mesmo motivo. |
| 23 | Browser Control | **NÃO** | `playwright`. O JARVIS *é* uma página; controlar navegador é dar a ele um segundo corpo. |
| 24 | Send Message (WhatsApp, Telegram) | **NÃO — viola guardrail** | O briefing diz, em absoluto: *"Never send. Not an email, message or calendar invite. Draft it and wait."* Isto não é preferência, é regra que ele escreveu. |
| 25 | Remote Dashboard com pareamento por QR | **NÃO** | Abre a máquina que guarda o vault dele para a rede. `fastapi`, `uvicorn`, `cryptography`, `qrcode`. O JARVIS é localhost por decisão. |
| 26 | Auto-Start on Boot (registro/LaunchAgent) | **NÃO** | Escreve no registro do Windows. Um atalho na pasta Inicializar resolve, sem código. |
| 27 | Clipboard Intelligence — copiar → traduzir/resumir/explicar | **TALVEZ** | Genuinamente bom. Mas exige monitorar a área de transferência do SO, o que quer dizer ler tudo que ele copia — inclusive senha. |
| 28 | Code Helper (revisão e geração) | **NÃO** | Ele já tem Claude Code para isso. Duplicação. |
| 29 | Dev Agent | **NÃO** | Mesmo motivo. |
| 30 | Game Updater (Steam/Epic) · Flight Finder · YouTube | **NÃO** | Fora de propósito. |

## Contagem

- **TRAZER: 4** — busca na web (1), busca paralela (6), resumo de sessão (2), proativo (3)
- **JÁ TEM: 9** — memória, visão, voz, entrada híbrida, idioma, identidade, leitura de arquivo, plano, painel
- **TALVEZ: 6** — brief matinal, monitor de tópico, lembretes, abrir app, área de transferência
- **NÃO: 12**

De trinta capacidades anunciadas, **quatro** valem trabalho e **nove já existem**
— algumas em versão melhor. O repositório é largo, não profundo: quase todo o
volume dele é controlar Windows, e isso não é o problema do Edson.

## O que o Edson já escolheu

Selecionado: **busca na web**, **resumo de sessão consumido no uso**, **proativo
com rotação e cooldown**. A busca paralela entra junto da busca. O brief matinal
não foi selecionado e fica disponível.

## Riscos de implementação, antes de começar

1. **`research_web` sem dependência.** DuckDuckGo HTML via `urllib` funciona mas
   é frágil: eles mudam o HTML e mudam sem aviso. Precisa falhar em voz alta —
   "a busca quebrou", nunca um resultado vazio silencioso.
2. **A guardrail do briefing sobre número derivado.** *"Never state a derived
   number without its qualifier."* Uma cotação da web tem data e fonte; se o
   preço do inox for de três semanas atrás, isso tem que ser dito na frase, não
   num rodapé.
3. **Injeção via conteúdo buscado.** Página da web é dado, nunca instrução. A
   regra já existe no `JARVIS.md` e vale igual aqui.
4. **Cota da assinatura.** O proativo fala sozinho; cada fala é uma chamada de
   modelo. Com o cérebro em Opus 5 isso consome a cota Max dele sem ele pedir
   nada. O cooldown de 20 minutos é o mínimo, e o padrão deve ser desligado.
