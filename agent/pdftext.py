"""pdftext.py — PDF text extraction with only the standard library.

Split out of vault.py because doing this properly is not small. A naive
extractor pulls the raw character codes out of a content stream and calls it
text. That works for PDFs written with standard fonts, and produces confident
garbage for everything else — Edson's SolidWorks drawings come out as
"' ( 6 & 5 , d ® 2" where the file actually says "DESCRIÇÃO", because the font
is subsetted and the codes are glyph indices, not characters.

Garbage that looks like text is worse than no text: it poisons the search index
and it reads as success. So this module does the real work:

  * indexes the PDF's objects and finds each page's font resources
  * parses every /ToUnicode CMap into a code -> character map
  * tokenises the content stream, tracks the active font via Tf, and decodes
    each shown string through that font's own map
  * breaks lines on actual vertical movement, not on every positioning operator

Not supported, and reported rather than faked: encryption, and scanned pages
with no text layer (those need OCR, which needs a dependency).
"""

from __future__ import annotations

import re
import zlib

# ---------------------------------------------------------------------------
# Byte-level helpers
# ---------------------------------------------------------------------------

WHITESPACE = b" \t\r\n\f\x00"
DELIMITERS = b"()<>[]{}/%"

_ESCAPES = {
    ord("n"): 0x0A, ord("r"): 0x0D, ord("t"): 0x09,
    ord("b"): 0x08, ord("f"): 0x0C,
    ord("("): 0x28, ord(")"): 0x29, ord("\\"): 0x5C,
}


def _decode_bytes(blob: bytes) -> str:
    """Fallback decoding when a font has no /ToUnicode map.

    WinAnsi is the common simple-font encoding, not Latin-1: they agree on
    ASCII and on £, and differ across 0x80-0x9F where the dashes and curly
    quotes live.
    """
    try:
        return blob.decode("cp1252")
    except UnicodeDecodeError:
        return blob.decode("latin-1", "replace")


def _literal_bytes(tok: bytes) -> bytes:
    """Raw bytes of a PDF (...) string, escapes resolved, charset untouched."""
    out = bytearray()
    i, n = 1, len(tok) - 1
    while i < n:
        ch = tok[i]
        if ch != 0x5C:
            out.append(ch)
            i += 1
            continue
        i += 1
        if i >= n:
            break
        nxt = tok[i]
        if nxt in _ESCAPES:
            out.append(_ESCAPES[nxt])
            i += 1
        elif 0x30 <= nxt <= 0x37:                       # octal, up to 3 digits
            digits = bytearray()
            while i < n and len(digits) < 3 and 0x30 <= tok[i] <= 0x37:
                digits.append(tok[i])
                i += 1
            out.append(int(digits.decode("ascii"), 8) & 0xFF)
        elif nxt in (0x0A, 0x0D):                       # line continuation
            i += 1
            if i < n and tok[i] in (0x0A, 0x0D) and tok[i] != nxt:
                i += 1
        else:
            out.append(nxt)
            i += 1
    return bytes(out)


def _hex_bytes(tok: bytes) -> bytes:
    digits = re.sub(rb"[^0-9A-Fa-f]", b"", tok)
    if len(digits) % 2:
        digits += b"0"
    try:
        return bytes.fromhex(digits.decode("ascii"))
    except ValueError:
        return b""


# ---------------------------------------------------------------------------
# Object index
# ---------------------------------------------------------------------------

_OBJ_RE = re.compile(rb"(?:^|[\r\n\s])(\d+)\s+(\d+)\s+obj\b")


