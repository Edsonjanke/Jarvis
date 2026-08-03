"""vault.py — folders become a searchable graph.

Knows nothing about demo vs real; it is handed roots by data.py and reads them.
Every file is opened 'rb' and closed. Nothing here writes anywhere, ever.

Three things come out of this module:
  * a graph  — notes as nodes, [[wikilinks]] as edges, degree per node
  * a search — BM25 over title/tags/body, with snippets and file citations
  * a report — counts by type, top hubs, and every file it refused, out loud

Run it directly for the report:  python -m agent.vault
"""

from __future__ import annotations

import math
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):  # allow `python agent/vault.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import data as data_mod
from agent.data import VaultRoot
from agent.pdftext import extract as extract_pdf_text

# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

MAX_FILE_BYTES = 2 * 1024 * 1024

TEXT_SUFFIXES = {".md", ".markdown", ".mdx", ".txt", ".text"}
PDF_SUFFIXES = {".pdf"}
INDEXED_SUFFIXES = TEXT_SUFFIXES | PDF_SUFFIXES

SKIP_DIRS = {
    "node_modules", ".git", ".svn", ".hg", "__pycache__", ".venv", "venv",
    ".obsidian", ".trash", ".cache", ".next", ".nuxt", "dist", "build",
    ".idea", ".vscode", "site-packages", ".pytest_cache", ".mypy_cache",
    "$recycle.bin", "system volume information",
}

# Folder name -> node type. Singular and plural both land here.
FOLDER_TYPES = {
    "client": "client", "clients": "client",
    "project": "project", "projects": "project",
    "meeting": "meeting", "meetings": "meeting",
    "invoice": "invoice", "invoices": "invoice", "finance": "invoice",
    "person": "person", "people": "person", "contacts": "person",
    "idea": "idea", "ideas": "idea",
    "task": "task", "tasks": "task", "todo": "task", "todos": "task",
    "reference": "reference", "references": "reference", "ref": "reference",
    "note": "note", "notes": "note", "daily": "note", "journal": "note",
}

KNOWN_TYPES = ("client", "project", "meeting", "invoice", "person",
               "idea", "task", "reference", "note")

STOPWORDS = {
    # English
    "a", "about", "an", "and", "are", "as", "at", "be", "but", "by", "did", "do",
    "does", "for", "from", "had", "has", "have", "how", "i", "if", "in", "into",
    "is", "it", "its", "me", "my", "no", "not", "of", "on", "or", "our", "so",
    "than", "that", "the", "their", "them", "then", "there", "these", "they",
    "this", "to", "too", "up", "was", "we", "were", "what", "when", "where",
    "which", "who", "why", "will", "with", "you", "your",
    # Portuguese. Without these, "peças que o Paulo desenhou" is four content
    # words to the scorer and the name gets drowned by the filler.
    "à", "ao", "aos", "aquele", "aquilo", "às", "com", "como", "da", "das", "de",
    "dela", "dele", "deles", "depois", "dos", "e", "ela", "ele", "eles", "em",
    "entre", "era", "essa", "esse", "esta", "estas", "este", "estes", "está",
    "estão", "eu", "foi", "foram", "há", "isso", "isto", "já", "lhe", "mais",
    "mas", "meu", "minha", "muito", "na", "nas", "nem", "no", "nos", "nossa",
    "nosso", "num", "numa", "não", "os", "ou", "para", "pela", "pelo", "por",
    "porque", "pra", "pro", "qual", "quais", "quando", "que", "quem", "se",
    "sem", "ser", "seu", "sua", "são", "só", "também", "tem", "ter", "teu",
    "tua", "um", "uma", "você", "vocês",
}
# Tokens arrive accent-folded, so the list has to be folded to match. Written
# accented above because that is how the words are spelled.
STOPWORDS = {
    "".join(c for c in unicodedata.normalize("NFD", w) if not unicodedata.combining(c))
    for w in STOPWORDS
}

# Technical drawings carry their real content in a title block, not in prose.
# These lift it out so a drawing is searchable by weight, material and date
# rather than only by the dimension callout that happens to be drawn first.
DRAW_CODE_RE = re.compile(r"\b\d{3}-\d{5,6}(?:-[A-Z]\d)?\b")

