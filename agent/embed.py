"""embed.py — THE ONLY FILE THAT TALKS TO OLLAMA.

Same rule as llm.py owning the model and voice.py owning ElevenLabs. This one
is optional in a way the others are not: if Ollama is not running, everything
here reports unavailable and retrieval carries on without it.

WHY IT EXISTS. vault.search is BM25 — lexical. Folding accents (step 4) made
"depósito" reach a note that says "deposit", because the prefix matcher can
see through the fold. It cannot see through a different word: asking "quanto
está em atraso?" of notes that say "outstanding" returns nothing at all, which
is the failure this closes.

There are two ways to close it, and brain.py uses both. Asking the model for
equivalent words costs one cheap call and needs nothing installed. Embeddings
find notes that share no word at all, and need Ollama. The first is the floor,
the second is the ceiling.

NOTHING IS SENT ANYWHERE. Ollama is a local server on 127.0.0.1. If it is not
there, no request leaves the machine and no note text is embedded at all.

    Install:  https://ollama.com  then  ollama pull nomic-embed-text

Run it directly to see where you stand:  python -m agent.embed
"""

from __future__ import annotations

import json
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if __package__ in (None, ""):  # allow `python agent/embed.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod

HOST = "http://127.0.0.1:11434"
MODEL = "nomic-embed-text"

# Ollama is either running or it is not; a slow probe would be a stalled page
# load. Cached so /api/health does not pay for it on every request.
PROBE_TIMEOUT = 1.5
PROBE_CACHE_SECONDS = 30
EMBED_TIMEOUT = 120

# Indexing every note costs one pass; after that only changed notes are redone.
CACHE_FILE = "embeddings.json"
BATCH = 32

_probe: tuple[float, bool] | None = None
_vectors: dict[str, dict[str, object]] | None = None


def _setting(name: str, default: str) -> str:
    return data_mod.setting(name, default)


def host() -> str:
    return _setting("OLLAMA_HOST", HOST).rstrip("/")


def model() -> str:
    return _setting("OLLAMA_EMBED_MODEL", MODEL)


# ---------------------------------------------------------------------------
# Is it there?
# ---------------------------------------------------------------------------

def available() -> bool:
    """True when Ollama answers and has the embedding model pulled."""
    global _probe
    now = time.time()
    if _probe is not None and now - _probe[0] < PROBE_CACHE_SECONDS:
        return _probe[1]

    ok = False
    try:
        with urllib.request.urlopen(f"{host()}/api/tags", timeout=PROBE_TIMEOUT) as res:
            tags = json.loads(res.read())
        names = {str(m.get("name", "")).split(":")[0] for m in tags.get("models", [])}
        ok = model().split(":")[0] in names
    except (OSError, ValueError):
        ok = False

    _probe = (now, ok)
    return ok


def reason() -> str | None:
    """Why semantic recall is off, or None when it is on."""
    if available():
        return None
    try:
        urllib.request.urlopen(f"{host()}/api/tags", timeout=PROBE_TIMEOUT).close()
    except OSError:
        return f"Ollama is not running at {host()} — semantic recall is off, words still work"
    return f"Ollama is running but {model()!r} is not pulled — run: ollama pull {model()}"


# ---------------------------------------------------------------------------
# Vectors
# ---------------------------------------------------------------------------

def embed(texts: list[str]) -> list[list[float]] | None:
    """Vectors for each text, or None if Ollama could not do it."""
    out: list[list[float]] = []
    for text in texts:
        body = json.dumps({"model": model(), "prompt": text[:8000]}).encode("utf-8")
        request = urllib.request.Request(
            f"{host()}/api/embeddings", data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=EMBED_TIMEOUT) as res:
                vector = json.loads(res.read()).get("embedding")
        except (OSError, ValueError):
            return None
        if not isinstance(vector, list) or not vector:
            return None
        out.append([float(v) for v in vector])
    return out


def _cache_path() -> Path:
    return data_mod.state_dir() / CACHE_FILE


def _load() -> dict[str, dict[str, object]]:
    global _vectors
    if _vectors is not None:
        return _vectors
    try:
        _vectors = json.loads(_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _vectors = {}
    return _vectors


def _save() -> None:
    try:
        _cache_path().write_text(json.dumps(_load()), encoding="utf-8")
    except OSError:
        pass          # a cache that cannot be written is slow, not broken


def _stamp(note) -> str:
    """Changes when the note does, so a stale vector is never reused."""
    return f"{int(note.mtime)}:{note.size}"


def index(vault, *, limit: int | None = None) -> int:
    """Embed anything new or changed. Returns how many were done.

    Only the title, type and the head of the body — enough to place a note in
    meaning-space, and it keeps a first run over a real vault to seconds
    rather than minutes.
    """
    if not available():
        return 0

    cache = _load()
    stale = [n for n in vault.notes.values()
             if cache.get(n.id, {}).get("stamp") != _stamp(n)]
    if limit:
        stale = stale[:limit]
    if not stale:
        return 0

    done = 0
    for start in range(0, len(stale), BATCH):
        chunk = stale[start:start + BATCH]
        vectors = embed([f"{n.title}. {n.type}. {n.text[:1200]}" for n in chunk])
        if vectors is None:
            break
        for note, vector in zip(chunk, vectors):
            cache[note.id] = {"stamp": _stamp(note), "v": vector}
            done += 1

    # Notes that no longer exist should not linger in the cache.
    for gone in set(cache) - set(vault.notes):
        cache.pop(gone, None)

    _save()
    return done


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def similar(vault, query: str, limit: int = 6, floor: float = 0.55) -> list[str]:
    """Note ids closest in meaning to the query. Empty when Ollama is absent.

    The floor matters: cosine similarity always returns *something*, and
    without a cut-off the least-unrelated note in the vault would be presented
    as a match to a question about nothing in it.
    """
    if not available() or not query.strip():
        return []
    cache = _load()
    if not cache:
        return []
    vector = embed([query])
    if not vector:
        return []

    scored = []
    for note_id, entry in cache.items():
        if note_id not in vault.notes:
            continue
        score = _cosine(vector[0], entry.get("v") or [])
        if score >= floor:
            scored.append((score, note_id))
    scored.sort(reverse=True)
    return [note_id for _, note_id in scored[:limit]]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    print(f"\n  ollama   {host()}")
    print(f"  model    {model()}")
    problem = reason()
    if problem:
        print(f"  status   OFF — {problem}\n")
        print("  Word-based recall still works; this only adds meaning-based recall.")
        print("  To turn it on:  https://ollama.com  then  ollama pull " + model() + "\n")
        return 1

    from agent.vault import Vault

    vault = Vault.from_config()
    started = time.time()
    done = index(vault)
    print(f"  status   ON")
    print(f"  indexed  {done} new or changed, {len(_load())} cached, "
          f"in {time.time() - started:.1f}s")
    print(f"  cache    {_cache_path()}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