def _index_objects(raw: bytes) -> dict[int, bytes]:
    """Map object number -> its body bytes, including objects inside /ObjStm.

    Each top-level object's body runs to the start of the next object header —
    a more robust boundary than searching for 'endobj', which can legitimately
    appear inside binary stream data.

    PDF 1.5 onwards may pack most objects into compressed *object streams*.
    A reader that only walks top-level `N 0 obj` headers sees the font
    descriptors and none of the page tree — which is exactly how a drawing ends
    up decoded with no font map at all.
    """
    headers = [(int(m.group(1)), m.start(), m.end()) for m in _OBJ_RE.finditer(raw)]

    objects: dict[int, bytes] = {}
    for i, (num, _hstart, body_start) in enumerate(headers):
        end = headers[i + 1][1] if i + 1 < len(headers) else len(raw)
        objects[num] = raw[body_start : max(body_start, end)]

    for body in list(objects.values()):
        head = _dict_slice(body)
        if b"/ObjStm" not in head:
            continue
        data = _stream_data(body)
        count = re.search(rb"/N\s+(\d+)", head)
        first = re.search(rb"/First\s+(\d+)", head)
        if not data or not count or not first:
            continue
        n, offset0 = int(count.group(1)), int(first.group(1))
        try:
            numbers = [int(t) for t in data[:offset0].split()]
        except ValueError:
            continue
        pairs = [(numbers[k], numbers[k + 1]) for k in range(0, min(len(numbers), 2 * n) - 1, 2)]
        for idx, (obj_num, rel) in enumerate(pairs):
            begin = offset0 + rel
            stop = offset0 + pairs[idx + 1][1] if idx + 1 < len(pairs) else len(data)
            if 0 <= begin < stop <= len(data):
                objects.setdefault(obj_num, data[begin:stop])

    return objects


def _dict_slice(body: bytes) -> bytes:
    """The outermost << >> dictionary in an object body, brackets included."""
    start = body.find(b"<<")
    if start == -1:
        return b""
    depth, i, n = 0, start, len(body)
    while i < n - 1:
        pair = body[i : i + 2]
        if pair == b"<<":
            depth += 1
            i += 2
            continue
        if pair == b">>":
            depth -= 1
            i += 2
            if depth == 0:
                return body[start:i]
            continue
        i += 1
    return body[start:]


def _stream_data(body: bytes) -> bytes | None:
    """Decoded stream payload of an object, or None when it has no stream."""
    marker = body.find(b"stream")
    if marker == -1:
        return None
    cursor = marker + 6
    if body[cursor : cursor + 2] == b"\r\n":
        cursor += 2
    elif body[cursor : cursor + 1] in (b"\n", b"\r"):
        cursor += 1
    end = body.find(b"endstream", cursor)
    blob = body[cursor:end] if end != -1 else body[cursor:]
    blob = blob.rstrip(b"\r\n")

    if b"/FlateDecode" in body[:marker]:
        try:
            return zlib.decompress(blob)
        except zlib.error:
            try:
                return zlib.decompressobj().decompress(blob)   # truncated tail
            except zlib.error:
                return None
    return blob


def _refs(fragment: bytes, key: bytes) -> list[int]:
    """Object numbers referenced by `key` — handles `N 0 R` and `[N 0 R ...]`."""
    match = re.search(re.escape(key) + rb"\s*(\[[^\]]*\]|\d+\s+\d+\s+R)", fragment)
    if not match:
        return []
    return [int(n) for n in re.findall(rb"(\d+)\s+\d+\s+R", match.group(1))]


# ---------------------------------------------------------------------------
# /ToUnicode CMaps
# ---------------------------------------------------------------------------

def _cmap_chars(blob: bytes) -> str:
    """A CMap destination is UTF-16BE, possibly several code points."""
    if len(blob) % 2:
        blob += b"\x00"
    try:
        return blob.decode("utf-16-be")
    except UnicodeDecodeError:
        return blob.decode("utf-16-be", "replace")