# Two title-block layouts are in use. In the older one the value follows its
# label ("PESO: 0.01 kg"); in the newer one it precedes it ("3.47 kg PESO:").
# Every field below therefore matches both orders, or it silently reads empty
# on half of Edson's drawings.
DRAW_FIELDS = {
    "peso": re.compile(r"PESO:?\s*([\d.,]+)\s*kg|([\d.,]+)\s*kg\s*PESO", re.IGNORECASE),
    "data": re.compile(r"DATA:?\s*(\d{2}/\d{2}/\d{4})|(\d{2}/\d{2}/\d{4})\s*DATA"),
    "material": re.compile(
        r"((?:BARRA|CHAPA|TUBO|PERFIL|BLOCO)[^\n]{0,44}?AISI\s*\d{3}[^\n]{0,26}?MM)",
        re.IGNORECASE),
    "escala": re.compile(r"\b(\d+\s*:\s*\d+(?:[.,]\d+)?)\s*A[0-4]\b|A[0-4]\s*(\d+:\d+(?:[.,]\d+)?)"),
    "formato": re.compile(r"\b\d+\s*:\s*\d+(?:[.,]\d+)?\s*(A[0-4])\b|\b(A[0-4])\s*\d+:\d+"),
    "grupo": re.compile(r"\b(\d{2}-[A-ZÇÃÉÍÓÚÂÊÔÀ][A-ZÇÃÉÍÓÚÂÊÔÀ ]{3,30}?)(?=\s+\d|\s+[A-Z]{2,}\s)"),
    # The name sits before DIEDRO on newer blocks and after FORMATO on older
    # ones; both spellings appear across Edson's 30 drawings.
    "projetista": re.compile(
        r"\b([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,15})\s+DIEDRO"
        r"|DIEDRO:?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,15})\b"
        r"|FORMATO:?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ]{3,15})\b"
    ),
}

# Words that are labels, not values — a loose field regex will otherwise
# happily report the projetista as "ESC".
DRAW_LABEL_WORDS = {
    "ESC", "FORMATO", "DIEDRO", "PESO", "DATA", "DESENHO", "PROJETO", "FOLHA",
    "CLIENTE", "QTD", "SAP", "ANTIGO", "COD", "CÓD", "REV", "APROVADO",
    "DESCRIÇÃO", "PROJETISTA", "DESENHISTA", "NENHUM", "MPCOD", "MPACAB",
}

# Labels that terminate the part name inside a title block.
DRAW_STOP_RE = re.compile(
    r"\b(?:DESENHO|CÓD\.|COD\.|PROJETO|PROJETISTA|DESENHISTA|ESC\.|FORMATO"
    r"|FOLHA|O\.F\.|QTD|CLIENTE|DIEDRO|PESO|DATA)\b[:.]?"
)

WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|([^\[\]]*))?\]\]")
TAG_RE = re.compile(r"(?<![\w&/#])#([A-Za-z][\w/-]{1,40})")
H1_RE = re.compile(r"^\s{0,3}#\s+(.+?)\s*$", re.MULTILINE)
# Accented Latin letters are word characters. An ASCII-only class silently
# splits "peças" into "pe" + "as" and "BRAÇO" into "bra" + "o", which fills the
# index with meaningless fragments and lets them outweigh real terms.
TOKEN_RE = re.compile(r"[0-9a-zà-öø-ÿ][0-9a-zà-öø-ÿ'&.\-]*")
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


def _fold(text: str) -> str:
    """Lowercase, and strip accents — one character in, one character out.

    Length-preserving on purpose. _snippet finds an offset in the folded text
    and then slices the *original* with it, so the two have to stay aligned;
    a plain NFD normalise would shift every index after the first accent.
    Anything that will not fold to a single character is left as it is.
    """
    if text.isascii():
        return text.lower()
    out = []
    for ch in text:
        low = ch.lower()
        if len(low) != 1:
            low = ch
        base = "".join(c for c in unicodedata.normalize("NFD", low)
                       if not unicodedata.combining(c))
        out.append(base if len(base) == 1 else low)
    return "".join(out)


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

def _clean_part_name(fragment: str) -> str:
    """Tidy a candidate part name and reject anything that is not one."""
    name = re.sub(r"\s+", " ", fragment).strip(" -–—.:,")
    name = re.sub(r"\s+(?:ANT|SEM|REV)\.?$", "", name).strip(" -–—.:,")
    if not 4 <= len(name) <= 90:
        return ""
    letters = sum(ch.isalpha() for ch in name)
    return name if letters >= len(name) * 0.5 else ""


