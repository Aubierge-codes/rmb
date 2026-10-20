"""Load source documents into the knowledge base.

  python -m ingest.ingest                       # download all six RMB sources and ingest them
  python -m ingest.ingest --only mining-quarry-law
  python -m ingest.ingest --pdf-dir ./downloads # use PDFs already on disk (file name = <id>.pdf)
  python -m ingest.ingest --sources tests/fixtures/sources_test.json --pdf-dir tests/fixtures

Gazetted laws are usually trilingual. Chunks are language-tagged; only English chunks are used by the demo.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import logging
import tempfile
from urllib.parse import unquote, urlparse
from datetime import date

import httpx

from app.config import settings
from app.store import Chunk, get_store

from .chunkers import chunk_articles, chunk_html, chunk_pages, ocr_warning, read_pdf_pages, tag_language

log = logging.getLogger("rmb.ingest")


def fetch(url: str, dest: str) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=120, headers={"User-Agent": "RMB-chatbot-prototype/0.1"}) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for part in r.iter_bytes():
                f.write(part)


def load_pdf(src: dict, pdf_dir: str) -> list[str]:
    """Read a cached PDF, replacing only a corrupt cache entry with a fresh download."""
    path = os.path.join(pdf_dir, src["id"] + ".pdf")
    source_name = os.path.basename(unquote(urlparse(src["url"]).path))
    alternate = os.path.join(pdf_dir, source_name)
    if source_name and alternate != path and os.path.exists(alternate):
        try:
            pages = read_pdf_pages(alternate)
            print(f"  using valid source-named cache {source_name}")
            return pages
        except Exception as exc:
            log.warning("ingestion_source_named_pdf_invalid source_id=%s error_type=%s", src["id"], type(exc).__name__)

    cache_locked = False
    if os.path.exists(path):
        try:
            return read_pdf_pages(path)
        except Exception as exc:
            backup = path + ".invalid"
            try:
                os.replace(path, backup)
            except OSError:
                cache_locked = True
            detail = "could not be replaced in this mounted directory" if cache_locked else f"was retained as {os.path.basename(backup)}"
            print(f"  ! cached PDF could not be parsed ({type(exc).__name__}); {detail}; re-downloading")
            log.warning("ingestion_cached_pdf_invalid source_id=%s error_type=%s", src["id"], type(exc).__name__)
    if cache_locked:
        fd, temp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
    else:
        temp_path = path + ".download"
    print(f"  downloading {src['url']}")
    try:
        fetch(src["url"], temp_path)
        pages = read_pdf_pages(temp_path)
        if cache_locked:
            os.remove(temp_path)
        else:
            os.replace(temp_path, path)
        return pages
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def register(src: dict, n_chunks: int, languages: dict, warnings: list[str]) -> None:
    """Send the document register entry to the case service so RMB staff see it in the content review list."""
    if not settings.case_api_url:
        return
    notes = f"chunks={n_chunks}; languages={languages}" + ("; WARNINGS: " + " | ".join(warnings) if warnings else "")
    try:
        httpx.put(
            f"{settings.case_api_url}/api/v1/documents",
            headers={"X-Service-Key": settings.service_key},
            json={"doc_id": src["id"], "title": src["title"], "category": src["category"], "source_url": src["url"],
                  "owner": src.get("owner"), "version": src.get("version"), "effective_date": src.get("effective_date"),
                  "review_date": src.get("review_date"), "language": "en", "status": src.get("status", "unverified"),
                  "chunks": n_chunks, "notes": notes},
            timeout=10,
        ).raise_for_status()
    except Exception as exc:
        print(f"  ! could not register in case service: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=os.path.join(os.path.dirname(__file__), "sources.json"))
    ap.add_argument("--pdf-dir", default="downloads")
    ap.add_argument("--only", help="ingest a single source id")
    a = ap.parse_args()

    sources = json.load(open(a.sources, encoding="utf-8"))["sources"]
    store = get_store()
    os.makedirs(a.pdf_dir, exist_ok=True)
    logging.basicConfig(level=logging.INFO)
    print(f"Knowledge base: {store.kind}")
    log.info("ingestion_started store=%s source_file=%s", store.kind, a.sources)
    failures = 0
    for src in sources:
        if a.only and src["id"] != a.only:
            continue
        print(f"\n== {src['id']} ({src['kind']})")
        warnings: list[str] = []
        try:
            if src["kind"] == "web":
                response = httpx.get(src["url"], follow_redirects=True, timeout=60, headers={"User-Agent": "RMB-chatbot-prototype/0.1"})
                response.raise_for_status()
                html = response.text
                raw = chunk_html(html)
            else:
                pages = load_pdf(src, a.pdf_dir)
                w = ocr_warning(pages)
                if w:
                    warnings.append(w)
                    print(f"  ! {w}")
                raw = chunk_articles(pages) if src["kind"] == "pdf_articles" else chunk_pages(pages)
            raw = tag_language(raw)
        except Exception as exc:
            print(f"  FAILED: {exc}")
            log.warning("ingestion_source_failed source_id=%s kind=%s error_type=%s", src["id"], src["kind"], type(exc).__name__)
            failures += 1
            continue
        langs: dict[str, int] = {}
        for c in raw:
            langs[c["language"]] = langs.get(c["language"], 0) + 1
        chunks = [Chunk(src["id"], src["title"], src["category"], src["url"], c["section_ref"], c["page"], c["language"], c["text"]) for c in raw]
        store.replace_document(src["id"], chunks)
        print(f"  {len(chunks)} chunks; languages: {langs}")
        log.info("ingestion_source_stored source_id=%s chunks=%d languages=%s total_chunks=%d", src["id"], len(chunks), langs, store.count())
        if langs.get("en", 0) == 0:
            warnings.append("no English chunks found")
            print("  ! no English chunks: check language tagging")
        register(src, len(chunks), langs, warnings)
    print(f"\nDone. Total chunks in knowledge base: {store.count()} ({date.today()})")
    log.info("ingestion_finished store=%s total_chunks=%d failures=%d", store.kind, store.count(), failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
