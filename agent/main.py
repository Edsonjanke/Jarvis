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

from agent import (brain, data as data_mod, edit, embed, llm, memory,
                   notebook, skills, tools, voice)
from agent.vault import Vault

# A question is a question, not a payload. Anything larger is a mistake or an
# attack, and is refused before it is read into memory.
MAX_BODY_BYTES = 64 * 1024

# Except a recording, which arrives base64'd inside the same JSON envelope so
# that one content-type rule covers every route. 30s of 16 kHz mono WAV is
# ~1 MB, and base64 adds a third.
MAX_AUDIO_BODY_BYTES = 6 * 1024 * 1024

# And a question can carry pictures — a photograph of a supplier's quote, a
# screenshot of a statement. The browser scales them down before sending, so
# this is a ceiling on a mistake rather than a working size.
MAX_IMAGE_BODY_BYTES = 24 * 1024 * 1024

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


def _images(body: dict[str, object]) -> list[tuple[str, str]]:
    """Pictures attached to a question, validated before they go anywhere.

    Everything about the shape is checked here rather than trusted: the type
    against a fixed list, the count, and that the payload is really base64.
    The last one matters most — the string is handed to a subprocess inside
    JSON, and decoding it here is what proves it is a picture and not a
    sentence someone hopes will be read as one.
    """
    raw = body.get("images")
    if not raw:
        return []
    if not isinstance(raw, list):
        raise ValueError("images must be a list")
    if len(raw) > llm.MAX_IMAGES:
        raise ValueError(f"at most {llm.MAX_IMAGES} images per question")

    out: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each image must be an object")
        media_type = str(item.get("media_type") or "").strip().lower()
        data = str(item.get("data") or "")
        if media_type not in llm.ALLOWED_IMAGE_TYPES:
            raise ValueError(f"{media_type or '(none)'} is not an image type Claude reads")
        try:
            decoded = base64.b64decode(data, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("image data is not valid base64") from None
        if not decoded:
            raise ValueError("empty image")
        if len(decoded) > llm.MAX_IMAGE_BYTES:
            raise ValueError(
                f"image over the {llm.MAX_IMAGE_BYTES // 1024 // 1024} MB cap")
        out.append((media_type, data))
    return out


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
        # How you work, as opposed to what is true. Reported here because a
        # skill that silently failed to load is an instruction you believe is
        # in effect and is not.
        "skills": skills.state(),
        # Writing to your own folders. Off the leash by your explicit choice,
        # and reported here so the page can say so — a program that can change
        # your documents should never be quiet about it.
        "edit": {"mode": edit.mode(), "changes": len(edit.changes(limit=200))},
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

    # This request's parsed body, or None before it is read. A class attribute
    # so it is defined even on a path that never reaches do_POST; do_POST
    # resets it per request, because one instance serves a whole connection.
    _body_cache: dict[str, object] | None = None
    _raw: bytes = b""

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

    def _drain(self, cap: int = MAX_BODY_BYTES) -> None:
        """Take the body off the socket. Nothing else.

        Split from parsing on purpose, and it is the split that makes the
        ordering in do_POST possible: the bytes have to leave the socket before
        any check runs, but a check must not be skipped because the bytes were
        wrong. So this reads and judges nothing, and _body() judges without
        reading.
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

        self._raw = self.rfile.read(length) if length > 0 else b""

    def _body(self) -> dict[str, object]:
        """The JSON body of a POST. Missing or empty is an empty dict.

        Parses what _drain already took off the socket, so calling it twice is
        free and calling it late is safe.
        """
        if self._body_cache is not None:
            return self._body_cache

        # Requiring JSON is the other half of the cross-site guard: a form or a
        # text/plain fetch is a "simple" request that needs no permission from
        # the browser, while application/json forces a preflight this server
        # does not answer.
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype and ctype != "application/json":
            raise ValueError(f"expected application/json, got {ctype}")

        if not self._raw:
            self._body_cache = {}
            return self._body_cache
        try:
            payload = json.loads(self._raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"body is not valid JSON: {exc}") from None
        if not isinstance(payload, dict):
            raise ValueError("body must be a JSON object")
        self._body_cache = payload
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
            # One instance serves every request on a keep-alive connection, so
            # last request's body must not be mistaken for this one's.
            self._body_cache = None
            self._raw = b""

            # Take the body off the socket HERE — every route, before any
            # check, and before the guard.
            #
            # On a keep-alive connection an unread body is not discarded. It
            # stays in the socket and the next request starts parsing halfway
            # through it. /api/reindex ignored its body, and the two bytes of
            # "{}" the page sends turned the following request into
            # "{}GET /api/health" — 501, and the page fell over.
            #
            # Before the guard, because that is the version with teeth. A
            # refused request has a body too, and leaving it unread lets a
            # cross-site page hide a whole HTTP request inside it: the 403
            # goes back, the bytes stay, and the parser reads them as a new
            # request — with the Host and Origin the attacker wrote. The guard
            # then approves, because it is reading the attacker's own headers.
            # Measured, not theorised: it switched an MCP tool on from
            # evil.example through a 403. tests/test_keepalive.py keeps it
            # measured.
            try:
                self._drain(MAX_AUDIO_BODY_BYTES if route == "/api/listen"
                            else MAX_IMAGE_BODY_BYTES if route == "/api/ask"
                            else MAX_BODY_BYTES)
            except ValueError as exc:
                self._fail(HTTPStatus.BAD_REQUEST, str(exc))
                return

            # After draining, so a cross-site request still gets told what it
            # is — 403 and "cross-site requests are refused", not a 400 about
            # its Content-Type. Draining is about the socket; this is about
            # who is asking. They are different questions.
            if not self._guard():
                return

            if route == "/api/reindex":
                vault = STORE.rebuild()
                self._json({"ok": True, "notes": len(vault.notes),
                            "seconds": round(vault.build_seconds, 3)})
                return
            if route in ("/api/ask", "/api/brief", "/api/plan", "/api/research"):
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
            if route == "/api/history/forget":
                self._forget_turn()
                return
            if route == "/api/edit":
                self._edit()
                return
            if route == "/api/undo":
                self._undo()
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
            # Validated out here, with the body, because a malformed picture is
            # the caller's mistake — a 400 with the reason. Left inside the
            # block below it would surface as a 500 and read like a crash.
            images = _images(body)
        except ValueError as exc:
            self._fail(HTTPStatus.BAD_REQUEST, str(exc))
            return

        # The conversation this belongs to. The page sends one back to carry
        # the thread on; an absent or unknown one simply starts a new
        # conversation, which is the right thing on a fresh page load.
        thread = str(body.get("thread") or "")[:64]

        vault = STORE.get()
        try:
            if route == "/api/ask":
                answer = brain.ask(vault, str(body.get("q") or ""), thread, images)
            elif route == "/api/plan":
                answer = brain.plan(vault, str(body.get("goal") or ""))
            elif route == "/api/research":
                answer = brain.research(vault, str(body.get("q") or ""),
                                        str(body.get("mode") or "search"), thread)
            else:
                answer = brain.brief(vault)
        except llm.LLMUnavailable as exc:
            # Configuration, not breakage: the graph and the search still work.
            self._fail(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
            return
        except llm.LLMFailed as exc:
            self._fail(HTTPStatus.BAD_GATEWAY, str(exc))
            return

        # Recorded before the reply goes out, so the id and the thread can go
        # with it — the page needs both to continue the conversation. It never
        # raises: a history that cannot be written is a lost note, not a lost
        # answer, and the answer is already in hand.
        turn = notebook.record(answer, thread)
        self._json({**answer.to_dict(), "turn": turn.id, "thread": turn.thread})

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
            body = self._body()
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

    # The one route that hands back a file off your disk, byte for byte.
    #
    # /api/note gives the text JARVIS extracted. That is what it can read, and
    # for 143 PDFs of invoices and purchase orders it is not the same thing as
    # the document: the extractor flattens a layout into a stream of words, and
    # the two it cannot read at all — a scan, an encrypted report — come back
    # empty. So this exists to show you the actual page.
    #
    # Serving files over HTTP is where a hole gets opened, so the rule is
    # narrow and stated once: the ONLY thing a caller may supply is a note id.
    # Not a path, not a fragment of one. The path comes from the index, which
    # was built by walking the roots you configured. Anything not in the index
    # does not exist as far as this route is concerned, which is what makes
    # ../../.env and C:\Windows\... unreachable — they are not ids.
    #
    # The containment check underneath is belt and braces for the case the
    # index cannot rule out: a junction or symlink inside your vault that
    # resolved somewhere else between indexing and now.
    FILE_TYPES = {
        ".pdf": "application/pdf",
        ".md": "text/plain; charset=utf-8",
        ".markdown": "text/plain; charset=utf-8",
        ".mdx": "text/plain; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
        ".text": "text/plain; charset=utf-8",
    }
    MAX_FILE_BYTES = 32 * 1024 * 1024

    def _file(self, note_id: str) -> None:
        vault = STORE.get()
        note = vault.notes.get(note_id)
        if note is None:
            self._fail(HTTPStatus.NOT_FOUND, f"no note with id {note_id!r}")
            return

        try:
            path = Path(note.path).resolve()
        except OSError as exc:
            self._fail(HTTPStatus.NOT_FOUND, f"cannot resolve the file: {exc}")
            return

        # Still inside a configured root, checked now rather than trusted from
        # index time.
        roots = [r.path.resolve() for r in vault.roots]
        if not any(path == root or root in path.parents for root in roots):
            self._fail(HTTPStatus.FORBIDDEN, "that file is outside your vault")
            return

        ctype = self.FILE_TYPES.get(path.suffix.lower())
        if ctype is None:
            self._fail(HTTPStatus.FORBIDDEN, f"{path.suffix} is not a type JARVIS serves")
            return

        try:
            if path.stat().st_size > self.MAX_FILE_BYTES:
                self._fail(HTTPStatus.FORBIDDEN, "file is too large to open here")
                return
            raw = path.read_bytes()
        except OSError as exc:
            self._fail(HTTPStatus.NOT_FOUND, f"cannot read the file: {exc}")
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        # inline so the browser's own PDF viewer opens it in a tab. The
        # filename is quoted and stripped of quotes and newlines, because it
        # comes from your disk and ends up in a header.
        safe = path.name.replace('"', "").replace("\r", "").replace("\n", "")
        self.send_header("Content-Disposition", f'inline; filename="{safe}"')
        # This response is a document, not the app. Nothing in it may run or
        # reach back out — a PDF can carry JavaScript.
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; object-src 'none'; script-src 'none'; "
                         "base-uri 'none'; form-action 'none'; sandbox")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(raw)

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

    def _edit(self) -> None:
        """Write, delete, or change the mode. The only route that alters your files.

        Every refusal from edit.py comes back as 403 with the reason, because
        each one is a rule being enforced rather than a malformed request —
        "fora do vault" and "apagar exige confirmação" are answers, not faults.
        """
        try:
            body = self._body()
        except ValueError as exc:
            self._fail(HTTPStatus.BAD_REQUEST, str(exc))
            return

        action = str(body.get("action") or "").strip()
        try:
            if action == "mode":
                edit.set_mode(str(body.get("mode") or ""))
                self._json(edit.state())
                return
            if action == "write":
                change = edit.write(str(body.get("path") or ""),
                                    str(body.get("content") or ""),
                                    note=str(body.get("note") or ""))
            elif action == "remove":
                change = edit.remove(str(body.get("path") or ""),
                                     confirm=bool(body.get("confirm")),
                                     note=str(body.get("note") or ""))
            else:
                self._fail(HTTPStatus.BAD_REQUEST,
                           "action must be write, remove or mode")
                return
        except edit.Refused as exc:
            self._fail(HTTPStatus.FORBIDDEN, str(exc))
            return

        # The vault on disk no longer matches the index, and an answer built
        # from a stale index would cite text that is not there any more.
        STORE.rebuild()
        self._json({"ok": True, "change": change.to_dict(), **edit.state()})

    def _undo(self) -> None:
        """Put a file back. The reason writing was allowed at all."""
        try:
            body = self._body()
        except ValueError as exc:
            self._fail(HTTPStatus.BAD_REQUEST, str(exc))
            return
        try:
            change = edit.undo(str(body.get("id") or ""))
        except edit.Refused as exc:
            self._fail(HTTPStatus.FORBIDDEN, str(exc))
            return
        STORE.rebuild()
        self._json({"ok": True, "change": change.to_dict(), **edit.state()})

    def _forget_turn(self) -> None:
        """Delete one recorded turn, or a whole conversation.

        History quotes your notes back at you — an answer about accounts
        payable contains your accounts payable. Being able to throw a piece of
        it away is part of it being acceptable to keep at all, which is the
        same argument the memory panel already makes.
        """
        try:
            body = self._body()
        except ValueError as exc:
            self._fail(HTTPStatus.BAD_REQUEST, str(exc))
            return

        thread_id = str(body.get("thread") or "")
        if thread_id:
            gone = notebook.forget_thread(thread_id)
            self._json({"ok": gone > 0, "removed": gone})
            return

        turn_id = str(body.get("id") or "")
        if not turn_id:
            self._fail(HTTPStatus.BAD_REQUEST, "give an id or a thread")
            return
        self._json({"ok": notebook.forget(turn_id), "removed": 1})

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

        if route == "/api/file":
            self._file((query.get("id") or [""])[0])
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

        if route == "/api/skills":
            self._json(skills.state())
            return

        if route == "/api/edit":
            self._json(edit.state())
            return

        if route == "/api/history":
            # ?thread= reads one conversation in reading order; otherwise the
            # most recent turns, newest first, optionally filtered by ?q=.
            thread_id = (query.get("thread") or [""])[0]
            if thread_id:
                self._json({
                    "thread": thread_id,
                    "turns": [t.to_dict() for t in
                              notebook.thread(thread_id, limit=200)],
                })
                return
            try:
                limit = max(1, min(200, int((query.get("limit") or ["50"])[0])))
            except ValueError:
                limit = 50
            self._json({
                "turns": [t.to_dict() for t in
                          notebook.turns(limit=limit, query=(query.get("q") or [""])[0])],
                "threads": notebook.threads(),
                "where": str(data_mod.ROOT / "history"),
            })
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