def _parse_cmap(data: bytes) -> dict[int, str]:
    """Parse a /ToUnicode CMap into {character code: text}."""
    table: dict[int, str] = {}

    for block in re.findall(rb"beginbfchar(.*?)endbfchar", data, re.DOTALL):
        for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", block):
            table[int(src, 16)] = _cmap_chars(bytes.fromhex(dst.decode("ascii")))

    for block in re.findall(rb"beginbfrange(.*?)endbfrange", data, re.DOTALL):
        # <lo> <hi> <dst>  — consecutive codes map to consecutive characters
        for lo, hi, dst in re.findall(
            rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>", block
        ):
            start, stop = int(lo, 16), int(hi, 16)
            base = bytes.fromhex(dst.decode("ascii"))
            if stop - start > 65535:
                continue
            for offset in range(stop - start + 1):
                bumped = bytearray(base)
                if bumped:
                    carry = bumped[-1] + offset
                    bumped[-1] = carry & 0xFF
                    if carry > 0xFF and len(bumped) > 1:
                        bumped[-2] = (bumped[-2] + (carry >> 8)) & 0xFF
                table[start + offset] = _cmap_chars(bytes(bumped))
        # <lo> <hi> [<d1> <d2> ...] — explicit destination per code
        for lo, _hi, arr in re.findall(
            rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]", block, re.DOTALL
        ):
            start = int(lo, 16)
            for offset, dst in enumerate(re.findall(rb"<([0-9A-Fa-f]*)>", arr)):
                table[start + offset] = _cmap_chars(bytes.fromhex(dst.decode("ascii")))

    return table


class Font:
    """What the renderer needs to know about one font resource."""

    __slots__ = ("cmap", "two_byte")

    def __init__(self, cmap: dict[int, str] | None, two_byte: bool) -> None:
        self.cmap = cmap
        self.two_byte = two_byte

    def decode(self, blob: bytes) -> str:
        if not self.cmap:
            return _decode_bytes(blob)
        out: list[str] = []
        if self.two_byte:
            for i in range(0, len(blob) - 1, 2):
                out.append(self.cmap.get((blob[i] << 8) | blob[i + 1], ""))
        else:
            for byte in blob:
                out.append(self.cmap.get(byte, ""))
        return "".join(out)


def _build_fonts(objects: dict[int, bytes]) -> dict[int, Font]:
    """Font object number -> Font. Only fonts that declare /ToUnicode."""
    fonts: dict[int, Font] = {}
    for num, body in objects.items():
        head = _dict_slice(body)
        if b"/Font" not in head and b"/ToUnicode" not in head:
            continue
        targets = _refs(head, b"/ToUnicode")
        if not targets:
            continue
        stream = _stream_data(objects.get(targets[0], b""))
        if not stream:
            continue
        table = _parse_cmap(stream)
        if table:
            fonts[num] = Font(table, two_byte=b"/Type0" in head)
    return fonts


def _page_font_maps(objects: dict[int, bytes], fonts: dict[int, Font]) -> list[dict[bytes, Font]]:
    """One resource-name -> Font map per page, in page order."""
    maps: list[dict[bytes, Font]] = []
    for num, body in objects.items():
        head = _dict_slice(body)
        if b"/Type" not in head or not re.search(rb"/Type\s*/Page\b", head):
            continue

        resources = head
        res_refs = _refs(head, b"/Resources")
        if res_refs:
            resources = _dict_slice(objects.get(res_refs[0], b""))
        elif b"/Resources" not in head:
            parents = _refs(head, b"/Parent")
            if parents:
                parent = _dict_slice(objects.get(parents[0], b""))
                p_res = _refs(parent, b"/Resources")
                resources = _dict_slice(objects.get(p_res[0], b"")) if p_res else parent

        block = re.search(rb"/Font\s*(<<.*?>>|\d+\s+\d+\s+R)", resources, re.DOTALL)
        if not block:
            maps.append({})
            continue
        fragment = block.group(1)
        if not fragment.startswith(b"<<"):
            ref = _refs(b"/Font " + fragment, b"/Font")
            fragment = _dict_slice(objects.get(ref[0], b"")) if ref else b""

        page_map: dict[bytes, Font] = {}
        for name, obj_num in re.findall(rb"/([^\s/<>\[\]]+)\s+(\d+)\s+\d+\s+R", fragment):
            font = fonts.get(int(obj_num))
            if font:
                page_map[name] = font
        maps.append(page_map)
    return maps


