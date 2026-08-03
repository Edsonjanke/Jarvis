"""tools.py — WHAT THE MODEL IS ALLOWED TO DO, AND NOTHING ELSE.

Until now the answer was "nothing": llm.py passed `--tools ""` and
`--strict-mcp-config`, and the model could not touch the disk, the network or
anything on this machine. That was a guarantee, and it is worth being precise
about what replaces it.

What replaces it is: **nothing, except what is named here and switched on.**
Never a blanket. The allowlist is built from a file JARVIS owns, `--strict-mcp-config`
stays on forever so nothing from this machine's own configuration can join in,
and the default is empty.

WHAT WE FOUND OUT THE HARD WAY. The six claude.ai connectors on this account —
Slack, Calendar, Drive, Gmail, Notion — are visible to `claude mcp list` but do
NOT exist in print mode. Measured: with the connectors connected, and with
`--strict-mcp-config` dropped, and with `--setting-sources` at its default, the
init event still reported `mcp_servers: []` and zero `mcp__` tools. They are an
interactive-session feature tied to the claude.ai login, not something a
headless run inherits.

So a server has to be declared here, with its own credential. `--mcp-config` is
verified to work in print mode: a declared server appears in the init event.
An unauthenticated one sits at `status: pending` and contributes no tools,
which is exactly what you see below until you add a token.

Run it directly to see what is on:  python -m agent.tools
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python agent/tools.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod

SERVERS_FILE = "mcp-servers.json"
ALLOWED_FILE = "tools-allowed.json"

# Servers JARVIS knows how to describe. Declaring one here does not switch it
# on and does not authenticate it — it only means the panel can offer it and
# say what it needs.
KNOWN = {
    "notion": {
        "label": "Notion",
        "url": "https://mcp.notion.com/mcp",
        "needs": "um token OAuth do Notion (Authorization: Bearer …)",
    },
    "drive": {
        "label": "Google Drive",
        "url": "https://drivemcp.googleapis.com/mcp/v1",
        "needs": "um token OAuth do Google com escopo do Drive",
    },
}


def _read(name: str, fallback):
    try:
        return json.loads((data_mod.state_dir() / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def _write(name: str, value) -> None:
    (data_mod.state_dir() / name).write_text(json.dumps(value, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Which servers exist
# ---------------------------------------------------------------------------

def servers() -> dict[str, dict]:
    """The MCP servers JARVIS declares. Ours alone — never this machine's."""
    declared = _read(SERVERS_FILE, {})
    return declared if isinstance(declared, dict) else {}


def config_path() -> Path | None:
    """A file for --mcp-config, or None when nothing is declared.

    Written fresh each time from what we hold, so the CLI can never be handed
    a server we did not put there.
    """
    declared = servers()
    if not declared:
        return None
    path = data_mod.state_dir() / "mcp-config.json"
    path.write_text(json.dumps({"mcpServers": declared}), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Which tools are permitted
# ---------------------------------------------------------------------------

def allowed() -> list[str]:
    """Tool names the model may call. Empty means it may call nothing."""
    names = _read(ALLOWED_FILE, [])
    return [str(n) for n in names] if isinstance(names, list) else []


def allow(names: list[str]) -> list[str]:
    """Replace the allowlist. The only way anything gets switched on."""
    clean = []
    for name in names or []:
        name = str(name).strip()
        # Tool names are identifiers, and this one ends up on a command line.
        if name and len(name) < 120 and not any(c.isspace() for c in name):
            clean.append(name)
    _write(ALLOWED_FILE, clean)
    return clean


def enabled() -> bool:
    return bool(allowed())


def flags() -> list[str]:
    """The argv fragment llm.py splices in.

    Two invariants live here, and llm.py's tests assert both:
      * --strict-mcp-config is present ALWAYS, switched on or off, so this
        machine's own MCP configuration can never join the session.
      * --tools carries the allowlist verbatim, and "" when it is empty —
        never "default", never omitted.
    """
    names = allowed()
    out = ["--tools", ",".join(names) if names else "",
           "--strict-mcp-config"]
    if names:
        path = config_path()
        if path is not None:
            out += ["--mcp-config", str(path)]
        # Print mode cannot ask anyone for permission, so a tool that would
        # prompt hangs the request instead. Only reachable when something is
        # deliberately switched on.
        out += ["--permission-mode", "dontAsk"]
    return out


def state() -> dict[str, object]:
    """What the panel shows. Honest about what is merely declared."""
    declared = servers()
    on = allowed()
    return {
        "enabled": bool(on),
        "allowed": on,
        "servers": [
            {
                "name": name,
                "label": KNOWN.get(name, {}).get("label", name),
                "declared": name in declared,
                "authenticated": bool(declared.get(name, {}).get("headers")),
                "needs": KNOWN.get(name, {}).get("needs", "uma credencial"),
                # Server-level, because the individual tool names are not
                # knowable until the server authenticates and reports them.
                # `mcp__notion` means every tool that server offers.
                "tools": [f"mcp__{name}"],
            }
            for name in sorted(set(KNOWN) | set(declared))
        ],
        # Said plainly, because it is the thing most likely to surprise.
        "note": ("Os conectores claude.ai (Slack, Gmail, Drive, Notion) não existem "
                 "em modo headless — um servidor precisa ser declarado aqui, com o "
                 "seu próprio token."),
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    info = state()
    print(f"\n  ferramentas  {'ligadas: ' + ', '.join(info['allowed']) if info['enabled'] else 'nenhuma (padrão)'}")
    print(f"  argv         {' '.join(repr(f) for f in flags())}\n")
    for server in info["servers"]:
        mark = "✓" if server["authenticated"] else ("·" if server["declared"] else " ")
        print(f"   {mark} {server['label']:<16} {'declarado' if server['declared'] else 'não declarado'}"
              f"{'' if server['authenticated'] else '  — precisa de ' + server['needs']}")
    print(f"\n  {info['note']}")
    print(f"  declare em: {data_mod.state_dir() / SERVERS_FILE}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
