-- Enables pgvector and creates the same chunk store DocuChat uses in production
-- (mirrors the Supabase `docuchat_chunks` table + cosine match function).
-- Runs automatically on first `docker-compose up` via the Postgres init hook.

CREATE EXTENSION IF NOT EXISTS vector;

-- gte-small embeddings are 384-dimensional (same model as the production embed
-- Edge Function). Swap the dimension here if you use a different embedder.
CREATE TABLE IF NOT EXISTS docuchat_chunks (
    id          bigserial PRIMARY KEY,
    doc_id      text        NOT NULL,
    title       text,
    content     text        NOT NULL,
    embedding   vector(384),
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- HNSW index for fast cosine-similarity top-k retrieval.
CREATE INDEX IF NOT EXISTS docuchat_chunks_embedding_idx
    ON docuchat_chunks
    USING hnsw (embedding vector_cosine_ops);

-- Cosine-similarity match function, mirroring the production RPC.
CREATE OR REPLACE FUNCTION match_docuchat_chunks(
    query_embedding vector(384),
    match_count int DEFAULT 5,
    min_similarity float DEFAULT 0.79
)
RETURNS TABLE (
    id bigint,
    doc_id text,
    title text,
    content text,
    similarity float
)
LANGUAGE sql STABLE
AS $$
    SELECT
        c.id,
        c.doc_id,
        c.title,
        c.content,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM docuchat_chunks c
    WHERE 1 - (c.embedding <=> query_embedding) >= min_similarity
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
$$;