def _page_contents(objects: dict[int, bytes]) -> list[bytes]:
    """Concatenated content-stream bytes per page, in page order."""
    pages: list[bytes] = []
    for _num, body in objects.items():
        head = _dict_slice(body)
        if not re.search(rb"/Type\s*/Page\b", head):
            continue
        parts: list[bytes] = []
        for ref in _refs(head, b"/Contents"):
            data = _stream_data(objects.get(ref, b""))
            if data:
                parts.append(data)
        pages.append(b"\n".join(parts))
    return pages


# ---------------------------------------------------------------------------
# Content-stream tokeniser
# ---------------------------------------------------------------------------

def _tokens(data: bytes):
    """Yield (kind, bytes) for a PDF content stream."""
    i, n = 0, len(data)
    while i < n:
        ch = data[i]
        if ch in WHITESPACE:
            i += 1
            continue
        if ch == 0x25:                                   # % comment
            nl = data.find(b"\n", i)
            i = n if nl == -1 else nl + 1
            continue
        if ch == 0x28:                                   # ( literal string
            j, depth = i + 1, 1
            while j < n and depth:
                c = data[j]
                if c == 0x5C:
                    j += 2
                    continue
                if c == 0x28:
                    depth += 1
                elif c == 0x29:
                    depth -= 1
                j += 1
            yield "str", data[i:j]
            i = j
            continue
        if data[i : i + 2] == b"<<":
            yield "op", b"<<"
            i += 2
            continue
        if data[i : i + 2] == b">>":
            yield "op", b">>"
            i += 2
            continue
        if ch == 0x3C:                                   # < hex string
            close = data.find(b">", i)
            if close == -1:
                return
            yield "hex", data[i : close + 1]
            i = close + 1
            continue
        if ch == 0x2F:                                   # /Name
            j = i + 1
            while j < n and data[j] not in WHITESPACE and data[j] not in DELIMITERS:
                j += 1
            yield "name", data[i + 1 : j]
            i = j
            continue
        if ch in b"[]":
            yield "arr", data[i : i + 1]
            i += 1
            continue
        if ch in b"+-." or 0x30 <= ch <= 0x39:
            j = i
            while j < n and (data[j] in b"+-.eE" or 0x30 <= data[j] <= 0x39):
                j += 1
            yield "num", data[i:j]
            i = j
            continue
        j = i
        while j < n and data[j] not in WHITESPACE and data[j] not in DELIMITERS:
            j += 1
        if j == i:
            j = i + 1
        yield "op", data[i:j]
        i = j


def _as_float(tok: bytes) -> float:
    try:
        return float(tok)
    except ValueError:
        return 0.0


