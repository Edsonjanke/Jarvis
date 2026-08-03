"""generate.py — builds data/demo_vault from a fixed seed.

Same seed, same graph, every run. Nothing here reads your real folders, and
nothing here writes outside data/demo_vault.

    python data/generate.py

╔═══════════════════════════════════════════════════════════════════════════╗
║  PLACEHOLDER CONTENT.  Everything JARVIS says in demo mode comes out of   ║
║  the PROFILE block below. It is invented, generic, and shaped like a      ║
║  small independent studio because the real profile has not landed yet.    ║
║  Swap PROFILE for the real business and rerun — nothing else changes.     ║
╚═══════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import random
import re
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

SEED = 1729
BASE_DATE = date(2026, 8, 2)          # fixed, so dates are reproducible too
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "demo_vault"


# ---------------------------------------------------------------------------
# PROFILE — the one block to replace
# ---------------------------------------------------------------------------

PROFILE = {
    "operator": "Edson",
    "business": "an independent design-and-build studio",
    "currency": "£",
    "offerings": [
        ("Site build", 6000, 14000, "project"),
        ("Design sprint", 2400, 4200, "week"),
        ("Care plan", 450, 1200, "month"),
        ("Audit", 900, 1800, "one-off"),
        ("Integration work", 1800, 5500, "project"),
    ],
    "clients": [
        ("Harrow & Vane", "furniture retail", "Leeds"),
        ("Northsound Audio", "hardware", "Glasgow"),
        ("Pellworth Legal", "professional services", "London"),
        ("Bramble Bakery", "food & drink", "Bristol"),
        ("Kestrel Fitness", "health", "Manchester"),
        ("Orlin Freight", "logistics", "Rotterdam"),
    ],
    "first_names": [
        "Aisha", "Bruno", "Cara", "Dmitri", "Elin", "Femi", "Greta", "Hal",
        "Ines", "Jonah", "Kira", "Luca", "Mira", "Noor", "Otto", "Priya",
        "Quinn", "Rafa", "Sena", "Tomas",
    ],
    "last_names": [
        "Achebe", "Berg", "Cortez", "Duval", "Esposito", "Falk", "Gallo",
        "Hoffman", "Iqbal", "Jansen", "Keller", "Lindqvist", "Moreau",
        "Nkemdi", "Ostrom", "Pires", "Rahman", "Sandoval", "Tanaka", "Vance",
    ],
    "project_kinds": [
        "Storefront rebuild", "Checkout rework", "Brand refresh",
        "Catalogue migration", "Booking flow", "Client portal",
        "Subscription launch", "Performance pass", "Wholesale portal",
        "Content model rewrite",
    ],
    "meeting_kinds": [
        "Kickoff", "Weekly check-in", "Scope review", "Design walkthrough",
        "Handover", "Retro", "Budget conversation", "Technical review",
    ],
    "note_topics": [
        ("Pricing ladder", "pricing"),
        ("Why the retainer keeps slipping", "retainers"),
        ("Discovery questions that actually work", "process"),
        ("What a good handover looks like", "process"),
        ("Hosting cost per client", "costs"),
        ("When to say no", "positioning"),
        ("Scope creep early-warning signs", "process"),
        ("Rate review, annual", "pricing"),
        ("The two-week rule", "process"),
        ("Referral sources, ranked", "growth"),
        ("Contract clauses worth keeping", "legal"),
        ("Time tracking, honestly", "process"),
        ("Where the margin actually goes", "costs"),
        ("Onboarding checklist", "process"),
        ("Post-launch support window", "process"),
        ("What clients ask before they buy", "sales"),
        ("Proposal template notes", "sales"),
        ("Tools I pay for", "costs"),
        ("Deposit policy", "cashflow"),
        ("Late payment, what works", "cashflow"),
        ("Quarter review", "planning"),
        ("Capacity, realistically", "planning"),
        ("The one-page brief", "process"),
        ("Saying the number first", "sales"),
    ],
    "hub_notes": [
        ("Operating principles", "positioning",
         "The spine note. Most other notes point back here."),
        ("Client health board", "clients",
         "One line per client, updated when something changes."),
        ("Money map", "cashflow",
         "Where revenue comes from and when it lands."),
    ],
}

RISKS = [
    "waiting on content from the client",
    "third-party API rate limits still unconfirmed",
    "scope grew by one page since the estimate",
    "sign-off sits with someone on leave",
    "no staging environment yet",
    "legacy data is dirtier than the sample suggested",
]

WINS = [
    "shipped a week early",
    "cut page weight by half",
    "support tickets down after the rewrite",
    "client renewed without being asked",
    "handover took one call instead of three",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def slug(text: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return out or "note"


def money(value: int) -> str:
    return f"{PROFILE['currency']}{value:,}"


def write(rel: str, body: str) -> None:
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.rstrip() + "\n", encoding="utf-8", newline="\n")


def frontmatter(**fields: object) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if value is None or value == [] or value == "":
            continue
        if isinstance(value, (list, tuple)):
            lines.append(f"{key}: [{', '.join(str(v) for v in value)}]")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# a very small PDF writer, so the PDF path in vault.py is actually exercised
# ---------------------------------------------------------------------------

def _escape_pdf(text: str) -> str:
    """Escape for a PDF literal string, WinAnsi (cp1252) as octal escapes.

    Everything stays ASCII on the wire, so '£' survives as \\243 rather than
    turning into '?' — which would make the rate card quote a wrong number.
    """
    out: list[str] = []
    for ch in text:
        if ch in "\\()":
            out.append("\\" + ch)
        elif 32 <= ord(ch) < 127:
            out.append(ch)
        else:
            try:
                out.append("".join(f"\\{b:03o}" for b in ch.encode("cp1252")))
            except UnicodeEncodeError:
                out.append("?")
    return "".join(out)


def pdf_bytes(title: str, lines: list[str]) -> bytes:
    """Uncompressed single-font PDF. Enough to prove the extractor works."""
    per_page = 44
    pages = [lines[i : i + per_page] for i in range(0, len(lines), per_page)] or [[]]

    objects: list[bytes] = []          # index 0 -> object 1

    def add(body: str) -> int:
        objects.append(body.encode("latin-1", "replace"))
        return len(objects)

    add("PLACEHOLDER")                 # 1 catalog, patched below
    add("PLACEHOLDER")                 # 2 pages, patched below
    font_no = add(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        "/Encoding /WinAnsiEncoding >>"
    )

    page_numbers: list[int] = []
    for page_lines in pages:
        parts = ["BT", "/F1 16 Tf", "54 780 Td", f"({_escape_pdf(title)}) Tj", "ET"]
        y = 748
        for line in page_lines:
            parts += ["BT", "/F1 11 Tf", f"54 {y} Td", f"({_escape_pdf(line)}) Tj", "ET"]
            y -= 16
        stream = "\n".join(parts)
        content_no = add(
            f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
        )
        page_no = add(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_no} 0 R >> >> "
            f"/Contents {content_no} 0 R >>"
        )
        page_numbers.append(page_no)

    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{n} 0 R" for n in page_numbers)
    objects[1] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_numbers)} >>"
    ).encode("latin-1")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode("latin-1")
    return bytes(out)


def write_pdf(rel: str, title: str, lines: list[str]) -> None:
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf_bytes(title, lines))


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------

def build() -> dict[str, int]:
    rng = random.Random(SEED)
    counts: dict[str, int] = {}

    people: list[dict] = []
    clients: list[dict] = []
    projects: list[dict] = []
    invoices: list[dict] = []
    meetings: list[dict] = []

    # -- clients and their people -------------------------------------------
    used_names: set[str] = set()
    for ci, (name, sector, city) in enumerate(PROFILE["clients"]):
        client = {"name": name, "sector": sector, "city": city, "people": [], "projects": []}
        for _ in range(rng.randint(2, 4)):
            while True:
                full = f"{rng.choice(PROFILE['first_names'])} {rng.choice(PROFILE['last_names'])}"
                if full not in used_names:
                    used_names.add(full)
                    break
            person = {
                "name": full,
                "client": name,
                "role": rng.choice(
                    ["founder", "operations lead", "marketing lead",
                     "finance", "product manager", "engineer"]
                ),
            }
            people.append(person)
            client["people"].append(full)
        clients.append(client)

        # sample without replacement: two projects with the same client and
        # kind would slug to the same filename and silently overwrite
        for kind in rng.sample(PROFILE["project_kinds"], k=rng.randint(2, 3)):
            title = f"{name} — {kind}"
            offering = rng.choice(PROFILE["offerings"])
            value = rng.randrange(offering[1], offering[2] + 1, 250)
            started = BASE_DATE - timedelta(days=rng.randint(20, 400))
            status = rng.choice(
                ["active", "active", "active", "delivered", "delivered", "paused"]
            )
            project = {
                "title": title, "client": name, "kind": kind,
                "offering": offering[0], "value": value, "status": status,
                "started": started, "lead": rng.choice(client["people"]),
                "risk": rng.choice(RISKS), "win": rng.choice(WINS),
            }
            projects.append(project)
            client["projects"].append(title)

    # -- invoices ------------------------------------------------------------
    for pi, project in enumerate(projects):
        for k in range(rng.randint(1, 3)):
            issued = project["started"] + timedelta(days=30 * (k + 1) + rng.randint(0, 12))
            if issued > BASE_DATE:
                continue
            share = rng.choice([0.4, 0.5, 0.5, 0.6, 1.0])
            amount = int(project["value"] * share / 50) * 50
            paid = rng.random() < (0.75 if project["status"] == "delivered" else 0.45)
            # The qualifier matters more than the number. Carry it explicitly.
            if paid:
                state, why = "paid", "settled in full"
            elif share < 1.0:
                state, why = "part-invoiced", "staged billing — the work is still running"
            else:
                state, why = "outstanding", f"issued {(BASE_DATE - issued).days} days ago, unpaid"
            invoices.append({
                "ref": f"INV-{2600 + len(invoices)}",
                "project": project["title"], "client": project["client"],
                "amount": amount, "issued": issued, "state": state, "why": why,
                "share": share,
            })

    # -- meetings ------------------------------------------------------------
    for project in projects:
        for _ in range(rng.randint(1, 4)):
            when = project["started"] + timedelta(days=rng.randint(1, 240))
            if when > BASE_DATE:
                when = BASE_DATE - timedelta(days=rng.randint(1, 25))
            kind = rng.choice(PROFILE["meeting_kinds"])
            attendees = rng.sample(
                [p for p in people if p["client"] == project["client"]],
                k=min(2, len([p for p in people if p["client"] == project["client"]])),
            )
            meetings.append({
                "title": f"{when.isoformat()} {kind} — {project['client']}",
                "kind": kind, "project": project["title"], "client": project["client"],
                "when": when, "attendees": [a["name"] for a in attendees],
                "decision": rng.choice([
                    "agreed to push the launch by a week",
                    "signed off the design direction",
                    "deferred the integration to phase two",
                    "confirmed the budget as quoted",
                    "asked for a fixed price instead of day rate",
                    "reduced scope to hit the date",
                ]),
                "action": rng.choice([
                    "send revised estimate",
                    "share staging link",
                    "chase the outstanding invoice",
                    "book the handover session",
                    "write up the scope change",
                ]),
            })

    # -- write people --------------------------------------------------------
    for person in sorted(people, key=lambda p: p["name"]):
        their_projects = [p["title"] for p in projects if p["lead"] == person["name"]]
        body = [
            frontmatter(
                title=person["name"], type="person", client=person["client"],
                role=person["role"], tags=["person"],
            ),
            f"# {person['name']}",
            "",
            f"{person['role'].title()} at [[{person['client']}]] "
            f"({[c for c in clients if c['name'] == person['client']][0]['city']}).",
            "",
        ]
        if their_projects:
            body.append("Point of contact on:")
            body += [f"- [[{t}]]" for t in their_projects]
            body.append("")
        body.append(f"Prefers {rng.choice(['email', 'a short call', 'written updates', 'Slack'])}. "
                    f"{rng.choice(['Decisive.', 'Needs a nudge.', 'Reads everything.', 'Skims.'])}")
        write(f"people/{slug(person['name'])}.md", "\n".join(body))
    counts["people"] = len(people)

    # -- write clients -------------------------------------------------------
    for client in clients:
        live = [p for p in projects if p["client"] == client["name"] and p["status"] == "active"]
        billed = sum(i["amount"] for i in invoices if i["client"] == client["name"])
        body = [
            frontmatter(
                title=client["name"], type="client", sector=client["sector"],
                city=client["city"], tags=["client"],
            ),
            f"# {client['name']}",
            "",
            f"{client['sector'].title()}, based in {client['city']}. "
            f"{len(live)} live project{'s' if len(live) != 1 else ''}, "
            f"{money(billed)} invoiced to date.",
            "",
            "## People",
            *[f"- [[{name}]]" for name in client["people"]],
            "",
            "## Projects",
            *[f"- [[{title}]]" for title in client["projects"]],
            "",
            "## Notes",
            f"Came in via {rng.choice(['a referral', 'an old contact', 'inbound', 'a past client'])}. "
            f"{rng.choice(['Pays on time.', 'Pays late, always settles.', 'Needs a reminder every time.', 'Pays on the day.'])}",
            "",
            "See also [[Client health board]] and [[Operating principles]].",
        ]
        write(f"clients/{slug(client['name'])}.md", "\n".join(body))
    counts["clients"] = len(clients)

    # -- write projects ------------------------------------------------------
    for project in projects:
        related = [i for i in invoices if i["project"] == project["title"]]
        sessions = [m for m in meetings if m["project"] == project["title"]]
        body = [
            frontmatter(
                title=project["title"], type="project", client=project["client"],
                status=project["status"], value=project["value"],
                offering=project["offering"], started=project["started"].isoformat(),
                tags=["project", project["status"]],
            ),
            f"# {project['title']}",
            "",
            f"{project['offering']} for [[{project['client']}]], quoted at "
            f"{money(project['value'])}. Started {project['started'].isoformat()}. "
            f"Status: **{project['status']}**.",
            "",
            f"Lead contact is [[{project['lead']}]].",
            "",
            "## Risk",
            f"- {project['risk']}",
            "",
        ]
        if project["status"] == "delivered":
            body += ["## Outcome", f"- {project['win']}", ""]
        if related:
            body.append("## Invoices")
            body += [
                f"- [[{i['ref']}]] — {money(i['amount'])}, {i['state']} ({i['why']})"
                for i in related
            ]
            body.append("")
        if sessions:
            body.append("## Meetings")
            body += [f"- [[{m['title']}]]" for m in sessions]
            body.append("")
        body.append(f"Priced off [[Pricing ladder]].")
        write(f"projects/{slug(project['title'])}.md", "\n".join(body))
    counts["projects"] = len(projects)

    # -- write invoices ------------------------------------------------------
    for invoice in invoices:
        body = [
            frontmatter(
                title=invoice["ref"], type="invoice", client=invoice["client"],
                amount=invoice["amount"], issued=invoice["issued"].isoformat(),
                state=invoice["state"], tags=["invoice", invoice["state"]],
            ),
            f"# {invoice['ref']}",
            "",
            f"{money(invoice['amount'])} to [[{invoice['client']}]] for "
            f"[[{invoice['project']}]], issued {invoice['issued'].isoformat()}.",
            "",
            f"**{invoice['state']}** — {invoice['why']}.",
            "",
            f"{int(invoice['share'] * 100)}% of the project value. "
            "A part-invoice is a billing stage, not a discount.",
            "",
            "Terms per [[Deposit policy]]. Chasing rules in [[Late payment, what works]].",
        ]
        write(f"invoices/{slug(invoice['ref'])}.md", "\n".join(body))
    counts["invoices"] = len(invoices)

    # -- write meetings ------------------------------------------------------
    for meeting in meetings:
        body = [
            frontmatter(
                title=meeting["title"], type="meeting", client=meeting["client"],
                date=meeting["when"].isoformat(), tags=["meeting"],
            ),
            f"# {meeting['title']}",
            "",
            f"{meeting['kind']} on [[{meeting['project']}]] with "
            + ", ".join(f"[[{a}]]" for a in meeting["attendees"]) + ".",
            "",
            "## Decision",
            f"- {meeting['decision']}",
            "",
            "## Action",
            f"- {meeting['action']}",
            "",
            f"Client file: [[{meeting['client']}]].",
        ]
        write(f"meetings/{slug(meeting['title'])}.md", "\n".join(body))
    counts["meetings"] = len(meetings)

    # -- write notes ---------------------------------------------------------
    note_titles = [t for t, _ in PROFILE["note_topics"]]
    hub_titles = [t for t, _, _ in PROFILE["hub_notes"]]

    one_liners = [
        "charge for the thinking, not the hours",
        "the deposit sets the tone for the whole job",
        "a slow no is worse than a fast one",
        "the second project is where the margin is",
        "every unbilled hour is a decision you made",
    ]

    for title, topic in PROFILE["note_topics"]:
        links = rng.sample(note_titles, k=rng.randint(1, 3))
        links = [t for t in links if t != title]
        links.append(rng.choice(hub_titles))
        if rng.random() < 0.5:
            links.append(rng.choice(clients)["name"])
        if rng.random() < 0.35:
            links.append(rng.choice(projects)["title"])
        body = [
            frontmatter(title=title, type="note", tags=["note", topic]),
            f"# {title}",
            "",
            rng.choice([
                "Written after the third time this came up.",
                "Rough. Revisit next quarter.",
                "This one holds up.",
                "Half of this is wrong and I know which half.",
            ]),
            "",
            "The short version: " + rng.choice(one_liners) + ".",
            "",
            "Related: " + ", ".join(f"[[{t}]]" for t in dict.fromkeys(links)) + ".",
        ]
        write(f"notes/{slug(title)}.md", "\n".join(body))
    counts["notes"] = len(PROFILE["note_topics"])

    # -- hub notes, deliberately over-connected ------------------------------
    for title, topic, blurb in PROFILE["hub_notes"]:
        if title == "Client health board":
            rows = [f"- [[{c['name']}]] — {c['sector']}, {len(c['projects'])} projects" for c in clients]
        elif title == "Money map":
            rows = [f"- {name}: {money(lo)}–{money(hi)} per {unit}"
                    for name, lo, hi, unit in PROFILE["offerings"]]
            rows += [f"- Open: [[{i['ref']}]] {money(i['amount'])} ({i['state']})"
                     for i in invoices if i["state"] != "paid"][:8]
        else:
            rows = [f"- [[{t}]]" for t in note_titles]
        body = [
            frontmatter(title=title, type="note", tags=["note", topic, "hub"]),
            f"# {title}",
            "",
            blurb,
            "",
            *rows,
            "",
            "Sibling hubs: " + ", ".join(f"[[{t}]]" for t in hub_titles if t != title) + ".",
        ]
        write(f"notes/{slug(title)}.md", "\n".join(body))
    counts["notes"] += len(PROFILE["hub_notes"])

    # -- reference PDFs ------------------------------------------------------
    write_pdf(
        "reference/rate-card.pdf",
        "Rate card 2026",
        [f"{name}: {money(lo)} to {money(hi)} per {unit}"
         for name, lo, hi, unit in PROFILE["offerings"]]
        + ["", "Deposit: 40% on signature, non-refundable.",
           "Balance: on handover, net 14.",
           "Out of scope work is quoted separately, never absorbed."],
    )
    write_pdf(
        "reference/standard-terms.pdf",
        "Standard terms of engagement",
        ["1. Scope is what the estimate says and nothing else.",
         "2. Change requests are priced before they are started.",
         "3. Payment is net 14 from the invoice date.",
         "4. Late payment accrues interest at 8% above base.",
         "5. Work stops if an invoice passes 30 days.",
         "6. Source files transfer on final payment.",
         "7. Either side may end a retainer with 30 days notice."],
    )
    biggest = sorted(clients, key=lambda c: -len(c["projects"]))[0]
    write_pdf(
        f"reference/{slug(biggest['name'])}-brief.pdf",
        f"{biggest['name']} — original brief",
        [f"Client: {biggest['name']} ({biggest['sector']}, {biggest['city']})",
         "",
         "Objective: replace the ageing storefront without losing search rankings.",
         "Constraints: no downtime, existing catalogue must migrate intact.",
         "Success: checkout completion above 62%, page weight under 900kb.",
         "",
         "Out of scope: photography, copywriting, ongoing hosting."],
    )
    counts["reference"] = 3

    return counts


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    # Only ever touch data/demo_vault, and only inside this repo.
    if OUT.exists():
        if OUT.name != "demo_vault" or ROOT not in OUT.parents:
            print(f"refusing to clear {OUT}", file=sys.stderr)
            return 1
        shutil.rmtree(OUT)

    counts = build()
    total = sum(counts.values())
    print(f"\n  demo vault -> {OUT}")
    print(f"  seed {SEED}, base date {BASE_DATE.isoformat()}\n")
    for kind, n in counts.items():
        print(f"    {kind.ljust(10)} {str(n).rjust(4)}")
    print(f"    {'total'.ljust(10)} {str(total).rjust(4)}\n")
    print("  PLACEHOLDER content — swap PROFILE in this file for the real business.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
