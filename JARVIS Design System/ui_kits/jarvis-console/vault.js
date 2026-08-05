/* Demo vault — the profile block from Jarvis/data/generate.py, shrunk to 44
   notes so the graph reads at card size. Same shapes, same seed idea: fixed
   data, identical picture every load. */
(function () {
  const clients = [
    ["Harrow & Vane", "furniture retail", "Leeds"],
    ["Northsound Audio", "hardware", "Glasgow"],
    ["Pellworth Legal", "professional services", "London"],
    ["Bramble Bakery", "food & drink", "Bristol"],
    ["Kestrel Fitness", "health", "Manchester"],
    ["Orlin Freight", "logistics", "Rotterdam"],
  ];
  const projects = [
    ["Storefront rebuild", 0], ["Checkout rework", 0], ["Brand refresh", 1],
    ["Catalogue migration", 2], ["Booking flow", 4], ["Client portal", 5],
    ["Subscription launch", 3], ["Performance pass", 1],
  ];
  const meetings = [
    ["Kickoff — Storefront rebuild", 0], ["Weekly check-in — Checkout rework", 1],
    ["Scope review — Brand refresh", 2], ["Handover — Booking flow", 4],
    ["Budget conversation — Client portal", 5],
  ];
  const invoices = [
    ["Fatura 4471", 0, "£6,200"], ["Fatura 4472", 1, "£2,400"],
    ["Fatura 4468", 2, "£1,800"], ["Fatura 4475", 4, "£4,150"],
    ["Fatura 4477", 5, "£980"],
  ];
  const people = [
    ["Aisha Rahman", 0], ["Bruno Cortez", 1], ["Elin Berg", 2],
    ["Femi Achebe", 3], ["Priya Iqbal", 4], ["Tomas Falk", 5],
  ];
  const notes = [
    ["Operating principles", "The spine note. Most other notes point back here.", ["positioning"]],
    ["Client health board", "One line per client, updated when something changes.", ["clients"]],
    ["Money map", "Where revenue comes from and when it lands.", ["cashflow"]],
    ["Deposit policy", "Half up front, the rest on handover. The deposit is what buys the slot in the calendar — a project without one is a conversation, and the calendar stays open.", ["cashflow"]],
    ["Pricing ladder", "Five offerings, five ceilings. Say the number first; the conversation after it is the real brief.", ["pricing"]],
    ["Late payment, what works", "Chase on the day, not the week. Name the invoice and the amount in the first line.", ["cashflow"]],
    ["Scope creep early-warning signs", "Three: a new name on the call, a deadline that moves toward you, and the word 'quick'.", ["process"]],
    ["Where the margin actually goes", "Hosting, the two hours before every call, and the fortnight after handover nobody quotes for.", ["costs"]],
    ["Capacity, realistically", "Two projects, one care plan, nothing else. The third project is always paid for by the first two.", ["planning"]],
    ["The two-week rule", "Nothing goes on the board that cannot start within a fortnight.", ["process"]],
  ];
  const refs = [
    ["Contrato padrão 2026", "reference"],
    ["Tabela de preços — julho", "reference"],
  ];

  const nodes = [];
  const edges = [];
  const bodies = {};
  const add = (id, title, type, rel, body, meta) => {
    nodes.push({ id, title, type, rel });
    bodies[id] = { body: body || "", meta: meta || {} };
  };
  const link = (a, b) => edges.push({ source: a, target: b });
  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  clients.forEach(([name, trade, city], i) => {
    const id = "demo/clients/" + slug(name) + ".md";
    add(id, name, "client", "clients/" + slug(name) + ".md",
      name + " — " + trade + ", " + city + ". Two projects live, one care plan. Paid on time twice, late once.",
      { trade: trade, city: city, since: "2024" });
  });
  projects.forEach(([name, ci], i) => {
    const id = "demo/projects/" + slug(name) + ".md";
    add(id, name, "project", "projects/" + slug(name) + ".md",
      name + " for " + clients[ci][0] + ". Fixed price, two-week discovery, handover in six.",
      { client: clients[ci][0], status: i % 3 === 0 ? "live" : "closed" });
    link(id, "demo/clients/" + slug(clients[ci][0]) + ".md");
  });
  meetings.forEach(([name, pi]) => {
    const id = "demo/meetings/" + slug(name) + ".md";
    add(id, name, "meeting", "meetings/" + slug(name) + ".md",
      "Present: the client and me. Decisions taken are in the project note; this is what was said.",
      { when: "2026-07-2" + (pi + 1) });
    link(id, "demo/projects/" + slug(projects[pi][0]) + ".md");
  });
  invoices.forEach(([name, ci, amount]) => {
    const id = "demo/invoices/" + slug(name) + ".pdf";
    add(id, name, "invoice", "invoices/" + slug(name) + ".pdf",
      "", { amount: amount, due: "2026-08-1" + (ci + 1), client: clients[ci][0] });
    bodies[id].warning = "no text extracted — scanned PDF";
    link(id, "demo/clients/" + slug(clients[ci][0]) + ".md");
  });
  people.forEach(([name, ci]) => {
    const id = "demo/people/" + slug(name) + ".md";
    add(id, name, "person", "people/" + slug(name) + ".md",
      name + " is the contact at " + clients[ci][0] + ". Answers email, not calls.",
      { at: clients[ci][0] });
    link(id, "demo/clients/" + slug(clients[ci][0]) + ".md");
  });
  notes.forEach(([title, body, tags], i) => {
    const id = "demo/notes/" + slug(title) + ".md";
    add(id, title, "note", "notes/" + slug(title) + ".md", body, { tags: tags.join(", ") });
    if (i > 0) link(id, "demo/notes/operating-principles.md");
  });
  refs.forEach(([title]) => {
    const id = "demo/reference/" + slug(title) + ".pdf";
    add(id, title, "reference", "reference/" + slug(title) + ".pdf",
      "Assinado em janeiro. Cláusula 7 é a que importa: 30 dias, sem exceção.", { pages: "4" });
    link(id, "demo/notes/deposit-policy.md");
  });

  link("demo/notes/deposit-policy.md", "demo/notes/money-map.md");
  link("demo/notes/late-payment-what-works.md", "demo/notes/money-map.md");
  link("demo/notes/client-health-board.md", "demo/clients/harrow-vane.md");
  link("demo/notes/client-health-board.md", "demo/clients/orlin-freight.md");
  link("demo/notes/client-health-board.md", "demo/clients/bramble-bakery.md");
  link("demo/notes/money-map.md", "demo/invoices/fatura-4471.pdf");
  link("demo/notes/money-map.md", "demo/invoices/fatura-4475.pdf");
  link("demo/notes/pricing-ladder.md", "demo/projects/storefront-rebuild.md");
  link("demo/notes/capacity-realistically.md", "demo/projects/booking-flow.md");
  link("demo/notes/scope-creep-early-warning-signs.md", "demo/projects/checkout-rework.md");
  link("demo/notes/deposit-policy.md", "demo/clients/harrow-vane.md");
  link("demo/notes/where-the-margin-actually-goes.md", "demo/notes/money-map.md");

  const degree = {};
  edges.forEach((e) => {
    degree[e.source] = (degree[e.source] || 0) + 1;
    degree[e.target] = (degree[e.target] || 0) + 1;
  });
  nodes.forEach((n) => { n.degree = degree[n.id] || 0; });

  const counts = {};
  nodes.forEach((n) => { counts[n.type] = (counts[n.type] || 0) + 1; });

  const hubs = nodes.slice().sort((a, b) => b.degree - a.degree).slice(0, 5).map((n) => n.id);

  window.VAULT = {
    nodes: nodes, edges: edges, bodies: bodies, counts: counts, hubs: hubs,
    stats: [["mode", "demo"], ["notes", String(nodes.length)], ["links", String(edges.length)],
            ["indexed in", "0.4s"], ["model", "sonnet-4.6"], ["listen", "missing"], ["speak", "this machine"]],
    brains: [
      { id: "claude-sonnet-4-6", label: "Sonnet 4.6", note: "rápido, o padrão", current: true },
      { id: "claude-opus-4-1", label: "Opus 4.1", note: "mais caro, para relatórios", current: false },
      { id: "claude-haiku-4-5", label: "Haiku 4.5", note: "para buscas curtas", current: false },
    ],
    tools: [
      { name: "drive", label: "Google Drive", authenticated: false, needs: "GOOGLE_OAUTH_TOKEN", on: false },
      { name: "gmail", label: "Gmail", authenticated: false, needs: "GOOGLE_OAUTH_TOKEN", on: false },
      { name: "fetch", label: "Fetch (web)", authenticated: true, on: false },
    ],
    skills: [
      { name: "Cobrança", description: "cobrar fornecedor, boleto vencido, atraso, inadimplência…", always: false },
      { name: "Fechamento", description: "", problem: "sem description — nunca casa" },
    ],
    edits: [
      { id: "e2", when: "04/08/2026, 11:02", path: "demo/notes/client-health-board.md", action: "escreveu", before: 1840, after: 1952, undone: false },
      { id: "e1", when: "03/08/2026, 16:20", path: "demo/notes/money-map.md", action: "escreveu", before: 2210, after: 2210, undone: true },
    ],
    facts: [
      { name: "jatinox-prazo", when: "2026-07-30", text: "Boleto da Jatinox sempre 28 dias, nunca 30." },
      { name: "sem-backup", when: "2026-07-22", text: "Não existe backup do Evo-SI. Qualquer escrita precisa de cópia antes." },
    ],
    turns: [
      { when: "04/08/2026, 14:22", question: "quanto está vencido com a Jatinox?", meta: "6 citações · 318 tokens · sonnet-4.6" },
      { when: "03/08/2026, 09:07", question: "o que muda no prazo se eu antecipar?", meta: "2 citações · 1.204 tokens · sonnet-4.6" },
      { when: "02/08/2026, 17:55", question: "quais projetos estão sem depósito?", meta: "0 citações · 96 tokens · sonnet-4.6" },
    ],
    answers: {
      ask: {
        kind: "ask",
        meta: "sonnet-4.6 · read 14 notes · 2 remembered · cobranca · JARVIS.md · 4.1s",
        body: "Metade na assinatura, metade na entrega [demo/notes/deposit-policy.md]. O depósito é o que compra a vaga na agenda — sem ele o projeto é uma conversa e a agenda continua aberta.\n\nA Harrow & Vane é a única cliente com projeto aberto e sem depósito registrado [demo/clients/harrow-vane.md]. A fatura 4471, de £6,200, vence em 11/08 [demo/invoices/fatura-4471.pdf].\n\nO que falta para responder direito sobre hoje: um export de contas a receber com data de hoje. O dado acima é de 28/07.",
        citations: ["demo/notes/deposit-policy.md", "demo/clients/harrow-vane.md", "demo/invoices/fatura-4471.pdf"],
      },
      brief: {
        kind: "brief",
        meta: "sonnet-4.6 · read 22 notes · JARVIS.md · 6.3s",
        body: "· Fatura 4471 (£6,200, Harrow & Vane) vence em 11/08 e não tem depósito lançado.\n· Checkout rework ganhou um nome novo na chamada de segunda — sinal de escopo [demo/notes/scope-creep-early-warning-signs.md].\n· Booking flow entregou; a janela de suporte fecha em 14 dias.\n· Capacidade: dois projetos e um care plan já estão ocupados. O terceiro entra sem margem [demo/notes/capacity-realistically.md].\n· Nada mais mudou desde 28/07.",
        citations: ["demo/notes/scope-creep-early-warning-signs.md", "demo/notes/capacity-realistically.md"],
      },
    },
  };
})();
