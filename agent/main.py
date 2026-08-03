"""main.py — the HTTP server and the API.

Standard library only. Binds to localhost by default. Serves exactly two things:
the files in ui/, and a small JSON API over the vault.

    python -m agent.main

Static serving is allowlisted by resolved path, so ../../.env resolves outside
ui/ and is refused. The key never leaves this process.
"""

from __future__ import annotations

import json
import mimetypes
import sys
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod
from agent.vault import Vault

UI_DIR = data_mod.ROOT / "ui"

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")


# ---------------------------------------------------------------------------
# Vault state, rebuilt on demand
# ---------------------------------------------------------------------------

class VaultStore:
    """Holds the current index. One writer at a time, readers never block long."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._vault: Vault | None = None

    def get(self) -> Vault:
        with self._lock:
            if self._vault is None:
                self._vault = Vault.from_config()
            return self._vault

    def rebuild(self) -> Vault:
        with self._lock:
            data_mod.reload_env()
            self._vault = Vault.from_config()
            return self._vault


STORE = VaultStore()


# ---------------------------------------------------------------------------
# Capability report — what is missing is said out loud, never swallowed
# ---------------------------------------------------------------------------

def capabilities() -> dict[str, object]:
    vault = STORE.get()
    return {
        "demo": data_mod.is_demo(),
        "mode_label": data_mod.mode_label(),
        "notes": len(vault.notes),
        "counts": vault.counts_by_type(),
        "roots": [{"label": r.label, "path": str(r.path)} for r in vault.roots],
        "problems": vault.problems,
        "skipped": len(vault.skipped),
        "model": {
            "available": bool(data_mod.anthropic_key()),
            "name": data_mod.anthropic_model() if data_mod.anthropic_key() else None,
            "reason": None if data_mod.anthropic_key()
                      else "no ANTHROPIC_API_KEY in .env — routing falls back to file scoring",
        },
        "voice": {
            "available": bool(data_mod.elevenlabs_key()),
            "voice_id": data_mod.elevenlabs_voice_id() or None,
            "reason": None if data_mod.elevenlabs_key()
                      else "no ELEVENLABS_API_KEY in .env — speech is off",
        },
        # Step 4 wires these. Declared now so the UI can grey them honestly
        # instead of pretending a dead button works.
        "stage": 2,
        "stage_note": "graph and index only — conversation and voice are not wired yet",
    }


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "JARVIS"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # -- plumbing -----------------------------------------------------------

    def log_message(self, fmt: str, *args: object) -> None:
        if self.path.startswith("/api/"):
            sys.stderr.write(f"  {self.command} {self.path} — {fmt % args}\n")

    def _send(self, status: int, body: bytes, ctype: str, *, cache: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=60" if cache else "no-store")
        # Local-only app: no third-party anything, so lock the page down hard.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; media-src 'self' blob:; img-src 'self' data: blob:; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'",
        )
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _fail(self, status: int, message: str) -> None:
        self._json({"error": message}, status)

    # -- routing ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            route = parsed.path
            if route.startswith("/api/"):
                self._api(route, query)
            else:
                self._static(route)
        except BrokenPipeError:
            pass
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._fail(HTTPStatus.INTERNAL_SERVER_ERROR, "server error — see the terminal")

    do_HEAD = do_GET

    def do_POST(self) -> None:  # noqa: N802
        try:
            route = urlparse(self.path).path
            if route == "/api/reindex":
                vault = STORE.rebuild()
                self._json({"ok": True, "notes": len(vault.notes),
                            "seconds": round(vault.build_seconds, 3)})
                return
            self._fail(HTTPStatus.NOT_FOUND, f"no route for POST {route}")
        except BrokenPipeError:
            pass
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._fail(HTTPStatus.INTERNAL_SERVER_ERROR, "server error — see the terminal")

    def _api(self, route: str, query: dict[str, list[str]]) -> None:
        if route == "/api/health":
            self._json(capabilities())
            return

        if route == "/api/graph":
            self._json(STORE.get().graph_payload())
            return

        if route == "/api/note":
            note_id = (query.get("id") or [""])[0]
            note = STORE.get().notes.get(note_id)
            if note is None:
                self._fail(HTTPStatus.NOT_FOUND, f"no note with id {note_id!r}")
                return
            payload = note.to_dict(with_text=True)
            payload["links"] = [
                {"id": other, "title": STORE.get().notes[other].title,
                 "type": STORE.get().notes[other].type,
                 "direction": "out" if other in note.out else "in"}
                for other in sorted(note.out | note.back)
            ]
            self._json(payload)
            return

        if route == "/api/path":
            a = (query.get("a") or [""])[0]
            b = (query.get("b") or [""])[0]
            vault = STORE.get()
            route_ids = vault.shortest_path(a, b)
            self._json({
                "path": route_ids,
                "titles": [vault.notes[i].title for i in route_ids],
                "found": bool(route_ids),
            })
            return

        if route == "/api/search":
            q = (query.get("q") or [""])[0]
            limit = min(25, int((query.get("limit") or ["8"])[0] or 8))
            hits = STORE.get().search(q, limit=limit)
            self._json({
                "query": q,
                "hits": [
                    {"id": h.note.id, "title": h.note.title, "type": h.note.type,
                     "rel": h.note.rel, "score": round(h.score, 3), "snippet": h.snippet}
                    for h in hits
                ],
            })
            return

        self._fail(HTTPStatus.NOT_FOUND, f"no route for GET {route}")

    def _static(self, route: str) -> None:
        rel = "index.html" if route in ("/", "") else route.lstrip("/")
        target = (UI_DIR / rel).resolve()
        try:
            target.relative_to(UI_DIR.resolve())
        except ValueError:
            self._fail(HTTPStatus.FORBIDDEN, "outside the ui folder")
            return
        if not target.is_file():
            self._fail(HTTPStatus.NOT_FOUND, f"no file at {rel}")
            return
        ctype, _ = mimetypes.guess_type(target.name)
        self._send(HTTPStatus.OK, target.read_bytes(),
                   ctype or "application/octet-stream", cache=False)


# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    host, port = data_mod.server_address()
    vault = STORE.get()
    caps = capabilities()

    print(vault.report())
    print(f"  model    {caps['model']['reason'] or caps['model']['name']}")
    print(f"  voice    {caps['voice']['reason'] or 'ElevenLabs key set'}")
    print(f"\n  JARVIS on http://{host}:{port}   (ctrl-c to stop)\n")

    if not UI_DIR.is_dir():
        print(f"  ui/ is missing at {UI_DIR}", file=sys.stderr)
        return 1

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped\n")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
