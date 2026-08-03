"""main.py — the HTTP server and the API.

Standard library only. Binds to localhost by default. Serves exactly two things:
the files in ui/, and a small JSON API over the vault.

    python -m agent.main

Static serving is allowlisted by resolved path, so ../../.env resolves outside
ui/ and is refused. The key never leaves this process.
"""

from __future__ import annotations

import base64
import binascii
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

from agent import brain, data as data_mod, embed, llm, memory, tools, voice
from agent.vault import Vault

# A question is a question, not a payload. Anything larger is a mistake or an
# attack, and is refused before it is read into memory.
MAX_BODY_BYTES = 64 * 1024

# Except a recording, which arrives base64'd inside the same JSON envelope so
# that one content-type rule covers every route. 30s of 16 kHz mono WAV is
# ~1 MB, and base64 adds a third.
MAX_AUDIO_BODY_BYTES = 6 * 1024 * 1024

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
        catch_up(self._vault)
        return self._vault


def catch_up(vault: Vault) -> None:
    """Embed anything new, off the critical path.

    Costs nothing and does nothing when Ollama is absent, which is the usual
    case. When it is present, a first run over a real vault takes seconds —
    long enough that nobody should wait for it to see the graph.
    """
    if not embed.available():
        return
    threading.Thread(target=embed.index, args=(vault,), daemon=True,
                     name="jarvis-embed").start()


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
        # The model runs on the Claude subscription signed in on this machine,
        # so there is no key to report — only whether Claude Code is installed
        # and logged in. llm.reason() never spawns anything; the answer was
        # latched at startup by llm.probe().
        "model": {
            "available": llm.available(),
            "name": llm.model_name() if llm.available() else None,
            "reason": llm.reason(),
        },
        # The two halves of voice are no longer the same thing. Listening goes
        # through ElevenLabs and needs a key; speaking is done by the browser
        # out of this machine's own voices, so it costs nothing, needs no key,
        # and no audio leaves the room.
        "voice": {
            "listen": {
                "available": voice.available(),
                "model": voice.model_name() if voice.available() else None,
                "reason": voice.reason(),
            },
            "speak": {"available": True, "engine": "browser"},
            "language": data_mod.language() or None,
        },
        "memory": {
            "facts": len(memory.facts()),
            "limit": memory.MAX_FACTS,
        },
        # Meaning-based recall is optional and normally off. Word-based recall
        # works either way, so this reports a bonus, not a fault.
        "semantic": {
            "available": embed.available(),
            "model": embed.model() if embed.available() else None,
            "reason": embed.reason(),
        },
        # What the model is allowed to reach outside the vault. Empty by
        # default, and on the page rather than in a config file precisely
        # because "it can read your Drive" should never be a quiet setting.
        "tools": tools.state(),
        "stage": 5,
        "stage_note": "",
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

    # -- who is allowed to ask -----------------------------------------------
    #
    # Binding to 127.0.0.1 keeps other machines out. It does not keep other
    # *pages* out: anything the browser has open can post here, and until now
    # that only cost a reindex. Now it spends the Claude plan. Two checks, and
    # between them a page on the open web can neither reach this nor read a note.

    _LOCAL = ("127.0.0.1", "localhost", "::1", "[::1]")

    def _host_is_local(self) -> bool:
        """Reject a Host we do not recognise, which is what stops DNS rebinding.

        A page on evil.example can re-point its own name at 127.0.0.1 and become
        same-origin with this server. What it cannot do is change the Host header
        it sends, so refusing an unfamiliar one closes that door.
        """
        host = (self.headers.get("Host") or "").strip().lower()
        if not host:
            return False
        if host.startswith("["):                       # [::1]:8765
            name = host.partition("]")[0] + "]"
        else:
            name = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        return name in self._LOCAL

    def _origin_is_ours(self) -> bool:
        """A cross-site page may not post here.

        No Origin at all is fine — that is curl, or a test. A browser always
        sends one on a POST, so a foreign value is exactly the case we want.
        """
        origin = self.headers.get("Origin")
        if origin is None or origin == "null":
            return True
        parsed = urlparse(origin)
        return (parsed.hostname or "").lower() in self._LOCAL

    def _guard(self) -> bool:
        if not self._host_is_local():
            self._fail(HTTPStatus.FORBIDDEN, "unrecognised Host header")
            return False
        if not self._origin_is_ours():
            self._fail(HTTPStatus.FORBIDDEN, "cross-site requests are refused")
            return False
        return True

    def _body(self, cap: int = MAX_BODY_BYTES) -> dict[str, object]:
        """The JSON body of a POST. Missing or empty is an empty dict.

        The body is read before anything is validated. On a keep-alive
        connection an unread body is not discarded — it stays in the socket and
        the next request starts parsing halfway through it, so rejecting early
        would turn one bad request into a broken connection.
        """
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self.close_connection = True
            raise ValueError("Content-Length is not a number") from None

        if length > cap:
            # Too big to drain, so this connection does not get reused.
            self.close_connection = True
            raise ValueError(f"body over the {cap // 1024} kB cap")

        raw = self.rfile.read(length) if length > 0 else b""

        # Requiring JSON is the other half of the cross-site guard: a form or a
        # text/plain fetch is a "simple" request that needs no permission from
        # the browser, while application/json forces a preflight this server
        # does not answer.
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype and ctype != "application/json":
            raise ValueError(f"expected application/json, got {ctype}")

        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"body is not valid JSON: {exc}") from None
        if not isinstance(payload, dict):
            raise ValueError("body must be a JSON object")
        return payload

    # -- routing ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            route = parsed.path
            if route.startswith("/api/"):
                # /api/note serves the full text of any note, so the guard has
                # to cover reads too, not just the routes that spend money.
                if not self._guard():
                    return
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
            if not self._guard():
                return
            if route == "/api/reindex":
                vault = STORE.rebuild()
                self._json({"ok": True, "notes": len(vault.notes),
                            "seconds": round(vault.build_seconds, 3)})
                return
            if route in ("/api/ask", "/api/brief", "/api/plan"):
                self._think(route)
                return
            if route == "/api/listen":
                self._listen()
                return
            if route == "/api/forget":
                self._forget()
                return
            if route == "/api/brain":
                self._brain()
                return
            if route == "/api/tools":
                self._tools()
                return
            self._fail(HTTPStatus.NOT_FOUND, f"no route for POST {route}")
        except BrokenPipeError:
            pass
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self._fail(HTTPStatus.INTERNAL_SERVER_ERROR, "server error — see the terminal")

    def _think(self, route: str) -> None:
        """ask / brief / plan. The key stays here; only the answer goes out."""
        try:
            body = self._body()
        except ValueError as exc:
            self._fail(HTTPStatus.BAD_REQUEST, str(exc))
            return

        vault = STORE.get()
        try:
            if route == "/api/ask":
                answer = brain.ask(vault, str(body.get("q") or ""))
            elif route == "/api/plan":
                answer = brain.plan(vault, str(body.get("goal") or ""))
            else:
                answer = brain.brief(vault)
        except llm.LLMUnavailable as exc:
            # Configuration, not breakage: the graph and the search still work.
            self._fail(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
            return
        except llm.LLMFailed as exc:
            self._fail(HTTPStatus.BAD_GATEWAY, str(exc))
            return

        self._json(answer.to_dict())

        # Deciding what was worth remembering is a second model call, so it
        # happens after the answer has already gone out, on its own thread.
        # The person is not kept waiting for it, and if it fails they still got
        # what they asked for.
        if route == "/api/ask":
            threading.Thread(
                target=memory.learn,
                args=(answer.question, answer.text),
                daemon=True,
                name="jarvis-remember",
            ).start()

    def _listen(self) -> None:
        """A recording in, the words in it out. Nothing is kept.

        The audio arrives base64'd inside the ordinary JSON envelope rather
        than as a multipart upload, so the one content-type rule that keeps
        cross-site posts out covers this route too, with no exception to
        reason about.
        """
        try:
            body = self._body(MAX_AUDIO_BODY_BYTES)
        except ValueError as exc:
            self._fail(HTTPStatus.BAD_REQUEST, str(exc))
            return

        raw = body.get("audio")
        if not isinstance(raw, str) or not raw:
            self._fail(HTTPStatus.BAD_REQUEST, "expected base64 WAV in an 'audio' field")
            return
        try:
            audio = base64.b64decode(raw, validate=True)
        except (ValueError, binascii.Error):
            self._fail(HTTPStatus.BAD_REQUEST, "'audio' is not valid base64")
            return

        try:
            heard = voice.transcribe(audio)
        except voice.VoiceUnavailable as exc:
            self._fail(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
            return
        except voice.VoiceFailed as exc:
            self._fail(HTTPStatus.BAD_GATEWAY, str(exc))
            return

        self._json(heard)

    def _brain(self) -> None:
        """Switch which model answers. Verified before it takes effect."""
        try:
            body = self._body()
        except ValueError as exc:
            self._fail(HTTPStatus.BAD_REQUEST, str(exc))
            return
        try:
            result = llm.choose(str(body.get("model") or ""))
        except ValueError as exc:
            # A malformed id is the caller's mistake, not the model's.
            self._fail(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except llm.LLMUnavailable as exc:
            self._fail(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
            return
        except llm.LLMFailed as exc:
            self._fail(HTTPStatus.BAD_GATEWAY, str(exc))
            return
        self._json({**result, "brains": llm.brains()})

    def _tools(self) -> None:
        """Switch tools on or off by name.

        The list is replaced wholesale rather than toggled one at a time, so
        the page and the allowlist can never drift apart — what you see is
        what the next call is permitted to do.
        """
        try:
            body = self._body()
        except ValueError as exc:
            self._fail(HTTPStatus.BAD_REQUEST, str(exc))
            return
        names = body.get("allowed")
        if not isinstance(names, list):
            self._fail(HTTPStatus.BAD_REQUEST, "allowed must be a list of tool names")
            return
        if len(names) > 60:
            self._fail(HTTPStatus.BAD_REQUEST, "too many tools")
            return
        tools.allow(names)
        self._json(tools.state())

    def _forget(self) -> None:
        """Delete one remembered fact. The only destructive route there is."""
        try:
            body = self._body()
        except ValueError as exc:
            self._fail(HTTPStatus.BAD_REQUEST, str(exc))
            return
        name = str(body.get("name") or "")
        if not name:
            self._fail(HTTPStatus.BAD_REQUEST, "expected a 'name'")
            return
        try:
            gone = memory.forget(name)
        except (OSError, ValueError) as exc:
            self._fail(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if not gone:
            self._fail(HTTPStatus.NOT_FOUND, f"nothing remembered called {name!r}")
            return
        self._json({"ok": True, "facts": [f.to_dict() for f in memory.facts()]})

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

        if route == "/api/brain":
            self._json({"brains": llm.brains(), "current": llm.model_name()})
            return

        if route == "/api/tools":
            self._json(tools.state())
            return

        if route == "/api/memory":
            self._json({"facts": [f.to_dict() for f in memory.facts()],
                        "limit": memory.MAX_FACTS,
                        "where": str(data_mod.MEMORY_DIR)})
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
    # Ask the CLI once, here, whether it is signed in. Every /api/health after
    # this reads what it latched instead of spawning a process per page load.
    llm.probe()
    catch_up(vault)
    caps = capabilities()

    print(vault.report())
    who = llm.account()
    if caps["model"]["reason"]:
        print(f"  model    {caps['model']['reason']}")
    else:
        lang = data_mod.language()
        print(f"  model    {caps['model']['name']} on your "
              f"{who.get('plan') or 'Claude'} subscription ({who.get('auth')})"
              f"{', answering in ' + lang if lang else ''}")
    note = llm.cli_note()
    if note:
        print(f"  note     {note}")
    listen = caps["voice"]["listen"]
    print(f"  listen   {listen['reason'] or listen['model'] + ' (free — spends no TTS quota)'}")
    print(f"  speak    this machine's own voices, in the browser")
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
