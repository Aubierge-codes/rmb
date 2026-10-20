"""Split source documents so that every answer can cite the exact article, page or section."""
from __future__ import annotations

import re
from html.parser import HTMLParser

from app.lang import detect_language

MAX_CHARS = 1500


def _clean(t: str) -> str:
    t = t.replace("\u00ad", "").replace("\x00", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def read_pdf_pages(path: str) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    return [_clean(p.extract_text() or "") for p in reader.pages]


def ocr_warning(pages: list[str]) -> str | None:
    if not pages:
        return "no pages found"
    avg = sum(len(p) for p in pages) / len(pages)
    if avg < 80:
        return f"very little text per page ({avg:.0f} chars): the PDF may be scanned and need OCR"
    return None


def _split_long(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Split on paragraph boundaries, falling back to sentences, keeping chunks under `limit`."""
    if len(text) <= limit:
        return [text]
    paras = re.split(r"\n\s*\n|\n(?=\(?[0-9a-z]{1,2}[.)] )", text)
    out, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 1 > limit and cur:
            out.append(cur.strip())
            cur = ""
        while len(p) > limit:
            cut = p.rfind(". ", 0, limit)
            cut = cut + 1 if cut > 200 else limit
            out.append(p[:cut].strip())
            p = p[cut:]
        cur += p + "\n"
    if cur.strip():
        out.append(cur.strip())
    return out


ARTICLE_RE = re.compile(r"^\s*(Article|Section)\s+(\d+|one|first)\b\s*[:.\-–]?\s*(.*)$", re.IGNORECASE | re.MULTILINE)
CHAPTER_RE = re.compile(r"^\s*(CHAPTER|Chapter)\s+([IVXLC\d]+|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)\b\s*[:.\-–]?\s*(.*)$", re.MULTILINE)


def chunk_articles(pages: list[str]) -> list[dict]:
    """Laws: one chunk per article (long articles split), tagged with the page where it starts."""
    full, offsets = "", []
    for i, p in enumerate(pages, 1):
        offsets.append((len(full), i))
        full += p + "\n"
    heads = list(ARTICLE_RE.finditer(full))
    if not heads:  # not an article-structured text: fall back to pages
        return chunk_pages(pages)

    def page_at(pos: int) -> int:
        pg = 1
        for off, n in offsets:
            if off <= pos:
                pg = n
        return pg

    chunks = []
    for idx, m in enumerate(heads):
        end = heads[idx + 1].start() if idx + 1 < len(heads) else len(full)
        body = full[m.end():end].strip()
        # drop chapter headings that trail the previous article into this one
        body = CHAPTER_RE.sub("", body).strip()
        title = m.group(3).strip()
        ref = f"{m.group(1).title()} {m.group(2)}" + (f": {title}" if title else "")
        if not body:
            continue
        parts = _split_long(body)
        for j, part in enumerate(parts, 1):
            chunks.append({"section_ref": ref + (f" (part {j})" if len(parts) > 1 else ""), "page": page_at(m.start()), "text": part})
    return chunks


def chunk_pages(pages: list[str]) -> list[dict]:
    """Prospectuses and reports: split by page, then by paragraph if long."""
    chunks = []
    for i, p in enumerate(pages, 1):
        if len(p) < 40:
            continue
        parts = _split_long(p, 1200)
        for j, part in enumerate(parts, 1):
            chunks.append({"section_ref": f"Page {i}" + (f" (part {j})" if len(parts) > 1 else ""), "page": i, "text": part})
    return chunks


class _Text(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "header", "noscript", "svg"}

    def __init__(self):
        super().__init__()
        self.skip = 0
        self.blocks: list[tuple[str, str]] = []  # (heading, text)
        self.heading = "Page"
        self._in_h = False
        self._buf = ""

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag in ("h1", "h2", "h3"):
            self._flush()
            self._in_h = True
            self._buf = ""

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag in ("h1", "h2", "h3"):
            self.heading = _clean(self._buf) or self.heading
            self._in_h = False
            self._buf = ""
        if tag in ("p", "li", "div", "br", "tr"):
            self._buf += "\n"

    def handle_data(self, data):
        if not self.skip:
            self._buf += data

    def _flush(self):
        t = _clean(self._buf)
        if t and not self._in_h and len(t) > 40:
            self.blocks.append((self.heading, t))
        self._buf = ""

    def close(self):
        super().close()
        self._flush()


def chunk_html(html: str) -> list[dict]:
    p = _Text()
    p.feed(html)
    p.close()
    chunks = []
    for heading, text in p.blocks:
        for j, part in enumerate(_split_long(text, 1200), 1):
            chunks.append({"section_ref": heading + (f" (part {j})" if j > 1 else ""), "page": None, "text": part})
    return chunks


def tag_language(chunks: list[dict]) -> list[dict]:
    for c in chunks:
        c["language"] = detect_language(c["text"])
    return chunks