def _render_page(content: bytes, font_map: dict[bytes, Font]) -> str:
    """Shown text for one page, with line breaks where the baseline moves."""
    lines: list[str] = []
    line: list[str] = []
    stack: list[tuple[str, bytes]] = []
    font: Font | None = None
    cur_y = last_y = 0.0
    leading = 0.0
    have_y = False

    def newline() -> None:
        nonlocal line
        if line:
            lines.append("".join(line))
            line = []

    def show(blob: bytes) -> None:
        nonlocal last_y, have_y
        text = font.decode(blob) if font else _decode_bytes(blob)
        if not text:
            return
        # A baseline change is a real line break; pure horizontal movement is
        # kerning between glyphs of the same line. Spaces are encoded glyphs,
        # so nothing has to be inferred from the positioning numbers.
        if have_y and abs(cur_y - last_y) > 0.5:
            newline()
        last_y = cur_y
        have_y = True
        line.append(text)

    for kind, tok in _tokens(content):
        if kind != "op":
            stack.append((kind, tok))
            continue

        op = tok
        if op == b"BT":
            cur_y = last_y = 0.0
            have_y = False
        elif op == b"Tf":
            if len(stack) >= 2 and stack[-2][0] == "name":
                font = font_map.get(stack[-2][1])
        elif op in (b"Td", b"TD"):
            if len(stack) >= 2:
                cur_y += _as_float(stack[-1][1])
                if op == b"TD":
                    leading = -_as_float(stack[-1][1])
        elif op == b"TL":
            if stack:
                leading = _as_float(stack[-1][1])
        elif op == b"Tm":
            if len(stack) >= 6:
                cur_y = _as_float(stack[-1][1])
        elif op == b"T*":
            cur_y -= leading
        elif op == b"Tj":
            if stack:
                k, s = stack[-1]
                show(_literal_bytes(s) if k == "str" else _hex_bytes(s))
        elif op in (b"'", b'"'):
            cur_y -= leading
            if stack:
                k, s = stack[-1]
                if k in ("str", "hex"):
                    show(_literal_bytes(s) if k == "str" else _hex_bytes(s))
        elif op == b"TJ":
            # Numbers inside the array are kerning adjustments; ignore them.
            for k, s in stack:
                if k == "str":
                    show(_literal_bytes(s))
                elif k == "hex":
                    show(_hex_bytes(s))
        elif op == b"ET":
            newline()

        stack.clear()

    newline()
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract(raw: bytes, max_chars: int = 400_000) -> tuple[str, str]:
    """Best-effort PDF text. Returns (text, warning); warning is '' when clean."""
    if b"/Encrypt" in raw[:4096] or b"/Encrypt" in raw[-4096:]:
        return "", "PDF criptografado — não indexado"

    try:
        objects = _index_objects(raw)
        fonts = _build_fonts(objects)
        font_maps = _page_font_maps(objects, fonts)
        pages = _page_contents(objects)
    except Exception:  # noqa: BLE001 — a malformed PDF must not kill the index
        objects, fonts, font_maps, pages = {}, {}, [], []

    chunks: list[str] = []
    for i, content in enumerate(pages):
        if not content:
            continue
        try:
            text = _render_page(content, font_maps[i] if i < len(font_maps) else {})
        except Exception:  # noqa: BLE001
            continue
        if text.strip():
            chunks.append(text)
        if sum(len(c) for c in chunks) >= max_chars:
            chunks.append("\n[truncado]")
            break

    if not chunks:
        # Structured parsing found nothing. Fall back to scanning every stream,
        # which catches PDFs whose page tree we failed to walk.
        chunks = _salvage(raw, max_chars)

    if not chunks:
        return "", "sem texto extraível (página digitalizada, ou codificação não suportada)"

    text = re.sub(r"[ \t]+", " ", "\n".join(chunks))
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    # A page of lone glyphs means the font map was missed — say so instead of
    # letting shredded text into the search index as if it were real.
    words = [w for w in text.split() if w]
    if len(words) > 30 and sum(len(w) for w in words) / len(words) < 1.6:
        return "", "texto ilegível (fonte sem mapa /ToUnicode utilizável)"

    return text, ""


def _salvage(raw: bytes, max_chars: int) -> list[str]:
    """Last resort: decode every stream with no font information at all."""
    chunks: list[str] = []
    pos = 0
    seen = 0
    while seen < 3000:
        start = raw.find(b"stream", pos)
        if start == -1:
            break
        cursor = start + 6
        if raw[cursor : cursor + 2] == b"\r\n":
            cursor += 2
        elif raw[cursor : cursor + 1] in (b"\n", b"\r"):
            cursor += 1
        end = raw.find(b"endstream", cursor)
        if end == -1:
            break
        blob = raw[cursor:end].rstrip(b"\r\n")
        pos = end + 9
        seen += 1
        try:
            content = zlib.decompress(blob)
        except zlib.error:
            content = blob
        if b"BT" not in content and b"Tj" not in content and b"TJ" not in content:
            continue
        try:
            text = _render_page(content, {})
        except Exception:  # noqa: BLE001
            continue
        if text.strip():
            chunks.append(text)
            if sum(len(c) for c in chunks) >= max_chars:
                break
    return chunks