def _drawing_description(text: str) -> str:
    """The part name from a drawing's title block.

    Newer drawings put the name after the label:
        '... DATA: DESCRIÇÃO: EIXO INTEIRICO ESTEIRA SINCRONIZADORA 01 - 127EC
         510-283684 DESENHO: ...'
    Older ones put it before:
        '... O.F.: 06-USINAGEM APOIO DO PARAFUSO DO PÉ NIVELADOR 510-244611-
         APOIO DO PARAFUSO DO PÉ NIVELADOR DESCRIÇÃO: PROJETO: ...'
    Try after the label, then before it.
    """
    marker = text.find("DESCRIÇÃO:")
    if marker == -1:
        return ""

    after = text[marker + len("DESCRIÇÃO:") :]
    cut = len(after)
    code = DRAW_CODE_RE.search(after)
    if code:
        cut = min(cut, code.start())
    stop = DRAW_STOP_RE.search(after)
    if stop:
        cut = min(cut, stop.start())
    name = _clean_part_name(after[:cut])
    if name:
        return name

    window = text[max(0, marker - 150) : marker]
    codes = list(DRAW_CODE_RE.finditer(window))
    return _clean_part_name(window[codes[-1].end() :] if codes else window)


def _drawing_fields(text: str) -> dict[str, object]:
    """Title-block fields, so a drawing is searchable by what it actually is."""
    if not text:
        return {}
    found: dict[str, object] = {}
    for key, pattern in DRAW_FIELDS.items():
        # Walk every match, not just the first: a loose alternation can hit a
        # label ("...FORMATO:ESC: 295336 PEDRO DIEDRO...") before the value, and
        # stopping there would drop the field entirely.
        for match in pattern.finditer(text):
            value = next((g for g in match.groups() if g), None)
            if not value:
                continue
            value = re.sub(r"\s+", " ", value).strip()
            if value.upper() in DRAW_LABEL_WORDS:
                continue
            found[key] = value
            break
    codes = DRAW_CODE_RE.findall(text)
    if codes:
        found["desenho"] = codes[0]
    description = _drawing_description(text)
    if description:
        found["descricao"] = description
    return found


def _split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Parse a leading --- block. Deliberately small: scalars and lists only."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    block = text[3:end]
    rest = text[end + 4 :].lstrip("\r\n")

    meta: dict[str, object] = {}
    key: str | None = None
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) and line.lstrip().startswith("- ") and key:
            meta.setdefault(key, [])
            if isinstance(meta[key], list):
                meta[key].append(line.lstrip()[2:].strip().strip("\"'"))
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            meta[key] = [v.strip().strip("\"'") for v in val[1:-1].split(",") if v.strip()]
        elif val:
            meta[key] = val.strip("\"'")
        else:
            meta[key] = []
    return meta, rest


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

@dataclass
class Note:
    id: str
    path: Path
    root: str
    rel: str
    title: str
    type: str
    tags: list[str]
    meta: dict[str, object]
    text: str
    size: int
    mtime: float
    raw_links: list[str] = field(default_factory=list)
    out: set[str] = field(default_factory=set)
    back: set[str] = field(default_factory=set)
    warning: str = ""

    @property
    def degree(self) -> int:
        return len(self.out | self.back)

    @property
    def excerpt(self) -> str:
        flat = re.sub(r"\s+", " ", self.text).strip()
        return flat[:280] + ("…" if len(flat) > 280 else "")

    def to_dict(self, *, with_text: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "tags": self.tags,
            "rel": self.rel,
            "root": self.root,
            "size": self.size,
            "mtime": self.mtime,
            "degree": self.degree,
            "out": sorted(self.out),
            "back": sorted(self.back),
            "meta": {k: v for k, v in self.meta.items() if k != "body"},
            "excerpt": self.excerpt,
        }
        if self.warning:
            payload["warning"] = self.warning
        if with_text:
            payload["text"] = self.text
        return payload


@dataclass
class SkippedFile:
    path: str
    reason: str


@dataclass
class Hit:
    note: Note
    score: float
    snippet: str


# ---------------------------------------------------------------------------
# The vault
# ---------------------------------------------------------------------------

