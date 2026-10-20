"""Knowledge base storage. PgStore (Postgres + pgvector) for the real stack, LocalStore (JSON file) for laptop testing."""
from __future__ import annotations

import json
import os
from contextlib import closing
from dataclasses import asdict, dataclass
from functools import lru_cache

import numpy as np
import logging

from .config import settings
from .embeddings import embed

log = logging.getLogger("rmb.store")


@dataclass
class Chunk:
    doc_id: str
    doc_title: str
    category: str  # regulatory | promotion | public_info
    source_url: str
    section_ref: str
    page: int | None
    language: str
    text: str


class LocalStore:
    kind = "local-json"

    def __init__(self, path: str):
        self.path = path
        self.chunks: list[Chunk] = []
        self.matrix = np.zeros((0, 1), dtype=np.float32)
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.chunks = [Chunk(**c) for c in json.load(f)["chunks"]]
        self._rebuild()

    def _rebuild(self) -> None:
        self.matrix = np.vstack([embed(c.section_ref + " " + c.text) for c in self.chunks]) if self.chunks else np.zeros((0, 1), dtype=np.float32)

    def replace_document(self, doc_id: str, chunks: list[Chunk]) -> None:
        self.chunks = [c for c in self.chunks if c.doc_id != doc_id] + chunks
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"chunks": [asdict(c) for c in self.chunks]}, f, ensure_ascii=False)
        self._rebuild()

    def search(self, vec: np.ndarray, k: int, language: str = "en") -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []
        sims = self.matrix @ vec
        order = np.argsort(-sims)
        out = []
        for i in order:
            if self.chunks[i].language in {language, "mixed", "unknown"}:
                out.append((self.chunks[i], float(sims[i])))
            if len(out) >= k:
                break
        return out

    def count(self) -> int:
        return len(self.chunks)


class PgStore:
    kind = "postgres-pgvector"

    def __init__(self, dsn: str):
        import psycopg2  # imported lazily so local mode needs no database driver

        self.psycopg2 = psycopg2
        self.dsn = dsn

    def _conn(self):
        return self.psycopg2.connect(self.dsn)

    @staticmethod
    def _vec(v: np.ndarray) -> str:
        return "[" + ",".join(f"{x:.6f}" for x in v) + "]"

    def replace_document(self, doc_id: str, chunks: list[Chunk]) -> None:
        with closing(self._conn()) as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM kb_chunks WHERE doc_id=%s", (doc_id,))
            for c in chunks:
                cur.execute(
                    "INSERT INTO kb_chunks (doc_id, doc_title, category, source_url, section_ref, page, language, text, embedding) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                    (c.doc_id, c.doc_title, c.category, c.source_url, c.section_ref, c.page, c.language, c.text,
                     self._vec(embed(c.section_ref + " " + c.text))),
                )

    def search(self, vec: np.ndarray, k: int, language: str = "en") -> list[tuple[Chunk, float]]:
        v = self._vec(vec)
        with closing(self._conn()) as conn, conn, conn.cursor() as cur:
            cur.execute(
                "SELECT doc_id, doc_title, category, source_url, section_ref, page, language, text, 1-(embedding <=> %s::vector) "
                "FROM kb_chunks WHERE language IN (%s, 'mixed', 'unknown') ORDER BY embedding <=> %s::vector LIMIT %s",
                (v, language, v, k),
            )
            return [(Chunk(*r[:8]), float(r[8])) for r in cur.fetchall()]

    def count(self) -> int:
        with closing(self._conn()) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM kb_chunks")
            return int(cur.fetchone()[0])


@lru_cache(maxsize=1)
def get_store():
    return PgStore(settings.database_url) if settings.database_url else LocalStore(settings.kb_path)


def reset_store_cache() -> None:
    get_store.cache_clear()
