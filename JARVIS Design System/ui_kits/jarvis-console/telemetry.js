/* Telemetry — the machine-side readouts v2 added to the console. Fixed
   values so every load draws the same picture; the drift in ConsoleV2 walks
   them a few points either way, which is all the movement the source's
   motion rules allow. */
(function () {
  window.TELEMETRY = {
    system: [
      { key: "cpu", label: "CPU", value: 17 },
      { key: "ram", label: "RAM", value: 39 },
      { key: "gpu", label: "GPU", value: 35 },
      { key: "dsk", label: "Disco", value: 52 },
    ],
    core: [
      ["modelo", "sonnet-4.6"],
      ["modo", "ask"],
      ["raciocínio", "87%"],
      ["resposta", "4,1s"],
    ],
    memory: {
      pct: 62,
      rows: [
        ["contexto ativo", "32,4 GB"],
        ["longo prazo", "128,7 GB"],
        ["curto prazo", "18,6 GB"],
      ],
    },
    network: [
      ["nós do vault", String(window.VAULT.nodes.length)],
      ["vínculos", String(window.VAULT.edges.length)],
      ["entrada", "2,4 MB/s"],
      ["saída", "1,8 MB/s"],
    ],
    feed: [
      { at: "22:41", what: "Índice atualizado", tail: "concluído" },
      { at: "22:40", what: "Arquivo lido", tail: "fatura-4471.pdf" },
      { at: "22:38", what: "Ferramenta negada", tail: "Google Drive", tone: "warn" },
      { at: "22:35", what: "Nota escrita", tail: "client-health-board", tone: "accent" },
      { at: "22:33", what: "Sessão aberta", tail: "edson@evo.local" },
    ],
    weather: {
      city: "Rio do Sul, SC",
      temp: "18",
      sky: "chuva fraca",
      rows: [["sensação", "16°C"], ["umidade", "88%"], ["vento", "11 km/h"], ["ar", "bom"]],
      week: [["ter", "19/12"], ["qua", "21/13"], ["qui", "23/14"], ["sex", "20/15"], ["sáb", "18/12"]],
    },
    jobs: [
      ["3", "rodando"],
      ["2", "agendadas"],
      ["5", "concluídas"],
      ["1", "falha"],
    ],
    quick: [
      { id: "voz", icon: "mic", label: "Voz", note: "falta ELEVENLABS_API_KEY", blocked: true },
      { id: "silencio", icon: "volume-x", label: "Silêncio" },
      { id: "reindexar", icon: "scan-line", label: "Reindexar", action: true },
      { id: "analisar", icon: "file-search", label: "Analisar" },
      { id: "treinar", icon: "brain-circuit", label: "Treinar", disabled: true, title: "a etapa 5 liga isto" },
    ],
    shortcuts: [
      { id: "terminal", icon: "square-terminal", label: "Terminal" },
      { id: "cerebro", icon: "database", label: "Cérebro" },
      { id: "ferramentas", icon: "network", label: "Ferramentas" },
      { id: "alteracoes", icon: "workflow", label: "Alterações" },
      { id: "habilidades", icon: "settings", label: "Habilidades" },
    ],
    log: [
      { at: "22:36:58", tag: "sys", text: "índice aberto — " + window.VAULT.nodes.length + " notas, " + window.VAULT.edges.length + " vínculos" },
      { at: "22:37:02", tag: "ok", text: "backend conectado — tudo operacional" },
      { at: "22:37:44", tag: "info", text: "cérebro: sonnet-4.6" },
      { at: "22:38:10", tag: "err", text: "falta ELEVENLABS_API_KEY — voz desligada" },
    ],
  };
})();
