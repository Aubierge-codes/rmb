-- Knowledge base tables (owned by the AI service). Case tables are created by the PHP case service on first start.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_chunks (
    id          BIGSERIAL PRIMARY KEY,
    doc_id      TEXT NOT NULL,
    doc_title   TEXT NOT NULL,
    category    TEXT NOT NULL,            -- regulatory | promotion | public_info
    source_url  TEXT,
    section_ref TEXT NOT NULL,            -- e.g. "Article 12: Application" or "Page 7"
    page        INTEGER,
    language    TEXT NOT NULL,            -- en | fr | rw | mixed | unknown (demo uses 'en' only)
    text        TEXT NOT NULL,
    embedding   vector(512) NOT NULL,     -- must match DIM in ai-service/app/embeddings.py
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS kb_chunks_doc ON kb_chunks (doc_id);
CREATE INDEX IF NOT EXISTS kb_chunks_embedding ON kb_chunks USING hnsw (embedding vector_cosine_ops);