class Vault:
    """An indexed set of folders. Build with Vault.build(roots)."""

    def __init__(self) -> None:
        self.notes: dict[str, Note] = {}
        self.skipped: list[SkippedFile] = []
        self.problems: list[str] = []
        self.unresolved: Counter[str] = Counter()
        self.roots: tuple[VaultRoot, ...] = ()
        self.built_at: float = 0.0
        self.build_seconds: float = 0.0
        self._df: Counter[str] = Counter()
        self._postings: dict[str, list[tuple[str, int]]] = {}
        self._lengths: dict[str, int] = {}
        self._meta_tokens: dict[str, set[str]] = {}
        self._avg_len: float = 1.0

    # -- construction -------------------------------------------------------

    @classmethod
    def build(cls, roots: tuple[VaultRoot, ...], problems: tuple[str, ...] = ()) -> "Vault":
        vault = cls()
        vault.roots = roots
        vault.problems = list(problems)
        started = time.time()
        for root in roots:
            vault._walk(root)
        vault._link()
        vault._index()
        vault.built_at = started
        vault.build_seconds = time.time() - started
        return vault

    @classmethod
    def from_config(cls) -> "Vault":
        report = data_mod.vault_sources()
        return cls.build(report.roots, report.problems)

    def _walk(self, root: VaultRoot) -> None:
        for dirpath, dirnames, filenames in os.walk(root.path, onerror=self._walk_error):
            dirnames[:] = sorted(
                d for d in dirnames
                if d.lower() not in SKIP_DIRS and not d.startswith(".")
            )
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                path = Path(dirpath) / name
                suffix = path.suffix.lower()
                if suffix not in INDEXED_SUFFIXES:
                    continue
                try:
                    stat = path.stat()
                except OSError as exc:
                    self.skipped.append(SkippedFile(str(path), f"unreadable: {exc.strerror or exc}"))
                    continue
                if stat.st_size > MAX_FILE_BYTES:
                    mb = stat.st_size / 1024 / 1024
                    self.skipped.append(SkippedFile(str(path), f"{mb:.1f} MB, over the 2 MB cap"))
                    continue
                note = self._read(path, root, stat.st_size, stat.st_mtime)
                if note is not None:
                    self.notes[note.id] = note

    def _walk_error(self, exc: OSError) -> None:
        self.problems.append(f"cannot enter {getattr(exc, 'filename', '?')}: {exc.strerror or exc}")

    def _read(self, path: Path, root: VaultRoot, size: int, mtime: float) -> Note | None:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            self.skipped.append(SkippedFile(str(path), f"unreadable: {exc.strerror or exc}"))
            return None

        warning = ""
        if path.suffix.lower() in PDF_SUFFIXES:
            body, warning = extract_pdf_text(raw)
            meta: dict[str, object] = _drawing_fields(body)
        else:
            text = raw.decode("utf-8-sig", errors="replace")
            meta, body = _split_frontmatter(text)

        try:
            rel = path.relative_to(root.path).as_posix()
        except ValueError:
            rel = path.name
        note_id = f"{root.label}/{rel}"
        if note_id in self.notes:
            note_id = f"{note_id}#{len(self.notes)}"

        title = self._title_for(meta, body, path)
        if path.suffix.lower() in PDF_SUFFIXES:
            title = self._pdf_title(body, path) or title
        tags = self._tags_for(meta, body)
        note = Note(
            id=note_id,
            path=path,
            root=root.label,
            rel=rel,
            title=title,
            type=self._type_for(meta, tags, path, root),
            tags=tags,
            meta=meta,
            text=body,
            size=size,
            mtime=mtime,
            warning=warning,
        )
        note.raw_links = [
            (m.group(1) or "").strip()
            for m in WIKILINK_RE.finditer(body)
            if (m.group(1) or "").strip()
        ]
        if warning:
            self.skipped.append(SkippedFile(str(path), warning))
        return note

    @staticmethod
    def _title_for(meta: dict[str, object], body: str, path: Path) -> str:
        raw = meta.get("title")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        match = H1_RE.search(body[:4000])
        if match:
            return match.group(1).strip().strip("#").strip()
        return path.stem.replace("-", " ").replace("_", " ").strip() or path.name

    @staticmethod
    def _pdf_title(body: str, path: Path) -> str:
        """Title for a PDF.

        'First short line' is right for a report and wrong for a technical
        drawing, where the first text on the page is a dimension callout —
        that rule produced titles like '12 h6' and '132,75'. Prefer the title
        block's part name, then the filename (Edson's encode the drawing
        number and often the part name), then the first line.
        """
        description = _drawing_description(body)
        if description:
            return description
        stem = path.stem.strip()
        if stem and any(ch.isalpha() for ch in stem):
            return re.sub(r"\s+", " ", stem)
        for line in body.splitlines()[:3]:
            line = line.strip()
            if 3 <= len(line) <= 80 and not line.endswith((".", ":", ";", ",")):
                return line
        return stem

    @staticmethod
    def _tags_for(meta: dict[str, object], body: str) -> list[str]:
        tags: list[str] = []
        raw = meta.get("tags")
        if isinstance(raw, str):
            tags.extend(t.strip() for t in re.split(r"[,\s]+", raw) if t.strip())
        elif isinstance(raw, list):
            tags.extend(str(t).strip() for t in raw if str(t).strip())
        stripped = CODE_FENCE_RE.sub(" ", body)
        tags.extend(m.group(1) for m in TAG_RE.finditer(stripped))
        seen: dict[str, None] = {}
        for tag in tags:
            seen.setdefault(tag.lstrip("#").lower(), None)
        return list(seen)

    @staticmethod
    def _type_for(meta: dict[str, object], tags: list[str], path: Path, root: VaultRoot) -> str:
        raw = meta.get("type")
        if isinstance(raw, str) and raw.strip().lower() in KNOWN_TYPES:
            return raw.strip().lower()
        for tag in tags:
            if tag in KNOWN_TYPES:
                return tag
        try:
            parts = path.relative_to(root.path).parts[:-1]
        except ValueError:
            parts = ()
        for part in reversed(parts):
            hit = FOLDER_TYPES.get(part.lower())
            if hit:
                return hit
        if path.suffix.lower() in PDF_SUFFIXES:
            return "reference"
        return "note"

    # -- graph --------------------------------------------------------------

    def _link(self) -> None:
        by_key: dict[str, str] = {}
        for note in self.notes.values():  # first writer wins, insertion is sorted
            for key in self._keys_for(note):
                by_key.setdefault(key, note.id)

        for note in self.notes.values():
            for target in note.raw_links:
                key = self._normalise(target)
                other = by_key.get(key) or by_key.get(key.rsplit("/", 1)[-1])
                if other is None or other == note.id:
                    if other is None:
                        self.unresolved[target] += 1
                    continue
                note.out.add(other)
                self.notes[other].back.add(note.id)

    def _keys_for(self, note: Note) -> list[str]:
        keys = [
            self._normalise(note.title),
            self._normalise(note.path.stem),
            self._normalise(note.rel),
            self._normalise(note.rel.rsplit(".", 1)[0]),
        ]
        alias = note.meta.get("aliases") or note.meta.get("alias")
        if isinstance(alias, str):
            keys.append(self._normalise(alias))
        elif isinstance(alias, list):
            keys.extend(self._normalise(str(a)) for a in alias)
        return [k for k in keys if k]

    @staticmethod
    def _normalise(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower()).strip("/")

    def neighbours(self, note_id: str) -> list[str]:
        note = self.notes.get(note_id)
        return sorted(note.out | note.back) if note else []

    def shortest_path(self, a: str, b: str) -> list[str]:
        """Undirected BFS. Empty list when there is no route."""
        if a not in self.notes or b not in self.notes:
            return []
        if a == b:
            return [a]
        prev: dict[str, str | None] = {a: None}
        queue = deque([a])
        while queue:
            here = queue.popleft()
            for nxt in self.neighbours(here):
                if nxt in prev:
                    continue
                prev[nxt] = here
                if nxt == b:
                    route = [b]
                    while prev[route[-1]] is not None:
                        route.append(prev[route[-1]])  # type: ignore[arg-type]
                    return list(reversed(route))
                queue.append(nxt)
        return []

    def hubs(self, limit: int = 10) -> list[Note]:
        return sorted(
            self.notes.values(),
            key=lambda n: (-n.degree, n.title.lower()),
        )[:limit]

    def counts_by_type(self) -> dict[str, int]:
        counter = Counter(n.type for n in self.notes.values())
        ordered = {t: counter[t] for t in KNOWN_TYPES if counter[t]}
        for key, val in sorted(counter.items()):
            ordered.setdefault(key, val)
        return ordered

    # -- search -------------------------------------------------------------

    def _index(self) -> None:
        postings: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for note in self.notes.values():
            counts = Counter(self._tokens(note.text))
            for token in self._tokens(note.title):
                counts[token] += 3          # title is worth three body mentions
            for tag in note.tags:
                for token in self._tokens(tag):
                    counts[token] += 2
            for token in self._tokens(note.type):
                counts[token] += 1
            # Title-block fields are the answer to most questions about a
            # drawing — who drew it, what it weighs, what it is made of — so
            # they are searchable, not just displayed.
            meta_tokens: set[str] = set()
            for key, value in note.meta.items():
                if isinstance(value, (list, tuple)):
                    value = " ".join(str(v) for v in value)
                for token in self._tokens(f"{key} {value}"):
                    counts[token] += 2
                meta_tokens.update(self._tokens(str(value)))
            self._meta_tokens[note.id] = meta_tokens
            self._lengths[note.id] = max(1, sum(counts.values()))
            for token, n in counts.items():
                postings[token].append((note.id, n))
                self._df[token] += 1
        self._postings = dict(postings)
        self._avg_len = (
            sum(self._lengths.values()) / len(self._lengths) if self._lengths else 1.0
        )

    @staticmethod
    def _tokens(text: str) -> list[str]:
        """Words, lowercased and stripped of accents.

        TOKEN_RE keeps accented letters so that "peças" stays one word instead
        of splitting into "pe" and "as". Folding happens after, so the index
        and the query both store "pecas": a question typed without accents
        finds a note written with them, and the other way round.

        This is not cosmetic. Dictation gets accents right — scribe_v1 hears
        "qual é a política de depósito" — while a keyboard often does not, and
        the prefix matcher that lets "deposito" find "deposit" cannot see past
        the "ó" in "depósito". Before folding, asking that question out loud
        returned nothing at all while typing it unaccented worked.
        """
        return TOKEN_RE.findall(_fold(text))

    def search(self, query: str, limit: int = 8, types: set[str] | None = None) -> list[Hit]:
        """BM25 with a small hub bonus. Returns notes, scores and snippets."""
        terms = [t for t in self._tokens(query) if len(t) > 1]
        strong = [t for t in terms if t not in STOPWORDS]
        terms = strong or terms
        if not terms or not self.notes:
            return []

        k1, b, total = 1.2, 0.75, len(self.notes)
        scores: dict[str, float] = defaultdict(float)
        for term in set(terms):
            postings = self._postings.get(term)
            if not postings:
                postings = self._prefix_postings(term)
                if not postings:
                    continue
                weight = 0.6                     # partial matches count for less
                df = len({nid for nid, _ in postings})
            else:
                weight = 1.0
                df = self._df[term]
            idf = math.log(1 + (total - df + 0.5) / (df + 0.5))
            for note_id, freq in postings:
                length = self._lengths[note_id]
                norm = freq * (k1 + 1) / (freq + k1 * (1 - b + b * length / self._avg_len))
                scores[note_id] += weight * idf * norm

        ranked: list[Hit] = []
        for note_id, score in scores.items():
            if score <= 0:            # a zero-score hit is noise, not a result
                continue
            note = self.notes[note_id]
            if types and note.type not in types:
                continue
            score *= 1.0 + min(note.degree, 20) * 0.015
            # "quem desenhou X" loses to raw BM25: the person's name appears in
            # many drawings (low idf) while an incidental rare word wins. An
            # exact hit on a title-block value is a much stronger signal of
            # intent than term rarity, so weight it as one.
            field_hits = len(self._meta_tokens.get(note_id, ()) & set(terms))
            if field_hits:
                score *= 1.0 + 0.9 * min(field_hits, 3)
            ranked.append(Hit(note, score, self._snippet(note, terms)))
        ranked.sort(key=lambda h: (-h.score, h.note.title.lower()))
        # Prefix matching produces a long tail of near-zero hits. Spoken aloud
        # they read as answers, so cut anything far below the best match.
        if ranked:
            floor = ranked[0].score * 0.18
            ranked = [h for h in ranked if h.score >= floor]
        return ranked[:limit]

    def _prefix_postings(self, term: str) -> list[tuple[str, int]]:
        if len(term) < 4:
            return []
        out: list[tuple[str, int]] = []
        for token, postings in self._postings.items():
            if token.startswith(term) or term.startswith(token) and len(token) >= 4:
                out.extend(postings)
                if len(out) > 4000:
                    break
        return out

    def _snippet(self, note: Note, terms: list[str], width: int = 240) -> str:
        flat = re.sub(r"\s+", " ", note.text).strip()
        if not flat:
            return note.warning or "(no text)"
        # Folded so the accent-folded search terms can be counted in it, and
        # length-preserving so the offsets still index into `flat`.
        lowered = _fold(flat)
        best, best_score = 0, -1
        step = max(1, width // 3)
        for start in range(0, max(1, len(flat) - width + step), step):
            window = lowered[start : start + width]
            score = sum(window.count(t) for t in terms)
            if score > best_score:
                best, best_score = start, score
        if best_score <= 0:
            return flat[:width] + ("…" if len(flat) > width else "")
        chunk = flat[best : best + width]
        if best > 0:
            chunk = chunk.split(" ", 1)[-1]
            chunk = "…" + chunk
        if best + width < len(flat):
            chunk = chunk.rsplit(" ", 1)[0] + "…"
        return chunk

    # -- serialisation ------------------------------------------------------

    def graph_payload(self) -> dict[str, object]:
        """What the browser gets. Text bodies stay on the server."""
        seen: set[tuple[str, str]] = set()
        edges = []
        for note in self.notes.values():
            for other in note.out:
                pair = tuple(sorted((note.id, other)))
                if pair in seen:
                    continue
                seen.add(pair)
                edges.append({"source": pair[0], "target": pair[1]})
        return {
            "nodes": [n.to_dict() for n in self.notes.values()],
            "edges": edges,
            "counts": self.counts_by_type(),
            "hubs": [n.id for n in self.hubs(10)],
            "roots": [{"label": r.label, "path": str(r.path)} for r in self.roots],
            "problems": self.problems,
            "skipped": [{"path": s.path, "reason": s.reason} for s in self.skipped],
            "built_at": self.built_at,
            "build_seconds": round(self.build_seconds, 3),
        }

    # -- report -------------------------------------------------------------

    def report(self) -> str:
        lines: list[str] = []
        add = lines.append
        add("")
        add(f"  JARVIS vault — {data_mod.mode_label()}")
        add("  " + "─" * 62)
        for root in self.roots:
            add(f"  source   [{root.label}] {root.path}")
        if not self.roots:
            add("  source   NONE")
        edges = sum(len(n.out) for n in self.notes.values())
        add(f"  indexed  {len(self.notes)} notes, {edges} links, "
            f"in {self.build_seconds:.2f}s")
        add("")

        counts = self.counts_by_type()
        add("  by type")
        if counts:
            width = max(len(t) for t in counts)
            biggest = max(counts.values())
            for kind, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
                bar = "█" * max(1, round(n / biggest * 28))
                add(f"    {kind.ljust(width)}  {str(n).rjust(4)}  {bar}")
        else:
            add("    (nothing)")
        add("")

        add("  top 10 hubs")
        hubs = self.hubs(10)
        if hubs:
            width = min(42, max(len(n.title) for n in hubs))
            for i, note in enumerate(hubs, 1):
                title = note.title if len(note.title) <= width else note.title[: width - 1] + "…"
                add(f"    {str(i).rjust(2)}. {title.ljust(width)}  "
                    f"{str(note.degree).rjust(3)} links   {note.type}   {note.rel}")
        else:
            add("    (nothing)")
        add("")

        if self.unresolved:
            top = self.unresolved.most_common(8)
            add(f"  unresolved links  {sum(self.unresolved.values())} "
                f"across {len(self.unresolved)} targets")
            for target, n in top:
                add(f"    [[{target}]] ×{n}")
            add("")

        if self.skipped:
            add(f"  skipped  {len(self.skipped)} files")
            for item in self.skipped[:10]:
                add(f"    {item.reason}  —  {item.path}")
            if len(self.skipped) > 10:
                add(f"    …and {len(self.skipped) - 10} more")
            add("")

        if self.problems:
            add("  PROBLEMS")
            for problem in self.problems:
                add(f"    {problem}")
            add("")

        return "\n".join(lines)


def main() -> int:
    vault = Vault.from_config()
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console
    except (AttributeError, OSError):
        pass
    print(vault.report())
    if not vault.notes:
        print("  Nothing indexed. That is a failure, not an empty result.\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
