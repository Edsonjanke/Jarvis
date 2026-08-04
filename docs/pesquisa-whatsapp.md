# JARVIS e as conversas do WhatsApp — pesquisa

> Pesquisa, não implementação. Nada aqui foi construído. O documento existe
> para ser executado fase a fase, com o raciocínio junto.
>
> Levantado em 04/08/2026.

## Por que este documento existe

A pergunta foi: como o JARVIS teria acesso às conversas do WhatsApp e
memorizaria tudo — contatos e o que foi dito.

**Decisões tomadas:** tudo entra, mas **separado** (trabalho e pessoal em
raízes distintas, para poder desligar uma); **as mídias vão junto**; e nada é
construído por ora.

Uma coisa dita uma vez, porque é verdade e não bloqueia nada: um export contém
o que **as outras pessoas** escreveram, e elas não escolheram isso. É a sua
conversa, na sua máquina, no seu app, e a lei brasileira tem exceção para uso
pessoal e doméstico. Mas o que entra no vault entra nos prompts, e é por isso
que "separado" foi a escolha certa.

---

## O que já funciona hoje, sem uma linha de código

Três peças já estão prontas e não sabiam que serviam para isto:

- **O indexador aceita `.txt`.** Um export do WhatsApp largado na pasta do
  vault já é lido e já é buscável. Hoje. Sem código.
- **O tipo `person` já existe** em `FOLDER_TYPES` ([../agent/vault.py](../agent/vault.py)),
  mapeado de `contacts/`. Cada contato pode virar nó do grafo.
- **[../agent/edit.py](../agent/edit.py) já escreve com contenção e desfazer.**
  Uma importação inteira passaria por ele e seria reversível pelo painel.

E há o detalhe que decide o valor: **o grafo tem 170 nós e zero ligações**,
porque PDF não tem wikilink. Conversas ligadas a contatos são o que finalmente
daria arestas — "quem falou comigo sobre a PARINOX" vira uma pergunta com
resposta.

---

## Os dois caminhos, e por que só um é defensável

### A. Exportar — oficial, gratuito, sem risco

`Exportar conversa` no próprio WhatsApp entrega um `.txt`. Limites: **40.000
mensagens sem mídia** ou **10.000 com mídia** por vez. Não é limite do
histórico — é limite da função de compartilhar.

Complemento oficial: **`Solicitar informações da conta`** devolve um relatório
que **não traz mensagem nenhuma**, mas traz **a lista de contatos com números e
os nomes de todos os grupos**. O esqueleto de contatos vem por via oficial, e o
export preenche o conteúdo.

Custo real: é manual. Alguns minutos por conversa, quando quiser atualizar.

### B. Ao vivo — e por que não

Só existe por bibliotecas não-oficiais (**Baileys** em Node, **whatsmeow** em
Go) que se pareiam como aparelho companheiro. Isso traria uma dependência de
runtime — o projeto inteiro é stdlib, e essa regra não é estética: é o que faz
ele rodar em qualquer máquina sem instalar nada.

Mas o problema maior não é esse. **Em maio de 2025 o WhatsApp mandou avisos de
"sua conta pode estar em risco — ferramentas não autorizadas" e banimentos para
usuários das duas bibliotecas, atingindo uso passivo, de baixo volume, só
respondendo.** Não foi varredura contra spammer. Os termos proíbem cliente
não-oficial, e a detecção pesa sinais como IP de datacenter, temporização
robótica e proporção de resposta.

O número em risco é o número da EVO. Uma conveniência de importação não vale
perder o WhatsApp do negócio.

*(A Cloud API oficial existe e é conforme, mas cobre só as mensagens que passam
pelo número de negócio via API — não o histórico pessoal.)*

**Recomendação: caminho A.** Se um dia o B for desejado, o desenho abaixo não
muda — só a origem dos arquivos.

---

## O desenho

### Novo: `agent/whatsapp.py`

O único arquivo que entende o formato do WhatsApp, como `pdftext.py` é o único
que entende PDF.

- `parse(path)` → lista de `(quando, quem, texto, anexo)`.
- **Deriva o formato do arquivo, não assume.** Android escreve
  `DD/MM/AAAA HH:MM - Fulano: texto`; iOS escreve
  `[DD/MM/AAAA HH:MM:SS] Fulano: texto`; e o separador de data muda com o
  locale. Detectar pelas primeiras linhas e falhar dizendo o que viu é melhor
  que uma regex que funciona num celular e em nenhum outro.
- Linhas sem carimbo de hora são **continuação** da mensagem anterior — uma
  mensagem de três parágrafos são três linhas no arquivo.
- Mensagens de sistema (aviso de criptografia, entrou/saiu do grupo) são
  descartadas, e o número descartado é reportado.
- Anexos aparecem como `<Mídia oculta>` ou `IMG-…jpg (arquivo anexado)`.

### O que vira nota

O teto de 2 MB do indexador ([../agent/vault.py](../agent/vault.py)) já obriga
a quebrar, e a quebra útil é por mês:

```
whatsapp/
  contacts/
    caroline-lemunha.md              type: person, aliases: [Carol, +55 47 ...]
    comercial-parinox.md
  2026-07/
    caroline-lemunha.md              conversa do mês, com [[Caroline Lemunha]]
  media/
    IMG-20260721-WA0001.jpg
```

A nota do mês abre com frontmatter (`type`, `date`, participantes) e o corpo é
a conversa em markdown. O wikilink para o contato é o que cria a aresta.

**Uma melhoria pequena que isto pede:** `FOLDER_TYPES` só conhece nomes em
inglês, e o vault é em português. Acrescentar `contatos`, `clientes`,
`projetos`, `reunioes`, `faturas`, `tarefas` e `notas` é uma linha e melhora
tudo, não só isto.

### As duas raízes

`JARVIS_VAULTS` já é separado por ponto-e-vírgula e já aceita várias pastas.
Trabalho e pessoal viram duas, e desligar a pessoal é apagar um trecho do
`.env` e apertar **Reindexar** — que já existe.

Vale um passo a mais: um **liga/desliga por raiz na página**, ao lado do painel
Ferramentas. Uma pasta que se desliga com um clique é diferente de uma que
exige editar arquivo.

### Escreve pelo `edit.py`

A importação não escreve direto: chama `edit.write()`, que prova contenção e
guarda cópia. Assim uma importação ruim é desfeita pelo painel Alterações, em
vez de ser limpa à mão.

### As mídias

Vão junto, e agora isso rende de verdade: ele **enxerga** (ver
[../agent/llm.py](../agent/llm.py), `_stdin_for`). Uma foto de orçamento que
chegou no zap deixa de ser arquivo morto. As imagens ficam em `media/` e a nota
do mês as referencia pelo nome — a mesma coisa que `/api/file` já faz com os
PDFs.

---

## O que isto custa, dito antes de construir

- **Volume.** 30 conversas ativas por dois anos são facilmente 100 mil
  mensagens. Elas competem com os 170 documentos de negócio na recuperação, e é
  exatamente por isso que separar em duas raízes foi a escolha certa.
- **A busca é lexical.** BM25 sobre conversa informal acha menos do que sobre
  documento — gente escreve "vc manda ate qnd?". A expansão de consulta ajuda,
  e o Ollama ajudaria mais ([../agent/embed.py](../agent/embed.py) está pronto
  e dormente).
- **O histórico já é o ponto mais pessoal do JARVIS**, e isto o multiplica.
  Vale reler o padrão do [../agent/share.py](../agent/share.py): nada disso sai
  daqui por acidente.

---

## Verificação

**O parser, contra arquivos de verdade.** `tests/test_whatsapp.py` com um
export sintético de cada formato (Android, iOS, com e sem mídia), mais os casos
que quebram parsers ingênuos: mensagem de várias linhas, mensagem contendo `:`
e `-`, nome de contato com emoji, mensagem apagada, e um arquivo cujo formato
não é reconhecido — que tem que falhar dizendo o que viu, não silenciosamente.

**A importação, num vault descartável.** Nunca contra o vault real.
[../tests/test_edit.py](../tests/test_edit.py) já tem a trava que impede o
teste de escapar do sandbox — o mesmo padrão se aplica aqui, e ela existe
porque a primeira versão daquele teste escreveu um arquivo dentro do vault de
verdade.

**O grafo.** Antes: 170 nós, 0 ligações. Depois de importar uma conversa: as
notas do mês têm que apontar para o contato, e o contato tem que aparecer como
`person`. Se as arestas não aparecerem, a importação não valeu o custo.

**Nada regrediu.** A suíte inteira (`python tests/run.py`, hoje 15 arquivos).

---

## O que fazer primeiro

Não a importação. **Exportar uma conversa só** e largar o `.txt` na pasta do
vault, sem código nenhum. Ele já vai ler. Uma tarde com isso responde o que
nenhum plano responde: se as respostas melhoram o bastante para justificar as
100 mil mensagens.

---

## Fontes

- [Como exportar conversa do WhatsApp (2026)](https://www.mosaicchats.com/blog/how-to-export-whatsapp-chat)
- [Limites de 40.000 / 10.000 mensagens](https://printchat.app/en/blog/export-more-than-40000-whatsapp-messages)
- [Avisos e banimentos com whatsmeow e Baileys](https://github.com/tulir/whatsmeow/issues/810)
- [Risco de banimento com API não-oficial](https://sporesec.com/en/blog/whatsapp-unofficial-api-ban-risk)
- [O que o relatório "Solicitar informações da conta" contém](https://www.wati.io/en/blog/whatsapp-account-info-report/)
